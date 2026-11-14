"""Narrow-filter twins on exactly cached expanded development injections.

No new positions, flux, or randomness are generated. Truth only labels results.
"""
import argparse,gzip,hashlib,json,time,resource
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from ml_inference.prepare import prepare
from ml_inference.detector import find_candidates,baseline_score,DetectionLimitError,difference_frames,_detect_peaks
from training.evaluate_background import SETTINGS,read_native,project_response,add_projected_injection

BASE=Path(__file__).resolve().parents[2]

def record(tracks,expected=None):
    data=dict(features=[list(map(float,t.features()))for t in tracks],baseline=[float(baseline_score(t))for t in tracks],candidate_epochs=[list(t.epochs)for t in tracks],candidate_positions_xy=[list(t.positions_xy)for t in tracks])
    if expected is not None:
        matched=[];spans=[];geometry=[]
        for index,t in enumerate(tracks):
            xy=np.asarray(t.positions_xy);truth=expected[list(t.epochs)]
            offsets=np.linalg.norm(xy-truth,axis=1);is_match=bool(np.all(offsets<=1.5))
            matched.append(0 if is_match else-2)
            span=float(np.max(np.linalg.norm(truth[:,None,:]-truth[None,:,:],axis=-1)))
            spans.append(span)
            if is_match:
                geometry.append(dict(candidate_index=index,epochs=list(t.epochs),true_displacement_px=span,
                    measured_displacement_px=float(np.max(np.linalg.norm(xy[:,None,:]-xy[None,:,:],axis=-1))),
                    max_offset_px=float(offsets.max())))
        data.update(matches=matched,matched_geometry=geometry,expected_span_among_candidate_epochs_px=spans)
    return data

def one(cache_path):
    cache_path=Path(cache_path)
    if any(token in str(cache_path).lower()for token in ['final','quarant']):raise ValueError('development caches only')
    with gzip.open(cache_path,'rt')as s:cache=json.load(s)
    paths=[Path(r['path'])for r in cache['input_sources']]
    for row,path in zip(cache['input_sources'],paths):
        if any(token in str(path).lower()for token in ['final','quarant']):raise ValueError('development pixels only')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('input checksum mismatch')
    center=cache['center_deg'];region=dict(right_ascension_deg=center[0],declination_deg=center[1],width_arcmin=6,height_arcmin=6)
    request=dict(schema_version=1,analysis_id='v3-expanded-narrow-'+cache['parent_id'],source=dict(kind='fits',observations=[dict(path=str(p),frame_id=p.stem,observation_id=p.stem)for p in paths],region=region))
    stack=prepare(request);lookup={p.stem:p for p in paths};native=[read_native(lookup[f['frame_id']],stack.grid,stack.images.shape[1:])for f in stack.frames];started=time.monotonic()
    settings={**SETTINGS,**cache.get('detector_settings',{}),'psf_sigma':.8}
    # Source cache chooses the profile; bounds are copied exactly, not inferred from names.
    if settings['min_speed']not in [.005,.5]:raise ValueError('requires declared slow/default profile')
    controls=find_candidates(stack.images,stack.times,**settings);fields=[];responses={}
    for index,source_field in enumerate(cache['fields']):
        expected=np.asarray(source_field['expected_xy']);tid=source_field.get('trajectory_id',index)
        copied={k:v for k,v in source_field.items()if k not in ['features','matches','baseline',
            'candidate_epochs','candidate_positions_xy','matched_geometry','expected_span_among_candidate_epochs_px',
            'peaks_per_epoch','peak_cap_reached','attribution_eligible','preexisting_control_match',
            'common_attribution_eligible_sigma12_profiles','detector_error']}
        preexisting=any(m==0 for m in record(controls,expected)['matches'])
        key=(str(tid),tuple(expected.ravel()))
        if key not in responses:responses[key]=np.asarray([project_response(n,stack.grid,xy)[0]for n,xy in zip(native,expected)])
        images=add_projected_injection(stack.images,responses[key],source_field['injected_flux'])
        for image in images:image-=np.nanmedian(image)
        detector_started=time.perf_counter();detector_cpu=time.process_time()
        try:tracks=find_candidates(images,stack.times,**settings)
        except DetectionLimitError as exc:
            fields.append({**copied,**record([],expected),'detector_error':str(exc),
                'attribution_eligible':not preexisting,'preexisting_control_match':preexisting});continue
        detector_wall=time.perf_counter()-detector_started;detector_cpu=time.process_time()-detector_cpu
        result=record(tracks,expected);result.update(detector_wall_seconds=detector_wall,detector_cpu_seconds=detector_cpu,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024);peaks=[len(_detect_peaks(d,np.isfinite(d),.8,settings['min_snr'],settings['max_peaks'],settings['min_support']))for d in difference_frames(images,True)]
        fields.append({**copied,**result,'attribution_eligible':not preexisting,'preexisting_control_match':preexisting,'peaks_per_epoch':peaks,'peak_cap_reached':any(p>=settings['max_peaks']for p in peaks)})
        if(index+1)%90==0:print(json.dumps(dict(parent=cache['parent_id'],min_speed=settings['min_speed'],trials=index+1,elapsed_seconds=time.monotonic()-started)),flush=True)
    output=Path('/tmp/spaceapps-v3-detection')/(cache_path.name.removesuffix('.json.gz')+'-sigma08.json.gz')
    payload={**{k:v for k,v in cache.items()if k not in ['fields','control','detector_settings','source_sha256','elapsed_seconds']},'fields':fields,'control':record(controls),'control_labels':'unknown','detector_settings':settings,'source_cache':str(cache_path),'source_cache_sha256':hashlib.sha256(cache_path.read_bytes()).hexdigest(),'source_sha256':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path(__file__),BASE/'ml_inference/detector.py',BASE/'ml_inference/prepare.py',BASE/'training/evaluate_background.py']},'elapsed_seconds':time.monotonic()-started}
    with gzip.open(output,'wt')as s:json.dump(payload,s,allow_nan=False)
    return dict(path=str(output),parent_id=cache['parent_id'],min_speed=settings['min_speed'],fields=len(fields),sha256=hashlib.sha256(output.read_bytes()).hexdigest())

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True,action='append');p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    with ProcessPoolExecutor(max_workers=a.workers)as pool:
        for result in pool.map(one,a.cache):print(json.dumps(result),flush=True)
if __name__=='__main__':main()
