"""Pre-registration native injection vs frozen registered comparator; TRAIN only."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import importlib.metadata
import json,math,sys,tempfile,time
from pathlib import Path
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from native_overlay import native_response,write_derivative,guard_source,digest,SOURCE_BIT,OUTLIER_BIT
OWN=Path(__file__).resolve().parent;DATA=OWN.parent;NAMESPACE=DATA.parents[2];PACKAGE=NAMESPACE/'backend/inference';RAW=Path('/tmp/spaceapps-v4-native-data');ALLOWED=RAW/'development'
sys.path.insert(0,str(PACKAGE))
from ml_inference.prepare import prepare
from training.evaluate_background import read_native,project_response


def request_for(group,rows,identity):
    return dict(schema_version=1,analysis_id=identity,source=dict(kind='fits',observations=rows,region=dict(right_ascension_deg=group['center'][0],declination_deg=group['center'][1],width_arcmin=6.,height_arcmin=6.)),options=dict(pixel_scale_arcsec=6.15,mask_policy='motion'))

def context(group):
    if group['split']!='train'or group['parent_id']not in ['v4-train01','v4-train02','v4-train03']:raise ValueError('Only the fixed TRAIN parents are authorized')
    manifest=Path(group['downloads_manifest']['path'])
    if digest(manifest)!=group['downloads_manifest']['sha256']:raise ValueError('TRAIN manifest changed')
    rows=json.loads(manifest.read_text())
    for row in rows:
        guard_source(row['path'],ALLOWED)
        if digest(row['path'])!=row['sha256']:raise ValueError('Original TRAIN bytes changed')
    observations=[dict(path=row['path'],sha256=row['sha256'],frame_id=Path(row['path']).stem)for row in rows]
    stack=prepare(request_for(group,observations,'v4-physics-original-'+group['parent_id']))
    lookup={Path(row['path']).stem:row for row in rows};ordered=[lookup[frame['frame_id']]for frame in stack.frames]
    natives=[];mads=[]
    for row in ordered:
        natives.append(read_native(row['path'],stack.grid,stack.images.shape[1:]))
        with fits.open(row['path'],memmap=False)as h:
            signal=np.asarray(h['IMAGE'].data,float)-h['ZODI'].data;flags=h['FLAGS'].data.astype(np.int64);variance=np.asarray(h['VARIANCE'].data,float)
            good=((flags&~(SOURCE_BIT|OUTLIER_BIT))==0)&np.isfinite(signal)&np.isfinite(variance)&(variance>0)
            values=signal[good];mads.append(float(1.4826*np.median(abs(values-np.median(values)))))
    if not np.isfinite(mads).all()or min(mads)<=0:raise ValueError('Native robust noise scale unavailable')
    return dict(group=group,stack=stack,rows=ordered,natives=natives,native_mads=mads,amplitude_base=float(np.median(mads)))

def stationary_anchor(case,native):
    shape=native['good'].shape;h,w=shape;center=np.array([(w-1)/2,(h-1)/2])
    if'phase_xy'in case:return np.floor(center)+np.asarray(case['phase_xy']),None
    if case['id']=='left-edge':return np.array([1.25,(h-1)/2+.25]),None
    candidates=[]
    if case['id']=='masked-interior':
        for y,x in np.argwhere(~native['good']):
            if 6<=x<w-6 and 6<=y<h-6:candidates.append((float((x-center[0])**2+(y-center[1])**2),int(y),int(x),[float(x),float(y)]))
    elif case['id']=='mixed-mask-boundary':
        for y in range(6,h-6):
            for x in range(6,w-7):
                if native['good'][y,x]!=native['good'][y,x+1]:candidates.append((float((x+.5-center[0])**2+(y-center[1])**2),y,x,[x+.5,float(y)]))
        if not candidates:
            for y in range(6,h-7):
                for x in range(6,w-6):
                    if native['good'][y,x]!=native['good'][y+1,x]:candidates.append((float((x-center[0])**2+(y+.5-center[1])**2),y,x,[float(x),y+.5]))
    if not candidates:return None,'Predeclared mask category unavailable in anchor epoch; no replacement'
    return np.asarray(min(candidates,key=lambda item:item[:3])[3]),None

def cases(plan,ctx,stage):
    stack=ctx['stack'];n=len(ctx['rows']);parent=ctx['group']['parent_id']
    if stage=='stationary':
        for case in plan['stationary_cases']:
            anchor,unavailable=stationary_anchor(case,ctx['natives'][0]);sky=None
            if anchor is not None:sky=np.tile(np.asarray(ctx['natives'][0]['wcs'].pixel_to_world_values(*anchor),float),(n,1))
            for multiplier in plan['amplitude_multipliers_native_MAD']:
                yield dict(parent_id=parent,stage=stage,case_id=case['id'],amplitude_multiplier=multiplier,anchor_native_xy=None if anchor is None else anchor.tolist(),unavailable=unavailable),sky
    else:
        moving=plan['moving_stage'];h,w=stack.images.shape[1:];origin=np.array([(w-1)*moving['origin_registered_fraction_xy'][0],(h-1)*moving['origin_registered_fraction_xy'][1]])
        for speed in moving['speeds_registered_pixels_per_hour']:
            for degrees in moving['direction_degrees']:
                velocity=speed*np.array([math.cos(math.radians(degrees)),math.sin(math.radians(degrees))]);positions=origin+stack.times[:,None]*velocity
                sky=np.column_stack(stack.grid.pixel_to_world_values(positions[:,0],positions[:,1]))
                for multiplier in moving['amplitude_multipliers_native_MAD']:
                    yield dict(parent_id=parent,stage=stage,case_id=f'speed-{speed:g}-direction-{degrees:g}',speed_registered_px_hour=speed,direction_degrees=degrees,
                               origin_registered_xy=origin.tolist(),velocity_registered_xy_hour=velocity.tolist(),amplitude_multiplier=multiplier,unavailable=None),sky

def centroid(values):
    weights=np.maximum(np.nan_to_num(values,nan=0.),0.);total=float(weights.sum())
    if total<=0:return None
    yy,xx=np.indices(values.shape);return [float((xx*weights).sum()/total),float((yy*weights).sum()/total)]

def trial(ctx,identity,sky):
    stack=ctx['stack'];amplitude=identity['amplitude_multiplier']*ctx['amplitude_base'];frames=[];derived_rows=[];responses=[];new_metadata=[]
    scratch=RAW/'physics-validation-scratch';scratch.mkdir(exist_ok=True)
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='native-overlay-',dir=scratch)as directory:
        for index,(row,native,world)in enumerate(zip(ctx['rows'],ctx['natives'],sky)):
            response,meta=native_response(row['path'],world,allowed_root=ALLOWED)
            target=Path(directory)/(Path(row['path']).stem+'-v4-research.fits')
            derivative=write_derivative(row['path'],target,response,amplitude,allowed_root=ALLOWED)
            frame_id=stack.frames[index]['frame_id']
            derived_rows.append(dict(path=str(target),sha256=derivative['derivative_sha256'],frame_id=frame_id,release='v4-physics-derivative',processing_version='v4-native-overlay-f64-v1'))
            position=np.asarray(stack.grid.world_to_pixel_values(*world),float);old_response,old_meta=project_response(native,stack.grid,position)
            responses.append(old_response);new_metadata.append(meta);frames.append(dict(original_obsid=row['obs_id'],old_projector_metadata=old_meta,independent_native_metadata=meta,derivative=derivative))
        prepared=prepare(request_for(ctx['group'],derived_rows,'v4-physics-derived-'+identity['parent_id']))
        if not np.array_equal(prepared.times,stack.times)or[frame['observation_id']for frame in prepared.frames]!=[frame['observation_id']for frame in stack.frames]:raise ValueError('Physical epoch identity/time changed')
        if not np.array_equal(np.isfinite(prepared.images),np.isfinite(stack.images))or not np.array_equal(prepared.outlier,stack.outlier)or not np.array_equal(prepared.bloom,stack.bloom):raise ValueError('Derivative changed prepared mask/support')
        epoch_metrics=[];max_abs=0.;relative_max=0.;constant_residual_max=0.
        for index,(original,derived,response)in enumerate(zip(stack.images,prepared.images,responses)):
            finite=np.isfinite(original);raw=amplitude*response;old_added=np.where(finite,original+raw,np.nan);old_shift=float(np.nanmedian(old_added));old_added-=old_shift
            old_delta=old_added-original;actual_delta=derived-original;residual=actual_delta-old_delta
            max_error=float(np.max(abs(residual[finite])));norm=float(np.linalg.norm(old_delta[finite]));relative=float(np.linalg.norm(residual[finite])/norm)if norm else(0. if not np.any(residual[finite])else None)
            premedian_residual=actual_delta-raw;constant=float(np.median(premedian_residual[finite]));constant_deviation=float(np.max(abs(premedian_residual[finite]-constant)))
            max_abs=max(max_abs,max_error);constant_residual_max=max(constant_residual_max,constant_deviation)
            if relative is not None:relative_max=max(relative_max,relative)
            epoch_metrics.append(dict(epoch=index,old_registered_response_sum=float(response[finite].sum()),actual_prepared_delta_sum=float(actual_delta[finite].sum()),
                old_postregistration_median_shift=old_shift,measured_delta_minus_raw_constant=constant,median_constant_prediction_error=abs(constant+old_shift),
                delta_vs_old_add_median_max_abs=max_error,delta_vs_old_add_median_relative_L2=relative,delta_minus_raw_max_nonconstant_residual=constant_deviation,
                old_positive_response_centroid_xy=centroid(np.where(finite,raw,np.nan)),actual_median_restored_positive_centroid_xy=centroid(np.where(finite,actual_delta-constant,np.nan)),
                finite_registered_pixels=int(finite.sum()),native_crop_response_sum=new_metadata[index]['native_crop_response_sum'],native_motion_good_response_sum=new_metadata[index]['native_motion_good_response_sum'],
                independent_and_old_epsf_zone_agree=new_metadata[index]['zone']==frames[index]['old_projector_metadata']['zone']))
    for frame in frames:frame['derivative']['deleted_after_validation']=True
    return dict(identity,amplitude_native_discrete_sum_MJy_per_sr=amplitude,native_mads_MJy_per_sr=ctx['native_mads'],sky_ra_dec_per_epoch=sky.tolist(),times_hours=stack.times.tolist(),
        all_derivative_fits_deleted=all(not Path(frame['derivative']['derivative_path']).exists()for frame in frames),all_nonimage_arrays_masks_physical_epochs_preserved=True,
        error=None,executed=True,maximum_delta_error=max_abs,maximum_relative_L2_error=relative_max,maximum_nonconstant_delta_residual=constant_residual_max,
        epoch_metrics=epoch_metrics,frames=frames,elapsed_seconds=time.monotonic()-started,added_photon_noise=False,variance_updated=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['stationary','moving'],required=True);args=parser.parse_args()
    plan_path=OWN/'plan.json';plan=json.loads(plan_path.read_text())
    if digest(plan_path)!='8f7ae2a66172df19648f74148f5485c31e0f7c0ae1b6d36b4a65e394556bbdd3':raise ValueError('Prospective physics matrix changed')
    invocation=dict(created_utc=datetime.now(timezone.utc).isoformat(),stage=args.stage,plan_sha256=digest(plan_path),source_sha256={str(path):digest(path)for path in [Path(__file__),OWN/'native_overlay.py',PACKAGE/'ml_inference/prepare.py',PACKAGE/'training/evaluate_background.py']},
        versions={name:importlib.metadata.version(name)for name in ['numpy','scipy','astropy']},final_pixels_opened=False,detector_or_model_called=False)
    with(OWN/f'invocation-{args.stage}.json').open('x')as f:json.dump(invocation,f,indent=2);f.write('\n')
    results=[]
    with(OWN/f'results-{args.stage}.jsonl').open('x')as stream:
        for group in plan['parents']:
            ctx=context(group)
            for identity,sky in cases(plan,ctx,args.stage):
                if identity['unavailable']:result=dict(identity,executed=False,error=None)
                else:
                    try:result=trial(ctx,identity,sky)
                    except Exception as error:result=dict(identity,executed=False,error=dict(type=type(error).__name__,message=str(error)))
                stream.write(json.dumps(result,allow_nan=False)+'\n');stream.flush();results.append(result)
                print(group['parent_id'],identity['case_id'],identity['amplitude_multiplier'],result.get('maximum_delta_error'),result.get('error')or result.get('unavailable')or'ok',flush=True)
            del ctx
    executed=[r for r in results if r.get('executed')];summary=dict(schema_version=1,stage=args.stage,invocation=invocation,planned_trials=len(results),executed_trials=len(executed),unavailable_trials=sum(bool(r.get('unavailable'))for r in results),runtime_error_trials=sum(r.get('error')is not None for r in results),
        maximum_delta_error=max((r['maximum_delta_error']for r in executed),default=None),maximum_relative_L2_error=max((r['maximum_relative_L2_error']for r in executed),default=None),
        maximum_nonconstant_delta_residual=max((r['maximum_nonconstant_delta_residual']for r in executed),default=None),all_scratch_fits_deleted=all(r.get('all_derivative_fits_deleted')for r in executed),
        units='Amplitude is MJy/sr discrete native-pixel sum; NOT calibrated point-source flux',added_photon_noise=False,variance_updated=False,final_pixels_opened=False,detector_or_model_called=False,
        interpretation='Engineering equivalence of native IMAGE injection before immutableprepare and registered injection comparator, with median subtraction quantified. Not recovery/performance evidence.')
    with(OWN/f'summary-{args.stage}.json').open('x')as f:json.dump(summary,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
