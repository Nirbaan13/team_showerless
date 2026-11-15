"""Paired DEVELOPMENT gate ablation; synthetic-known labels/native UNKNOWN controls."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import resource
import time
import numpy as np
from ml_inference.prepare import prepare
from ml_inference.model import load_ranker
from training.simulate_v2 import simulate,load_bank
from training.evaluate_background import read_native,project_response,add_projected_injection
from ml.pvusatov.experiments.v4.detection.psf_gate import ProposalContext

REPO=Path(__file__).resolve().parents[5];INF=REPO/'ml/pvusatov/backend/inference'
GATES=(None,2.,3.,4.);CONTEXT={}


def _ranker():
    if 'ranker'not in CONTEXT:CONTEXT['ranker']=load_ranker(REPO/'ml/pvusatov/releases/v3/model')
    return CONTEXT['ranker']


def labels(tracks,truth,native):
    result=[]
    for t in tracks:
        distances=[np.linalg.norm(np.asarray(t.positions_xy)-p[list(t.epochs)],axis=1)for p in truth]
        eligible=[i for i,d in enumerate(distances)if np.all(d<=1.5)]
        result.append(min(eligible,key=lambda i:float(np.mean(distances[i])))if eligible else(-2 if native else-1))
    return result


def _native(path):
    if 'final'in str(path).lower()or'quarant'in str(path).lower():raise ValueError('FINAL inputs forbidden')
    if path not in CONTEXT:
        with gzip.open(path,'rt')as s:c=json.load(s)
        if c['partition']!='train':raise ValueError('first native pilot is TRAIN only')
        obs=[];paths=[]
        for i,r in enumerate(c['input_sources']):
            p=Path(r['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'];paths.append(p)
            obs.append(dict(path=str(p),frame_id=p.stem,sha256=r['sha256']))
        ra,dec=c['center_deg'];stack=prepare(dict(schema_version=1,analysis_id='v4pilot-'+c['parent_id'],
            source=dict(kind='fits',observations=obs,region=dict(right_ascension_deg=ra,declination_deg=dec,width_arcmin=6,height_arcmin=6))))
        bystem={p.stem:p for p in paths};paths=[bystem[f['frame_id']]for f in stack.frames]
        native=[read_native(p,stack.grid,stack.images.shape[1:])for p in paths]
        control=ProposalContext(stack.images,stack.times);controls={str(g):control.detect(g)for g in GATES}
        CONTEXT[path]=dict(cache=c,stack=stack,native=native,controls=controls,responses={})
    return CONTEXT[path]


def _one(task):
    if task[0]=='synthetic':
        seed=task[1]
        if not 3801000<=seed<3801200:raise ValueError('only declared DEVELOPMENT seed range')
        if 'bank'not in CONTEXT:CONTEXT['bank']=load_bank(INF/'training/calibration/instrument-epsf-bank.npz')
        images,times,truth,mode,metadata=simulate(seed,CONTEXT['bank'],extended=seed%3==0,varying_psf=True)
        identity=dict(kind='synthetic',seed=seed,independent_parent=str(seed),mode=mode,truth_count=len(truth))
        controls=None;native=False
    else:
        path,index=task[1:];ctx=_native(path);f=ctx['cache']['fields'][index];stack=ctx['stack'];truth=[np.asarray(f['expected_xy'])]
        key=json.dumps(f['expected_xy']);responses=ctx['responses'].get(key)
        if responses is None:
            responses=np.asarray([project_response(n,stack.grid,p)[0]for n,p in zip(ctx['native'],truth[0])]);ctx['responses'][key]=responses
        images=add_projected_injection(stack.images,responses,f['injected_flux'])
        for image in images:image-=np.nanmedian(image)
        times=stack.times;identity=dict(kind='native',independent_parent=f['parent_id'],field_index=index,
            trajectory_id=f['trajectory_id'],brightness=f['brightness'],truth_count=1,usable_center_epochs=f['usable_center_epochs'])
        controls=ctx['controls'];native=True
    context=ProposalContext(images,times);methods={};ranker=_ranker()
    for gate in GATES:
        result=context.detect(gate);tracks=result.pop('tracks');matched=labels(tracks,truth,native)
        features=np.asarray([t.features()for t in tracks],np.float32).reshape(-1,6);scores=ranker.score(features);order=np.argsort(-scores,kind='stable')
        count=lambda indexes:len({matched[i]for i in indexes if matched[i]>=0})
        preexisting=bool(controls is not None and any(m>=0 for m in labels(controls[str(gate)]['tracks'],truth,True)))
        methods[str(gate)]={**result,'candidate_rows':len(tracks),'detected':count(range(len(tracks))),
            'c13_top1':count(order[:1]),'c13_top3':count(order[:3]),'heuristic_top1':count(range(min(1,len(tracks)))),
            'heuristic_top3':count(range(min(3,len(tracks)))),'attribution_eligible':not preexisting,
            'known_synthetic_unmatched_rows':sum(m<0 for m in matched)if not native else None,
            'unknown_control_rows':len(controls[str(gate)]['tracks'])if controls is not None else None}
    return {**identity,'methods':methods,'rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}


def summarize(fields):
    result={}
    for kind in ('synthetic','native'):
        fs=[f for f in fields if f['kind']==kind];methods={}
        for gate in GATES:
            key=str(gate);rows=[f['methods'][key]for f in fs];base=[f['methods']['None']for f in fs]
            common=[i for i,(a,b)in enumerate(zip(base,rows))if a['attribution_eligible']and b['attribution_eligible']]
            counts={metric:sum(r[metric]for r in rows)for metric in ['candidate_rows','detected','c13_top1','c13_top3','heuristic_top1','heuristic_top3']}
            byparent={}
            for f,row in zip(fs,rows):
                p=byparent.setdefault(f['independent_parent'],dict(trials=0,candidate_rows=0,detected=0,c13_top1=0,c13_top3=0))
                p['trials']+=1
                for metric in list(p)[1:]:p[metric]+=row[metric]
            methods[key]=dict(trials=len(rows),truth_count=sum(f['truth_count']for f in fs),independent_parents=len(byparent),
                **counts,common_attributable_trials=len(common),
                common_c13_top1=sum(rows[i]['c13_top1']for i in common),common_c13_top3=sum(rows[i]['c13_top3']for i in common),
                errors=sum(r['error']is not None for r in rows),peak_cap_trials=sum(r['peak_cap_reached']for r in rows),
                detector_cpu_seconds=sum(r['total_cpu_seconds']for r in rows),detector_wall_seconds_sum=sum(r['total_wall_seconds']for r in rows),per_parent=byparent)
        result[kind]=methods
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,default=4);p.add_argument('--output',required=True);a=p.parse_args()
    if not 1<=a.workers<=6:raise ValueError('one to six bounded workers')
    caches=[Path('/tmp/spaceapps-v3-ranker')/f'native-train{i:02d}-short-v2.json.gz'for i in range(1,5)]
    sources=[Path(__file__),Path(__file__).with_name('features.py'),Path(__file__).with_name('psf_gate.py'),INF/'ml_inference/detector.py',INF/'training/simulate_v2.py',INF/'training/evaluate_background.py']
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in sources}
    tasks=[('synthetic',seed)for seed in range(3801000,3801200)]+[('native',str(path),i)for path in caches for i in range(30)]
    started=time.perf_counter();fields=[]
    with ProcessPoolExecutor(max_workers=a.workers)as pool:
        for field in pool.map(_one,tasks,chunksize=1):
            fields.append(field)
            if len(fields)%40==0:print(json.dumps(dict(completed=len(fields),planned=len(tasks),elapsed=time.perf_counter()-started)),flush=True)
    for path,sha in hashes.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha,'source changed mid-pilot'
    report=dict(schema_version=1,designation='DEVELOPMENT gate pilot; no final/selection claim',source_sha256=hashes,
        gates=GATES,settings='C13 legacy peak proposal settings; local template gate before linking',
        model_sha256=_ranker().metadata['sha256'],native_input_cache_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in caches},
        native_controls='UNKNOWN, never counted as false positives',c13_ranking='exploratory fixed-model ranking; gate is a NEW detector profile',
        summary=summarize(fields),fields=fields,elapsed_seconds=time.perf_counter()-started)
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True);tmp=output.with_suffix(output.suffix+'.tmp');tmp.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');tmp.replace(output)
    print(json.dumps(dict(path=str(output),summary=report['summary'],elapsed=report['elapsed_seconds'])),flush=True)


if __name__=='__main__':main()
