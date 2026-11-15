"""Known stationary-source artifact audit in declared native TRAIN fields.

Sources remain at fixed sky coordinates. Actual native ePSF changes, pixel
phase and production projection can produce apparent moving residuals. No
invented track velocity or registration jitter is supplied. Brightness support
and constant flux match the corresponding moving-source injection cache.
Unmodified native candidates remain unknown and are never negative labels.
"""
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from ml_inference.prepare import prepare
from ml_inference.detector import find_candidates
from training.evaluate_background import SETTINGS,read_native,project_response,add_projected_injection
from cache_native import matched,record


def run_group(item):
    group,root=item
    folder=Path('/tmp/spaceapps-v3-ranker/native-inputs')/(group+'-short-v2')
    metadata=json.loads((folder/'group.json').read_text())
    if metadata['split']!='train':raise ValueError('only native TRAIN fields accepted')
    downloads=json.loads((folder/'downloads.json').read_text())
    paths=[folder/Path(d['path']).name for d in downloads]
    for row,p in zip(downloads,paths):
        if hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('inputchecksum mismatch')
    request=dict(schema_version=1,analysis_id='v3-stationary-'+group,source=dict(kind='fits',observations=[dict(path=str(p),frame_id=p.stem,observation_id=p.stem) for p in paths],region=dict(right_ascension_deg=metadata['center'][0],declination_deg=metadata['center'][1],width_arcmin=6,height_arcmin=6)))
    stack=prepare(request);lookup={p.stem:p for p in paths};paths=[lookup[f['frame_id']] for f in stack.frames]
    native=[read_native(p,stack.grid,stack.images.shape[1:]) for p in paths]
    sigmas=np.asarray([1.4826*np.median(abs(v-np.median(v))) for im in stack.images for v in [im[np.isfinite(im)]]])
    rng=np.random.default_rng(1700000+int(group[-2:]));h,w=stack.images.shape[1:]
    configs=[dict(SETTINGS,psf_sigma=s) for s in [1.2,.8]]
    controls=[find_candidates(stack.images,stack.times,**cfg) for cfg in configs]
    fields=[[],[]];started=time.monotonic()
    for trial in range(60):
        origin=rng.uniform([8,8],[w-8,h-8]);positions=np.tile(origin,(len(stack.times),1))
        responses=np.asarray([project_response(n,stack.grid,origin)[0] for n in native])
        peak=float(np.median(np.max(responses,axis=(1,2))))
        for brightness in [3.,6.,12.,24.,48.]:
            flux=brightness*np.median(sigmas)/peak if peak>0 else 0
            images=add_projected_injection(stack.images,responses,flux)
            for im in images:im-=np.nanmedian(im)
            for j,cfg in enumerate(configs):
                preexisting=any(matched(controls[j],positions))
                tracks=find_candidates(images,stack.times,**cfg)
                truth=matched(tracks,positions)
                fields[j].append(dict(parent_id=group,partition='train',trajectory_id=trial,stationary_sky_truth=True,
                                      fixed_xy=origin.tolist(),brightness=brightness,flux=float(flux),
                                      attribution_eligible=not preexisting,preexisting_control_match=preexisting,
                                      truth_count=0,matches=[-1 if m and not preexisting else -2 for m in truth],**record(tracks)))
    outputs=[]
    for cfg,rows in zip(configs,fields):
        name=group+'-stationary-sigma'+str(cfg['psf_sigma'])+'.json.gz';path=Path(root)/name
        payload=dict(schema_version=1,partition='train',parent_id=group,artifact_identity='fixed sky stationary source; no imposed apparent motion',
                     detector_settings=cfg,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),input_sources=downloads,
                     known_negative_rows=sum(sum(m==-1 for m in f['matches']) for f in rows),unmatched_real_candidates_labeled=False,
                     limitations=['constant flux across changing passbands, same approximation as moving positives','no photon noise or variance update','all derivatives share one parent background'],fields=rows)
        with gzip.open(path,'wt') as handle:json.dump(payload,handle,allow_nan=False)
        outputs.append(dict(path=str(path),known_negative_rows=payload['known_negative_rows']))
    return dict(group=group,elapsed_seconds=time.monotonic()-started,outputs=outputs)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workers',type=int,default=3);p.add_argument('--output',default='/tmp/spaceapps-v3-ranker/native-artifacts');a=p.parse_args();Path(a.output).mkdir(parents=True,exist_ok=True)
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        tasks=[pool.submit(run_group,(f'train{i:02}',a.output)) for i in range(1,9)]
        for task in as_completed(tasks):print(json.dumps(task.result()),flush=True)
