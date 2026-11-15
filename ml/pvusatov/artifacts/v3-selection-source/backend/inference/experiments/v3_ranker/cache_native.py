"""Native development injection cache without assigning labels to real controls.

Only declared TRAIN/VALIDATION inputs are accepted. Never run on quarantined
final fields. Parent-field grouping survives every derivative injection.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from ml_inference.prepare import prepare
from ml_inference.detector import find_candidates,baseline_score,difference_frames,_detect_peaks
from training.evaluate_background import SETTINGS,read_native,project_response,add_projected_injection,trajectory


def matched(tracks,expected):
    return [bool(np.all(np.linalg.norm(np.asarray(t.positions_xy)-expected[list(t.epochs)],axis=1)<=1.5)) for t in tracks]


def record(tracks):
    return dict(features=[list(map(float,t.features())) for t in tracks],baseline=[float(baseline_score(t)) for t in tracks],
                candidate_epochs=[list(t.epochs) for t in tracks],candidate_positions_xy=[list(t.positions_xy) for t in tracks])


def run(args):
    folder=Path(args.input_dir)
    if 'final' in str(folder).lower() or 'quarant' in str(folder).lower():raise ValueError('quarantined inputs forbidden')
    started=time.monotonic()
    downloads=json.loads((folder/'downloads.json').read_text())
    paths=[folder/Path(row['path']).name for row in downloads]
    sources=[]
    for row,p in zip(downloads,paths):
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if digest!=row['sha256']:raise ValueError('input checksum mismatch')
        sources.append(dict(path=str(p),sha256=digest,url=row['url']))
    request=dict(schema_version=1,analysis_id='v3-'+args.parent_id,
                 source=dict(kind='fits',observations=[dict(path=str(p),frame_id=p.stem,observation_id=p.stem) for p in paths],
                             region=dict(right_ascension_deg=args.ra,declination_deg=args.dec,width_arcmin=6,height_arcmin=6)))
    stack=prepare(request)
    lookup={p.stem:p for p in paths};paths=[lookup[f['frame_id']] for f in stack.frames]
    native=[read_native(p,stack.grid,stack.images.shape[1:]) for p in paths]
    control=find_candidates(stack.images,stack.times,**SETTINGS)
    sigma=np.asarray([1.4826*np.median(abs(v-np.median(v))) for image in stack.images for v in [image[np.isfinite(image)]]])
    if not np.all(sigma>0):raise ValueError('nonpositive native background scale')
    rng=np.random.default_rng(args.seed);fields=[]
    h,w=stack.images.shape[1:]
    for trajectory_id in range(args.trajectories):
        speed=[1.,4.,10.,25.,50.][trajectory_id%5]
        origin=rng.uniform([8,8],[w-8,h-8]);angle=rng.uniform(0,2*np.pi)
        velocity=speed*np.asarray([np.cos(angle),np.sin(angle)])
        positions=trajectory(origin,velocity,stack.times)
        responses=[];epsf=[];coverage=0
        for n,position,image in zip(native,positions,stack.images):
            response,meta=project_response(n,stack.grid,position);responses.append(response);epsf.append(meta)
            x,y=np.rint(position).astype(int)
            coverage+=int(0<=x<w and 0<=y<h and np.isfinite(image[y,x]))
        responses=np.asarray(responses)
        typical_peak=float(np.median(np.max(responses,axis=(1,2))))
        preexisting=any(matched(control,positions))
        for brightness in [3.,6.,12.,24.,48.]:
            flux=brightness*float(np.median(sigma))/typical_peak if typical_peak>0 else 0
            injected=add_projected_injection(stack.images,responses,flux)
            for image in injected:image-=np.nanmedian(image)
            tracks=find_candidates(injected,stack.times,**SETTINGS)
            matches=matched(tracks,positions)
            peaks=[len(_detect_peaks(d,np.isfinite(d),1.2,4,100,.8)) for d in difference_frames(injected,True)]
            fields.append(dict(parent_id=args.parent_id,partition=args.partition,seed=args.seed,trajectory_id=trajectory_id,
                               speed_px_hour=speed,brightness=brightness,origin_xy=origin.tolist(),velocity_xy_hour=velocity.tolist(),
                               expected_xy=positions.tolist(),usable_center_epochs=coverage,truth_count=1,
                               attribution_eligible=not preexisting,preexisting_control_match=preexisting,
                               injected_flux=flux,epsf=epsf,matches=[0 if m else -2 for m in matches],
                               peaks_per_epoch=peaks,peak_cap_reached=any(p>=100 for p in peaks),**record(tracks)))
        if trajectory_id%10==0 or trajectory_id==args.trajectories-1:
            print(json.dumps(dict(parent_id=args.parent_id,trials=len(fields),positives=sum(sum(m>=0 for m in f['matches']) for f in fields),elapsed_seconds=round(time.monotonic()-started,2))),flush=True)
    sources_code=[Path(__file__),Path('backend/inference/experiments/v3_ranker/protocol.py'),Path('backend/inference/training/evaluate_background.py'),Path('backend/inference/ml_inference/prepare.py'),Path('backend/inference/ml_inference/detector.py')]
    payload=dict(schema_version=1,partition=args.partition,parent_id=args.parent_id,independent_parent_fields=1,
                 all_derivatives_correlated=True,real_unknown_candidates_unlabeled=True,input_sources=sources,
                 center_deg=[args.ra,args.dec],registered_shape=list(stack.images.shape),times_hours=stack.times.tolist(),
                 finite_fraction_per_epoch=np.isfinite(stack.images).mean(axis=(1,2)).tolist(),warnings=stack.warnings,
                 frames=stack.frames,control=record(control),control_labels='unknown',detector_settings=SETTINGS,
                 limitations=['fixed flux across passbands','no added photon noise or variance update','sources projected after registration','all derivatives share one real parent'],
                 source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources_code},fields=fields,
                 elapsed_seconds=time.monotonic()-started)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(output,'wt') as handle:json.dump(payload,handle,allow_nan=False)
    print('CACHE '+str(output)+' '+hashlib.sha256(output.read_bytes()).hexdigest(),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir',required=True);p.add_argument('--parent-id',required=True)
    p.add_argument('--partition',required=True,choices=['train','validation'])
    p.add_argument('--ra',required=True,type=float);p.add_argument('--dec',required=True,type=float)
    p.add_argument('--seed',required=True,type=int);p.add_argument('--trajectories',type=int,default=60)
    p.add_argument('--output',required=True)
    run(p.parse_args())
