"""Predeclared expanded native validation, paired default/slow profiles.

Six new independent parents; 270 correlated derivatives each. Nine speeds,
six directions, five brightnesses. Positions are never moved into coverage.
No final pixels are read and no labels are assigned to unknown real tracks.
"""
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import time
import numpy as np
from ml_inference.prepare import prepare
from ml_inference.detector import find_candidates,difference_frames,_detect_peaks
from training.evaluate_background import SETTINGS,read_native,project_response,add_projected_injection,trajectory
from cache_native import matched,record

SPEEDS=[.01,.03,.1,.3,1.,4.,10.,25.,50.]

def one(group):
    source=Path('/tmp/spaceapps-v3-native-data/expansion-v2/development')/(group+'-augmented')
    folder=Path('/tmp/spaceapps-v3-ranker/native-inputs')/(group+'-expanded-v1');folder.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((source/'group.json').read_text());downloads=json.loads((source/'downloads.json').read_text())
    if metadata['split']!='validation':raise ValueError('only validation development allowed')
    for row in downloads:
        p=source/Path(row['path']).name;target=folder/p.name;shutil.copy2(p,target)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('input checksum mismatch')
    for name in ['group.json','downloads.json']:shutil.copy2(source/name,folder/name)
    paths=[folder/Path(row['path']).name for row in downloads]
    request=dict(schema_version=1,analysis_id='v3-expanded-'+group,source=dict(kind='fits',observations=[dict(path=str(p),frame_id=p.stem,observation_id=p.stem) for p in paths],region=dict(right_ascension_deg=metadata['center'][0],declination_deg=metadata['center'][1],width_arcmin=6,height_arcmin=6)))
    stack=prepare(request);lookup={p.stem:p for p in paths};paths=[lookup[f['frame_id']] for f in stack.frames]
    native=[read_native(p,stack.grid,stack.images.shape[1:]) for p in paths]
    sigmas=np.asarray([1.4826*np.median(abs(v-np.median(v))) for im in stack.images for v in [im[np.isfinite(im)]]])
    configs={label:dict(SETTINGS,psf_sigma=1.2,min_speed=speed) for label,speed in [('default',.5),('slow',.005)]}
    control={label:find_candidates(stack.images,stack.times,**cfg) for label,cfg in configs.items()}
    rows={label:[] for label in configs};started=time.monotonic();h,w=stack.images.shape[1:]
    seed=1610000+int(group[-2:]);rng=np.random.default_rng(seed)
    for speed in SPEEDS:
        for direction in range(6):
            origin=rng.uniform([8,8],[w-8,h-8]);angle=rng.uniform(0,2*np.pi);velocity=speed*np.asarray([np.cos(angle),np.sin(angle)])
            positions=trajectory(origin,velocity,stack.times)
            responses=[];usable=[];epsf=[]
            for n,position,image in zip(native,positions,stack.images):
                response,meta=project_response(n,stack.grid,position);responses.append(response);epsf.append(meta)
                x,y=np.rint(position).astype(int);usable.append(bool(0<=x<w and 0<=y<h and np.isfinite(image[y,x])))
            responses=np.asarray(responses);peaks=np.max(responses,axis=(1,2));covered=peaks[np.asarray(usable)&(peaks>0)]
            # Brightness normalization never turns off an in-coverage early source merely
            # because most late epochs have left the field. No position is recentered.
            supported=covered if len(covered) else peaks[peaks>0]
            if not len(supported):
                fallback=[project_response(n,stack.grid,np.asarray([w/2,h/2]))[0].max() for n in native]
                supported=np.asarray([p for p in fallback if p>0])
            typical=float(np.median(supported)) if len(supported) else 1.
            valid_positions=positions[np.asarray(usable)]
            span=float(np.linalg.norm(valid_positions[-1]-valid_positions[0])) if len(valid_positions)>=2 else 0.
            preexisting={label:any(matched(tracks,positions)) for label,tracks in control.items()}
            for brightness in [3.,6.,12.,24.,48.]:
                flux=brightness*float(np.median(sigmas))/typical
                images=add_projected_injection(stack.images,responses,flux)
                for im in images:im-=np.nanmedian(im)
                for label,cfg in configs.items():
                    tracks=find_candidates(images,stack.times,**cfg);matches=matched(tracks,positions)
                    residuals=difference_frames(images,True)
                    peaks_epoch=[len(_detect_peaks(d,np.isfinite(d),cfg['psf_sigma'],cfg['min_snr'],100,.8)) for d in residuals]
                    matched_geometry=[]
                    for i,t in enumerate(tracks):
                        if not matches[i]:continue
                        epochs=list(t.epochs);true_span=float(np.linalg.norm(positions[epochs[-1]]-positions[epochs[0]]))
                        measured_span=float(np.linalg.norm(np.asarray(t.positions_xy[-1])-np.asarray(t.positions_xy[0])))
                        matched_geometry.append(dict(candidate_index=i,epochs=epochs,true_displacement_px=true_span,measured_displacement_px=measured_span,max_offset_px=float(np.max(np.linalg.norm(np.asarray(t.positions_xy)-positions[epochs],axis=1)))))
                    rows[label].append(dict(parent_id=group,partition='validation',seed=seed,trajectory_id=f'{speed:g}-{direction}',speed_px_hour=speed,brightness=brightness,
                        origin_xy=origin.tolist(),velocity_xy_hour=velocity.tolist(),expected_xy=positions.tolist(),injected_flux=flux,epsf=epsf,
                        usable_center_epochs=sum(usable),center_usable_flags=usable,expected_covered_displacement_px=span,independent_geometry=dict(finite_center_epochs=sum(usable),covered_true_displacement_px=span),
                        truth_count=1,attribution_eligible=not preexisting[label],common_attribution_eligible_sigma12_profiles=not any(preexisting.values()),preexisting_control_match=preexisting[label],
                        matches=[0 if m else -2 for m in matches],matched_geometry=matched_geometry,peaks_per_epoch=peaks_epoch,peak_cap_reached=any(n>=100 for n in peaks_epoch),**record(tracks)))
            print(json.dumps(dict(group=group,speed=speed,direction=direction,trials=len(rows['default']),elapsed_seconds=round(time.monotonic()-started,1))),flush=True)
    outputs=[]
    for label,cfg in configs.items():
        output=Path('/tmp/spaceapps-v3-ranker')/(f'native-{group}-expanded-v1-sigma12-{label}.json.gz')
        payload=dict(schema_version=1,designation='expanded validation DEVELOPMENT; final unopened',parent_id=group,partition='validation',seed=seed,
            detector_settings=cfg,input_sources=downloads,center_deg=metadata['center'],times_hours=stack.times.tolist(),registered_shape=list(stack.images.shape),
            finite_fraction_per_epoch=np.isfinite(stack.images).mean(axis=(1,2)).tolist(),warnings=stack.warnings,control=record(control[label]),control_labels='unknown',
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),profile=label,
            brightness_normalization='median projected response peak at finite covered centers; fallback to any positive support, then field-center response if source outside every epoch',
            injection_matrix=dict(speeds_px_hour=SPEEDS,directions_per_speed=6,brightness=[3,6,12,24,48],planned=270,recenter_into_coverage=False),
            fields=rows[label],elapsed_seconds=time.monotonic()-started)
        with gzip.open(output,'wt') as f:json.dump(payload,f,allow_nan=False)
        outputs.append(str(output))
    return dict(group=group,outputs=outputs,elapsed_seconds=time.monotonic()-started)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--groups',nargs='+',default=[f'validation{i:02}' for i in range(6,12)]);p.add_argument('--workers',type=int,default=3);a=p.parse_args()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for task in as_completed([pool.submit(one,g) for g in a.groups]):print('COMPLETE '+json.dumps(task.result()),flush=True)
