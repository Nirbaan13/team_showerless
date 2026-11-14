"""Paired development-only native injection detector ablation from frozen trial caches."""
import argparse,gzip,hashlib,json,resource,time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from ml_inference.prepare import prepare
from ml_inference.detector import find_candidates,baseline_score,DetectionLimitError,difference_frames,_detect_peaks
from ml_inference.model import load_ranker
from training.evaluate_background import SETTINGS,read_native,project_response,add_projected_injection

BASE=Path(__file__).resolve().parents[2]
CONFIGS=[(1.2,4.),(1.2,3.),(1.2,2.5),(1.2,2.),(.8,4.),(.8,3.),(.6,4.),(.6,3.),(1.6,4.),(1.6,3.)]

def matched(tracks,expected):
    return [bool(np.all(np.linalg.norm(np.asarray(t.positions_xy)-expected[list(t.epochs)],axis=1)<=1.5))for t in tracks]

def one(cache_path):
    cache_path=Path(cache_path)
    if 'final'in str(cache_path).lower()or 'quarant'in str(cache_path).lower():raise ValueError('development only')
    with gzip.open(cache_path,'rt')as stream:cache=json.load(stream)
    sources=cache['input_sources'];paths=[Path(r['path'])for r in sources]
    if any(not any(version in str(p)for version in ['short-v1','short-v2'])for p in paths):raise ValueError('requires declared short-v1/short-v2 snapshot')
    for row,path in zip(sources,paths):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('input mismatch')
    request=dict(schema_version=1,analysis_id='v3-detector-'+cache['parent_id'],source=dict(kind='fits',observations=[dict(path=str(p),frame_id=p.stem,observation_id=p.stem)for p in paths],region=dict(right_ascension_deg=cache['center_deg'][0],declination_deg=cache['center_deg'][1],width_arcmin=6,height_arcmin=6)))
    stack=prepare(request);lookup={p.stem:p for p in paths};paths=[lookup[f['frame_id']]for f in stack.frames]
    native=[read_native(p,stack.grid,stack.images.shape[1:])for p in paths];ranker=load_ranker(BASE/'models');controls={};fields=[]
    for sigma,snr in CONFIGS:
        name=f'sigma{sigma}_snr{snr}';tracks=find_candidates(stack.images,stack.times,**{**SETTINGS,'psf_sigma':sigma,'min_snr':snr});controls[name]=tracks
    responses_by_trajectory={};started=time.monotonic()
    for index,field in enumerate(cache['fields']):
        expected=np.asarray(field['expected_xy']);tid=field['trajectory_id']
        if tid not in responses_by_trajectory:responses_by_trajectory[tid]=np.asarray([project_response(n,stack.grid,position)[0]for n,position in zip(native,expected)])
        injected=add_projected_injection(stack.images,responses_by_trajectory[tid],field['injected_flux'])
        for image in injected:image-=np.nanmedian(image)
        methods={}
        residuals=difference_frames(injected,True)
        for sigma,snr in CONFIGS:
            name=f'sigma{sigma}_snr{snr}';start=time.perf_counter();cpu=time.process_time()
            try:tracks=find_candidates(injected,stack.times,**{**SETTINGS,'psf_sigma':sigma,'min_snr':snr})
            except DetectionLimitError as e:methods[name]=dict(error=str(e));continue
            features=[list(map(float,t.features()))for t in tracks];scores=ranker.score(np.asarray(features,np.float32).reshape(-1,6));matches=matched(tracks,expected);order=np.argsort(-scores,kind='stable')
            peaks=[len(_detect_peaks(d,np.isfinite(d),sigma,snr,100,.8))for d in residuals]
            methods[name]=dict(features=features,matches=[0 if m else-2 for m in matches],baseline=[float(baseline_score(t))for t in tracks],scores=scores.tolist(),candidates=len(tracks),detected=any(matches),at_1=any(matches[i]for i in order[:1]),at_3=any(matches[i]for i in order[:3]),preexisting_control_match=any(matched(controls[name],expected)),peaks_per_epoch=peaks,peak_cap_reached=any(p>=100 for p in peaks),wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
        fields.append({**{k:field[k]for k in ['parent_id','partition','seed','trajectory_id','speed_px_hour','brightness','expected_xy','usable_center_epochs','injected_flux']},'truth_count':1,'methods':methods})
        if(index+1)%50==0:print(json.dumps(dict(parent=cache['parent_id'],trials=index+1,elapsed=time.monotonic()-started)),flush=True)
    output=Path('/tmp/spaceapps-v3-detection')/f'{cache_path.name.removesuffix(".json.gz")}-scan.json.gz'
    report=dict(designation='paired v3 development only',parent_id=cache['parent_id'],partition=cache['partition'],source_cache=str(cache_path),source_cache_sha256=hashlib.sha256(cache_path.read_bytes()).hexdigest(),input_sources=sources,center_deg=cache['center_deg'],times_hours=stack.times.tolist(),shape=list(stack.images.shape),control_candidates={k:len(v)for k,v in controls.items()},control_features={k:[list(map(float,t.features()))for t in v]for k,v in controls.items()},fields=fields,elapsed_seconds=time.monotonic()-started)
    with gzip.open(output,'wt')as stream:json.dump(report,stream,allow_nan=False)
    return dict(path=str(output),parent_id=cache['parent_id'],summary=summary(fields))

def summary(fields):
    out={}
    for sigma,snr in CONFIGS:
        name=f'sigma{sigma}_snr{snr}';valid=[f['methods'][name]for f in fields if 'error'not in f['methods'][name]]
        eligible=[m for m in valid if not m['preexisting_control_match']]
        out[name]=dict(trials=len(fields),complete_trials=len(valid),attribution_eligible=len(eligible),raw_detected=sum(m['detected']for m in valid),**{k:sum(m[k]for m in eligible)for k in ['detected','at_1','at_3','candidates']},peak_cap_trials=sum(m['peak_cap_reached']for m in valid),wall_p50=float(np.median([m['wall_seconds']for m in valid])),wall_p95=float(np.quantile([m['wall_seconds']for m in valid],.95)),max_rss_mib=max(m['rss_mib']for m in valid))
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',action='append',required=True);p.add_argument('--workers',type=int,default=6);p.add_argument('--output',required=True);a=p.parse_args();results=[]
    with ProcessPoolExecutor(max_workers=a.workers)as pool:
        for result in pool.map(one,a.cache):results.append(result);print(json.dumps(result),flush=True)
    Path(a.output).write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':main()
