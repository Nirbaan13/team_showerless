"""Conditional diagonal-native uncertainty through immutable masked SIP prepare.

Gaussian perturbations sanity-check an explicit mathematical assumption only.
They are not source Poisson noise, training labels or instrument covariance data.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import importlib.metadata
import json,math,sys,tempfile,time
from pathlib import Path
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.stats import chi2
from operators import bilinear_operator,covariance_for_rows,affine_amplitude_weights
OWN=Path(__file__).resolve().parent
sys.path.insert(0,str(OWN.parent))
from native_overlay import guard_source,digest,_equal_array
import run_validation as source_context
RAW=Path('/tmp/spaceapps-v4-native-data');ALLOWED=RAW/'development';PLAN_SHA='54a4e8c243d7bb44aad61944d723f8527fa19fb316de02010420544feab54394'


def write_conditional_derivative(source,target,perturbation):
    source=guard_source(source,ALLOWED);original_sha=digest(source)
    with fits.open(source,memmap=False) as original:
        copy=fits.HDUList([hdu.copy() for hdu in original])
        copy['IMAGE'].data=np.asarray(original['IMAGE'].data,np.float64)+np.asarray(perturbation,np.float64)
        for key in ['BSCALE','BZERO']:copy['IMAGE'].header.remove(key,ignore_missing=True,remove_all=True)
        copy[0].header['V4DERIV']=True;copy[0].header['V4COND']=True;copy[0].header['V4ORIG']=original_sha
        copy[0].header.add_history('V4 conditional independent native Gaussian uncertainty perturbation.')
        copy[0].header.add_history('Not source Poisson noise; original VARIANCE is the conditional reference.')
        for hdu in copy:
            for key in ['CHECKSUM','DATASUM']:hdu.header.remove(key,ignore_missing=True,remove_all=True)
        copy.writeto(target,checksum=True,output_verify='exception');copy.close()
        with fits.open(target,memmap=False,checksum=True) as derived:
            if derived['IMAGE'].header['BITPIX']!=-64:raise ValueError('Conditional derivative is not float64')
            for a,b in zip(original,derived):
                if a.name!=b.name or (a.name!='IMAGE' and not _equal_array(a.data,b.data)):raise ValueError('Conditional derivative changed non-IMAGE arrays')
                if b.verify_checksum()!=1 or b.verify_datasum()!=1:raise ValueError('Conditional derivative checksum failed')
    if digest(source)!=original_sha:raise ValueError('Original archive bytes changed')
    return dict(original_sha256=original_sha,derivative_sha256=digest(target),original_path=str(source),derivative_path=str(target),conditional_gaussian_perturbation=True,
                source_photon_noise_added=False,variance_reference_updated=False,nonimage_arrays_preserved=True,image_bitpix=-64,checksums_valid=True,archive_bytes_claimed=False)


def frame_operator(ctx,index):
    stack=ctx['stack'];row=ctx['rows'][index]
    with fits.open(guard_source(row['path'],ALLOWED),memmap=False) as hdus:
        header=hdus[0].header.copy();header.update(hdus['IMAGE'].header)
        image=np.asarray(hdus['IMAGE'].data,float);zodi=np.asarray(hdus['ZODI'].data,float);variance=np.asarray(hdus['VARIANCE'].data,float);flags=np.asarray(hdus['FLAGS'].data,np.int64)
        signal=image-zodi
        good=((flags&~((1<<21)|(1<<19)))==0)&np.isfinite(signal)&np.isfinite(variance)&(variance>0)
        if str(header.get('BUNIT')).replace(' ','')!='MJy/sr' or str(hdus['VARIANCE'].header.get('BUNIT')).replace(' ','')!='MJy2/sr2':raise ValueError('Conditional variance units differ from declared units')
        native=WCS(header).celestial
    yy,xx=np.indices(stack.images.shape[1:]);nx,ny=native.world_to_pixel_values(*stack.grid.pixel_to_world_values(xx,yy))
    result=bilinear_operator(nx,ny,good,variance);valid=result['usable']
    if not np.array_equal(valid,np.isfinite(stack.images[index])):raise ValueError('Explicit operator mask differs from immutable prepare')
    projected=np.asarray(result['operator']@np.where(good,signal,0.).ravel()).reshape(valid.shape)
    centered=np.where(valid,projected,np.nan);centered-=np.nanmedian(centered)
    difference=float(np.nanmax(abs(centered-stack.images[index])))
    if difference>1e-10:raise ValueError('Explicit bilinear signal operator differs from immutable prepare')
    result.update(has_sip=native.sip is not None,operator_vs_prepare_max_abs=difference,native_shape=list(signal.shape),native_good=good)
    return result


def patch_centers(plan,valid):
    h,w=valid.shape;center=np.array([(w-1)/2,(h-1)/2]);result=[]
    for patch in plan['patches']:
        if patch['id']=='center-phase':point=center+np.array([.25,.75])
        elif patch['id']=='registered-left-edge':point=np.array([1.25,center[1]+.25])
        else:
            candidates=[]
            for y in range(3,h-3):
                for x in range(3,w-4):
                    if valid[y,x]!=valid[y,x+1]:candidates.append((float((x+.5-center[0])**2+(y-center[1])**2),y,x,[x+.5,float(y)]))
            if not candidates:
                for y in range(3,h-4):
                    for x in range(3,w-3):
                        if valid[y,x]!=valid[y+1,x]:candidates.append((float((x-center[0])**2+(y+.5-center[1])**2),y,x,[float(x),y+.5]))
            point=np.asarray(min(candidates,key=lambda item:item[:3])[3]) if candidates else None
        result.append((patch['id'],point))
    return result


def patch_fit(plan,point,result):
    if point is None:raise ValueError('Predeclared mixed support category unavailable; no replacement')
    h,w=result['usable'].shape;r=plan['patch_radius_pixels'];cx,cy=np.floor(point).astype(int)
    xx,yy=np.meshgrid(np.arange(cx-r,cx+r+1),np.arange(cy-r,cy+r+1));template=np.exp(-((xx-point[0])**2+(yy-point[1])**2)/(2*plan['gaussian_template_sigma_pixels']**2));template/=template.sum()
    inside=(xx>=0)&(xx<w)&(yy>=0)&(yy<h);valid=np.zeros(xx.shape,bool);valid[inside]=result['usable'][yy[inside],xx[inside]]
    indices=(yy[valid]*w+xx[valid]).astype(int);values=template[valid]
    if len(indices)<3:raise ValueError('Fewer than three usable predeclared patch pixels')
    covariance=covariance_for_rows(result['operator'],result['native_variance'],indices);fit=affine_amplitude_weights(values,covariance)
    fit.update(indices=indices,usable_pixels=len(indices),full_patch_pixels=template.size,registered_xy=point.tolist(),template_values=values,
               covariance=covariance,median_diagonal_variance=float(np.median(np.diag(covariance))))
    return fit


def neighbour_stats(result):
    h,w=result['usable'].shape;yy,xx=np.indices((h,w));first=(yy*w+xx);output={}
    for name,dy,dx in [('right',0,1),('up',1,0),('diagonal',1,1)]:
        keep=np.zeros((h,w),bool);keep[:h-dy,:w-dx]=result['usable'][:h-dy,:w-dx]&result['usable'][dy:,dx:]
        left=first[keep];right=left+dy*w+dx
        a=result['operator'][left];b=result['operator'][right]
        covariance=np.asarray(a.multiply(b)@result['native_variance']).ravel();diagonal=result['variance_diagonal'].ravel()
        rho=covariance/np.sqrt(diagonal[left]*diagonal[right])
        output[name]=dict(pairs=len(rho),rho_min=float(rho.min()),rho_median=float(np.median(rho)),rho_max=float(rho.max()),rho_q05_q95=np.quantile(rho,[.05,.95]).tolist()) if len(rho) else dict(pairs=0)
    return output


def conditional_spotcheck(ctx,noise,expected_noise):
    scratch=RAW/'physics-validation-scratch';scratch.mkdir(exist_ok=True);row=ctx['rows'][0]
    with tempfile.TemporaryDirectory(prefix='conditional-variance-',dir=scratch) as directory:
        target=Path(directory)/(Path(row['path']).stem+'-v4-conditional-noise.fits')
        derivative=write_conditional_derivative(row['path'],target,noise)
        observations=[]
        for index,original in enumerate(ctx['rows']):
            observations.append(dict(path=str(target) if index==0 else original['path'],sha256=derivative['derivative_sha256'] if index==0 else original['sha256'],frame_id=ctx['stack'].frames[index]['frame_id'],release='v4-conditional-research' if index==0 else'dr1',processing_version='v4-conditional-f64-v1' if index==0 else'original-declared'))
        prepared=source_context.prepare(source_context.request_for(ctx['group'],observations,'v4-conditional-prepare-spotcheck'))
        original=ctx['stack'].images[0];valid=np.isfinite(original)
        expected=np.where(valid,original+expected_noise,np.nan);expected-=np.nanmedian(expected)
        if not np.array_equal(np.isfinite(prepared.images),np.isfinite(ctx['stack'].images)):raise ValueError('Conditional derivative changed prepared masks')
        error=float(np.nanmax(abs(prepared.images[0]-expected)))
        if error>1e-10:raise ValueError('Conditional operator+median differs from actual derived FITS prepare')
        derivative.update(prepare_vs_explicit_operator_max_abs=error,physical_epochs_preserved=prepared.frames[0]['physical_observation_id']==ctx['stack'].frames[0]['physical_observation_id'])
    derivative['deleted_after_validation']=not Path(derivative['derivative_path']).exists();return derivative


def run_frame(plan,ctx,index):
    result=frame_operator(ctx,index);valid=result['usable'];shape=valid.shape;fields=[];fits_by_id={}
    for patch_id,point in patch_centers(plan,valid):
        try:
            fit=patch_fit(plan,point,result);fits_by_id[patch_id]=fit
            fields.append(dict(patch_id=patch_id,available=True,registered_xy=fit['registered_xy'],usable_pixels=fit['usable_pixels'],full_patch_pixels=fit['full_patch_pixels'],
                variance_exact=fit['variance_exact'],variance_diagonal_assumption=fit['variance_diagonal_assumption'],sigma_ratio_exact_to_diagonal=fit['sigma_ratio_exact_to_diagonal'],
                amplitude_constant_response=fit['amplitude_constant_response'],amplitude_template_response=fit['amplitude_template_response'],fisher_condition_number=fit['fisher_condition_number'],
                median_diagonal_variance=fit['median_diagonal_variance']))
        except ValueError as error:fields.append(dict(patch_id=patch_id,available=False,reason=str(error)))
    samples={key:[] for key in fits_by_id};pre_samples={key:[] for key in fits_by_id};n=plan['realization_count_per_frame'];batch=plan['batch_size']
    seed=plan['seeds_by_parent'][ctx['group']['parent_id']]+100*index;rng=np.random.default_rng(seed);sd=np.sqrt(result['native_variance']);baseline=ctx['stack'].images[index];spotcheck=None;median_shifts=[];sample_mean_squares=[]
    for first in range(0,n,batch):
        count=min(batch,n-first);noise=rng.standard_normal((count,len(sd)))*sd[None,:];registered=(result['operator']@noise.T).T
        images=np.where(valid[None,:,:],baseline[None,:,:]+registered.reshape(count,*shape),np.nan);shift=np.nanmedian(images,axis=(1,2));delta=(images-shift[:,None,None]-baseline[None,:,:]).reshape(count,-1)
        median_shifts.extend(map(float,shift))
        for patch_id,fit in fits_by_id.items():
            samples[patch_id].extend(map(float,delta[:,fit['indices']]@fit['amplitude_weights']))
            pre_samples[patch_id].extend(map(float,registered[:,fit['indices']]@fit['amplitude_weights']))
        if index==0 and first==0:spotcheck=conditional_spotcheck(ctx,noise[0].reshape(result['native_shape']),registered[0].reshape(shape))
    for field in fields:
        if not field['available']:continue
        patch_id=field['patch_id'];values=np.asarray(samples[patch_id]);before=np.asarray(pre_samples[patch_id]);sample_variance=float(np.var(values,ddof=1));analytic=field['variance_exact'];df=len(values)-1
        interval=[df*sample_variance/float(chi2.ppf(.975,df)),df*sample_variance/float(chi2.ppf(.025,df))]
        field.update(realizations=len(values),mc_amplitude_mean=float(values.mean()),mc_variance=sample_variance,mc_sigma=float(np.sqrt(sample_variance)),analytic_sigma=float(np.sqrt(analytic)),
            mc_to_analytic_variance_ratio=sample_variance/analytic,mc_variance95_interval=interval,analytic_inside_mc95_interval=interval[0]<=analytic<=interval[1],
            variance_deviation_normalized_by_mc_SE=(sample_variance-analytic)/(analytic*np.sqrt(2/df)),
            maximum_affine_amplitude_change_from_median=float(np.max(abs(values-before))),
            mc_mean_in_analytic_sigma_units=float(values.mean()/np.sqrt(analytic)))
    ratio=result['linear_interpolated_variance'][valid]/result['variance_diagonal'][valid]
    return dict(parent_id=ctx['group']['parent_id'],detector=ctx['group']['detector'],epoch=index,physical_obsid=ctx['rows'][index]['obs_id'],source_sha256=ctx['rows'][index]['sha256'],seed=seed,
        realizations=n,native_shape=result['native_shape'],registered_shape=list(shape),has_sip=result['has_sip'],finite_registered_pixels=int(valid.sum()),operator_vs_immutable_prepare_max_abs=result['operator_vs_prepare_max_abs'],
        naive_linear_variance_to_squared_weight_variance=dict(min=float(ratio.min()),median=float(np.median(ratio)),max=float(ratio.max())),
        registered_neighbour_covariance=neighbour_stats(result),global_median_shift_abs_max=float(np.max(np.abs(median_shifts))),patches=fields,conditional_native_fits_spotcheck=spotcheck,
        conditional_diagonal_input_assumption=True,instrument_covariance_claimed=False,source_photon_noise_added=False,final_pixels_opened=False)


def main():
    plan_path=OWN/'plan.json'
    if digest(plan_path)!=PLAN_SHA:raise ValueError('Prospective variance study changed')
    plan=json.loads(plan_path.read_text());invocation=dict(created_utc=datetime.now(timezone.utc).isoformat(),plan_sha256=PLAN_SHA,
        source_sha256={str(path):digest(path) for path in [Path(__file__),OWN/'operators.py',OWN.parent/'native_overlay.py',OWN.parent/'run_validation.py',source_context.PACKAGE/'ml_inference/prepare.py']},
        versions={name:importlib.metadata.version(name) for name in ['numpy','scipy','astropy']},scope=plan['scope'],final_pixels_opened=False)
    with(OWN/'invocation.json').open('x') as handle:json.dump(invocation,handle,indent=2);handle.write('\n')
    started=time.monotonic();records=[]
    with(OWN/'results.jsonl').open('x') as stream:
        for group in plan['parents']:
            ctx=source_context.context(group)
            for index in range(len(ctx['rows'])):
                record=run_frame(plan,ctx,index);records.append(record);stream.write(json.dumps(record,allow_nan=False)+'\n');stream.flush()
                print(group['parent_id'],index,'patches',sum(patch['available'] for patch in record['patches']),'ratios',[round(patch['sigma_ratio_exact_to_diagonal'],3) for patch in record['patches'] if patch['available']],flush=True)
            del ctx
    patches=[patch for frame in records for patch in frame['patches'] if patch['available']];ratios=[patch['sigma_ratio_exact_to_diagonal'] for patch in patches]
    result=dict(schema_version=1,invocation=invocation,frame_count=len(records),independent_train_parents=3,conditional_draws_per_frame=plan['realization_count_per_frame'],total_conditional_frame_draws=sum(frame['realizations'] for frame in records),
        planned_patches=len(records)*len(plan['patches']),available_patches=len(patches),unavailable_patches=len(records)*len(plan['patches'])-len(patches),
        sigma_ratio_exact_to_diagonal=dict(min=min(ratios),median=float(np.median(ratios)),max=max(ratios)),
        maximum_mc_variance_deviation_normalized_by_SE=max(abs(patch['variance_deviation_normalized_by_mc_SE']) for patch in patches),mc95_intervals_containing_analytic=sum(patch['analytic_inside_mc95_interval'] for patch in patches),
        maximum_affine_amplitude_change_from_median=max(patch['maximum_affine_amplitude_change_from_median'] for patch in patches),
        maximum_explicit_operator_vs_prepare_error=max(frame['operator_vs_immutable_prepare_max_abs'] for frame in records),
        native_conditional_fits_spotchecks=[frame['conditional_native_fits_spotcheck'] for frame in records if frame['conditional_native_fits_spotcheck']],
        elapsed_seconds=time.monotonic()-started,source_photon_noise_added=False,variance_reference_updated=False,model_or_detector_called=False,final_pixels_opened=False,
        scope='Conditional independent native Gaussian uncertainty propagation only; not instrument covariance, physical source Poisson noise, real precision, training labels or model validation',
        temporal_limit='No leave-one-out residual temporal covariance is modeled. Neighbor covariance refers to registration before temporal background subtraction.')
    with(OWN/'summary.json').open('x') as handle:json.dump(result,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
