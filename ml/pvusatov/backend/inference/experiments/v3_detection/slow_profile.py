"""Predeclared slow-motion engineering diagnostic on allowed augmented parents."""
import argparse,gzip,hashlib,json,resource,time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter,map_coordinates
from ml_inference.prepare import prepare
from ml_inference.detector import find_candidates,difference_frames,DetectionLimitError
from ml_inference.model import load_ranker
from training.evaluate_background import SETTINGS,read_native,project_response,add_projected_injection
BASE=Path(__file__).resolve().parents[2]
PARENTS=[('validation01',30.,45.,1800001),('validation02',165.,5.,1800002),('validation03',300.,-20.,1800003)]
SETTINGS_SLOW={**SETTINGS,'min_speed':.005}

def matched(tracks,expected):
    return [bool(np.all(np.linalg.norm(np.asarray(t.positions_xy)-expected[list(t.epochs)],axis=1)<=1.5))for t in tracks]

def attenuation(response,valid,positions,sigma):
    masked=np.where(valid,response,np.nan);residual=difference_frames(masked,True);ratios=[]
    for original,diff,(x,y)in zip(masked,residual,positions):
        samples=[]
        for image in [original,diff]:
            good=np.isfinite(image);sup=gaussian_filter(good.astype(float),sigma);sm=gaussian_filter(np.where(good,image,0),sigma)
            sm=np.divide(sm,sup,out=np.zeros_like(sm),where=sup>0)
            samples.append(float(map_coordinates(sm,[[y],[x]],order=1,cval=np.nan)[0]))
        ratios.append(samples[1]/samples[0]if np.isfinite(samples).all()and samples[0]>0 else None)
    return ratios

def one(spec):
    group,ra,dec,seed=spec;folder=Path('/tmp/spaceapps-v3-native-data/development/variants')/(group+'-augmented')
    downloads=json.loads((folder/'downloads.json').read_text());paths=[folder/Path(r['path']).name for r in downloads]
    for row,path in zip(downloads,paths):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('source checksum mismatch')
    request=dict(schema_version=1,analysis_id='v3-slow-'+group,source=dict(kind='fits',observations=[dict(path=str(p),frame_id=p.stem,observation_id=p.stem)for p in paths],region=dict(right_ascension_deg=ra,declination_deg=dec,width_arcmin=6,height_arcmin=6)))
    stack=prepare(request);lookup={p.stem:p for p in paths};paths=[lookup[f['frame_id']]for f in stack.frames];native=[read_native(p,stack.grid,stack.images.shape[1:])for p in paths];ranker=load_ranker(BASE/'models');rng=np.random.default_rng(seed);fields=[];controls={};started=time.monotonic()
    for sigma in [1.2,.8]:
        try:controls[str(sigma)]=find_candidates(stack.images,stack.times,**{**SETTINGS_SLOW,'psf_sigma':sigma})
        except DetectionLimitError as exc:raise ValueError(f'control search failed {group}: {exc}')from exc
    noise=np.array([1.4826*np.median(abs(v-np.median(v)))for image in stack.images for v in [image[np.isfinite(image)]]]);h,w=stack.images.shape[1:]
    for speed in [.01,.03,.1,.3,1.]:
        for direction_id in range(6):
            origin=rng.uniform([8,8],[w-8,h-8]);angle=rng.uniform(0,2*np.pi);velocity=speed*np.array([np.cos(angle),np.sin(angle)]);positions=origin+stack.times[:,None]*velocity
            response=np.asarray([project_response(n,stack.grid,xy)[0]for n,xy in zip(native,positions)]);peak=float(np.median(np.max(response,axis=(1,2))));coverage=0
            for image,(x,y)in zip(stack.images,np.rint(positions).astype(int)):
                coverage+=int(0<=x<w and 0<=y<h and np.isfinite(image[y,x]))
            att={str(s):attenuation(response,np.isfinite(stack.images),positions,s)for s in [1.2,.8]}
            for brightness in [3.,6.,12.,24.,48.]:
                flux=brightness*float(np.median(noise))/peak if peak>0 else 0;injected=add_projected_injection(stack.images,response,flux)
                for image in injected:image-=np.nanmedian(image)
                methods={}
                for sigma in [1.2,.8]:
                    name=str(sigma);start=time.perf_counter();cpu=time.process_time()
                    try:tracks=find_candidates(injected,stack.times,**{**SETTINGS_SLOW,'psf_sigma':sigma})
                    except DetectionLimitError as exc:methods[name]=dict(error=str(exc));continue
                    features=np.asarray([t.features()for t in tracks],np.float32).reshape(-1,6);scores=ranker.score(features);matches=matched(tracks,positions);order=np.argsort(-scores,kind='stable')
                    methods[name]=dict(candidates=len(tracks),detected=any(matches),at_1=any(matches[i]for i in order[:1]),at_3=any(matches[i]for i in order[:3]),preexisting_control_match=any(matched(controls[name],positions)),features=features.tolist(),matches=[0 if m else-2 for m in matches],scores=scores.tolist(),wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
                fields.append(dict(parent_id=group,seed=seed,speed_px_hour=speed,direction_id=direction_id,brightness=brightness,origin_xy=origin.tolist(),velocity_xy_hour=velocity.tolist(),expected_xy=positions.tolist(),total_displacement_px=float(np.linalg.norm(positions[-1]-positions[0])),usable_center_epochs=coverage,isolated_source_filtered_attenuation=att,methods=methods))
        print(json.dumps(dict(parent=group,speed=speed,trials=len(fields),elapsed_seconds=time.monotonic()-started)),flush=True)
    report=dict(designation='predeclared slow-motion engineering development profile; no distant-body detection claim',parent_id=group,seed=seed,all_derivatives_correlated=True,settings=SETTINGS_SLOW,compared_psf_sigma=[1.2,.8],shape=list(stack.images.shape),times_hours=stack.times.tolist(),frames=stack.frames,input_sources=downloads,warnings=stack.warnings,finite_fraction_per_epoch=np.isfinite(stack.images).mean(axis=(1,2)).tolist(),control_candidates={k:len(v)for k,v in controls.items()},control_features={k:[list(map(float,t.features()))for t in v]for k,v in controls.items()},fields=fields,model_sha256=ranker.metadata['sha256'],source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),elapsed_seconds=time.monotonic()-started)
    output=Path('/tmp/spaceapps-v3-detection')/f'slow-{group}.json.gz'
    with gzip.open(output,'wt')as s:json.dump(report,s,allow_nan=False)
    return str(output)

def main():
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,default=2);a=p.parse_args()
    with ProcessPoolExecutor(max_workers=a.workers)as pool:
        for path in pool.map(one,PARENTS):print('REPORT '+path,flush=True)
if __name__=='__main__':main()
