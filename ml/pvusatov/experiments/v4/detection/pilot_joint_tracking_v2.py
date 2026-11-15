"""Prospectively fixed, separately typed DEVELOPMENT track-before-detect pilot.

No six-feature rows are generated from fitted hypotheses. Native controls remain
UNKNOWN. All 200 declared synthetic fields and 54 metadata-selected TRAIN-only
native derivatives are planned before image access. No FINAL input is accepted.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import resource
import time
import numpy as np
from ml.pvusatov.experiments.v4.detection.replay_guard import validate_replay
from ml_inference.detector import find_candidates
from ml_inference.model import load_ranker
from ml_inference.prepare import prepare
from training.simulate_v2 import simulate, load_bank, draw_cadence
from training.evaluate_background import read_native, project_response, add_projected_injection
from ml.pvusatov.experiments.v4.detection.joint_tracking import automatic_groups, plan_search, search_maps, nuisance_maps

REPO=Path(__file__).resolve().parents[5]
INF=REPO/'ml/pvusatov/backend/inference'
HERE=Path(__file__).resolve().parent
SETTINGS=dict(min_snr=4.,max_peaks=100,psf_sigma=.8,min_speed=.5,max_speed=60.,match_radius=1.4,min_epochs=3,min_support=.8,leave_one_out=True)
THRESHOLDS=(5.,6.,7.)
STATISTICS=('nuisance_sum','robust_positive')
MAX_WORK=600000000
C13='c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204'
CACHE_SHAS={'v4-train01':'efff6a122afb7537c6c36357dcbce465c199d977979808f978534f57ec0f0368',
            'v4-train03':'008327a0785202f5a91a5fdefa50e12dc46e3933792931cbc7d1f3f4f6f85f82'}
CONTEXT={}


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as s:
        for block in iter(lambda:s.read(1048576),b''):h.update(block)
    return h.hexdigest()


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temporary.replace(path)


def select_native(fields):
    return [f for f in fields if f.get('truth_kind')=='moving_injection'and f['direction_id']==0 and f['brightness']in(3,6,12)]


def span(path):
    p=np.asarray(path,float)
    return float(np.max(np.linalg.norm(p[:,None]-p[None,:],axis=2)))if len(p)>1 else 0.


def evaluate(tracks,truth,native):
    matches=[];true_spans=[];fitted_spans=[]
    for t in tracks:
        epochs=list(t.epochs);xy=np.asarray(t.positions_xy)
        distances=[np.linalg.norm(xy-np.asarray(p)[epochs],axis=1)for p in truth]
        eligible=[j for j,d in enumerate(distances)if np.all(d<=1.5)]
        j=min(eligible,key=lambda j:float(np.mean(distances[j])))if eligible else(-2 if native else-1)
        matches.append(j);true_spans.append(span(np.asarray(truth[j])[epochs])if j>=0 else None)
        fitted_spans.append(span(xy))
    count=lambda ids:len({matches[i]for i in ids if matches[i]>=0})
    resolved=lambda ids:len({matches[i]for i in ids if matches[i]>=0 and true_spans[i]>=3.})
    return dict(candidate_rows=len(tracks),matches=matches,detected=count(range(len(tracks))),
        top1=count(range(min(1,len(tracks)))),top3=count(range(min(3,len(tracks)))),
        resolved_detected=resolved(range(len(tracks))),resolved_top1=resolved(range(min(1,len(tracks)))),
        resolved_top3=resolved(range(min(3,len(tracks)))),matched_true_spans_px=true_spans,
        fitted_spans_px=fitted_spans,known_unmatched_rows=sum(m<0 for m in matches)if not native else None)


def merge_groups(tracks,threshold):
    ordered=sorted((t for t in tracks if t.search_statistic>=threshold),key=lambda t:-t.search_statistic)
    selected=[];capped=False
    for t in ordered:
        duplicate=False
        for other in selected:
            common=sorted(set(t.epochs)&set(other.epochs))
            if len(common)<3:continue
            a=np.asarray(t.positions_xy)[[t.epochs.index(e)for e in common]]
            b=np.asarray(other.positions_xy)[[other.epochs.index(e)for e in common]]
            if np.median(np.linalg.norm(a-b,axis=1))<2.:duplicate=True;break
        if duplicate:continue
        if len(selected)==100:capped=True;break
        selected.append(t)
    return selected,capped


def joint(images,times):
    started=time.perf_counter();cpu=time.process_time()
    maps,normalization=nuisance_maps(images)
    outputs={};diagnostics=[]
    for statistic in STATISTICS:
        alltracks=[];diags=[]
        for group in automatic_groups(times):
            plan=plan_search(np.asarray(times)[list(group)],images.shape[1:],reference_epoch_count=len(times))
            try:
                tracks,diag=search_maps(maps[list(group)],np.asarray(times)[list(group)],reference_epoch_count=len(times),
                    real_epochs=group,threshold=5.,max_work=MAX_WORK,statistic=statistic)
                alltracks.extend(tracks);diag['error']=None
            except Exception as exc:
                diag=dict(plan,error=type(exc).__name__+': '+str(exc),hypothesis_search_complete=False,
                    proposal_publication_complete=False,candidate_cap_reached=False,first_unpublished_statistic=None)
            diag['epochs']=list(group);diags.append(diag)
        for threshold in THRESHOLDS:
            tracks,capped=merge_groups(alltracks,threshold)
            hidden=any(d.get('first_unpublished_statistic')is not None and d['first_unpublished_statistic']>=threshold for d in diags)
            outputs[f'{statistic}:{threshold:g}']=dict(tracks=tracks,candidate_cap_reached=capped or hidden,
                errors=sum(d['error']is not None for d in diags),hypothesis_search_complete=all(d['hypothesis_search_complete']for d in diags),
                proposal_publication_complete=not(capped or hidden)and all(d['error']is None for d in diags))
        diagnostics.append(dict(statistic=statistic,groups=diags))
    return outputs,dict(normalization=normalization,searches=diagnostics,wall_seconds=time.perf_counter()-started,cpu_seconds=time.process_time()-cpu)


def ranker():
    if 'ranker'not in CONTEXT:
        CONTEXT['ranker']=load_ranker(REPO/'ml/pvusatov/releases/v3/model')
        if CONTEXT['ranker'].metadata['sha256']!=C13:raise ValueError('C13 baseline mismatch')
    return CONTEXT['ranker']


def native_context(header):
    parent=header['parent_id']
    if parent not in CONTEXT:
        obs=header['input_sources']
        for row in obs:
            if digest(row['path'])!=row['sha256']:raise ValueError('native bytes changed')
        ra,dec=header['center_deg']
        request=dict(schema_version=1,analysis_id='v4-joint-'+parent,source=dict(kind='fits',observations=obs,
            region=dict(right_ascension_deg=ra,declination_deg=dec,width_arcmin=6.,height_arcmin=6.)),options=header['preparation_options'])
        stack=prepare(request)
        np.testing.assert_allclose(stack.times,header['times_hours'],rtol=0,atol=1e-12)
        if list(stack.images.shape)!=header['registered_shape']:raise ValueError('registered shape changed')
        lookup={r['frame_id']:r for r in obs}
        natives=[read_native(lookup[f['frame_id']]['path'],stack.grid,stack.images.shape[1:])for f in stack.frames]
        controls,control_diagnostics=joint(stack.images,stack.times)
        baseline=find_candidates(stack.images,stack.times,**SETTINGS)
        CONTEXT[parent]=dict(stack=stack,natives=natives,responses={},controls=controls,control_diagnostics=control_diagnostics,baseline=baseline)
    return CONTEXT[parent]


def one(task):
    started=time.perf_counter();cpu=time.process_time();native=task['kind']=='native'
    identity={k:v for k,v in task.items()if k not in('header','field')}
    try:
        if not native:
            seed=task['seed']
            if not 3801000<=seed<3801200:raise ValueError('only declared DEVELOPMENT seeds accepted')
            if 'bank'not in CONTEXT:CONTEXT['bank']=load_bank(INF/'training/calibration/instrument-epsf-bank.npz')
            images,times,truth,mode,metadata=simulate(seed,CONTEXT['bank'],extended=seed%3==0,varying_psf=True)
            identity.update(mode=mode,truth_count=len(truth),metadata=metadata,times_hours=times.tolist(),shape=list(images.shape))
            controls=None
        else:
            f=task['field'];ctx=native_context(task['header']);stack=ctx['stack'];truth=[np.asarray(f['expected_xy'])]
            key=json.dumps(f['expected_xy']);responses=ctx['responses'].get(key)
            if responses is None:
                responses=np.asarray([project_response(n,stack.grid,p)[0]for n,p in zip(ctx['natives'],truth[0])]);ctx['responses'][key]=responses
            images=add_projected_injection(stack.images,responses,f['injected_flux'])
            for image in images:image-=np.nanmedian(image)
            times=stack.times;controls=ctx['controls']
            identity.update(truth_count=1,speed_px_hour=f['speed_px_hour'],brightness=f['brightness'],trajectory_id=f['trajectory_id'],
                latent_sha256=hashlib.sha256(json.dumps({k:f[k]for k in('expected_xy','injected_flux','origin_xy','velocity_xy_hour')},sort_keys=True).encode()).hexdigest(),
                times_hours=times.tolist(),shape=list(images.shape),covered_displacement_px=f['expected_covered_displacement_px'])
        # Same reconstructed images/proposals MUST agree with recorded cache before joint search.
        baseline_started=time.perf_counter();tracks=find_candidates(images,times,**SETTINGS)
        if native:
            validate_replay(tracks,f)
        scores=ranker().score(np.asarray([t.features()for t in tracks],np.float32).reshape(-1,6));order=np.argsort(-scores,kind='stable')
        baseline=evaluate([tracks[i]for i in order],truth,native)
        baseline.update(top100_detected=evaluate([tracks[i]for i in order[:100]],truth,native)['detected'],
            wall_seconds=time.perf_counter()-baseline_started,attribution_eligible=not native or evaluate(ctx['baseline'],truth,True)['detected']==0)
        results,diagnostics=joint(images,times);methods={}
        for name,result in results.items():
            tr=result.pop('tracks');metrics=evaluate(tr,truth,native)
            eligible=not native or evaluate(controls[name]['tracks'],truth,True)['detected']==0
            methods[name]=dict(result,**metrics,attribution_eligible=eligible,unknown_control_rows=len(controls[name]['tracks'])if native else None,
                typed_hypotheses=[asdict(t)for t in tr])
        return dict(identity,baseline=baseline,methods=methods,diagnostics=diagnostics,error=None,
            wall_seconds=time.perf_counter()-started,cpu_seconds=time.process_time()-cpu,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    except Exception as exc:
        return dict(identity,error=type(exc).__name__+': '+str(exc),wall_seconds=time.perf_counter()-started,cpu_seconds=time.process_time()-cpu,
            rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)


def build_tasks():
    tasks=[];cachehashes={}
    for seed in range(3801000,3801200):
        rng=np.random.default_rng(seed);n=int(rng.choice([3,4,5,6,7,8],p=[.30,.25,.15,.15,.075,.075]));times,_=draw_cadence(rng,n)
        tasks.append(dict(kind='synthetic',seed=seed,parent_id=str(seed),planned_times=times.tolist(),planned_shape=[80,80]))
    for parent,sha in CACHE_SHAS.items():
        path=Path('/tmp/spaceapps-v4-native-cache/main-v2')/(parent+'-both.json.gz')
        if digest(path)!=sha:raise ValueError('safe native cache SHA mismatch')
        cachehashes[str(path)]=sha
        with gzip.open(path,'rt')as s:cache=json.load(s)
        if cache['partition']!='train'or cache['parent_id']!=parent or cache['baseline_model_sha256']!=C13:raise ValueError('only declared safe TRAIN parents')
        selected=select_native(cache['fields'])
        if len(selected)!=27:raise ValueError('27 metadata-selected native derivatives required')
        header={k:cache[k]for k in('parent_id','input_sources','center_deg','times_hours','registered_shape','preparation_options')}
        if cache['detector_settings']!=SETTINGS:raise ValueError('baseline profile differs')
        for f in selected:
            keep={k:f[k]for k in('expected_xy','injected_flux','origin_xy','velocity_xy_hour','speed_px_hour','brightness','trajectory_id',
                'expected_covered_displacement_px','candidate_epochs','candidate_positions_xy','features')}
            tasks.append(dict(kind='native',parent_id=parent,seed=f['seed'],header=header,field=keep,
                planned_times=cache['times_hours'],planned_shape=cache['registered_shape'][1:]))
        del cache
    return tasks,cachehashes


def summary(fields):
    result={}
    for kind in('synthetic','native'):
        fs=[f for f in fields if f['kind']==kind];ok=[f for f in fs if f['error']is None]
        methods={}
        for name in['baseline',*[f'{s}:{t:g}'for s in STATISTICS for t in THRESHOLDS]]:
            rows=[f['baseline']if name=='baseline'else f['methods'][name]for f in ok]
            common=[i for i,f in enumerate(ok)if f['baseline']['attribution_eligible']and rows[i]['attribution_eligible']]
            methods[name]=dict(completed=len(ok),allplanned=len(fs),errors=len(fs)-len(ok),truth_count=sum(f.get('truth_count',0)for f in fs),
                **{k:sum(r[k]for r in rows)for k in('candidate_rows','detected','top1','top3','resolved_detected','resolved_top1','resolved_top3')},
                common_attributable_trials=len(common),common_top1=sum(rows[i]['top1']for i in common),common_top3=sum(rows[i]['top3']for i in common),
                incomplete_searches=sum(not r.get('hypothesis_search_complete',True)for r in rows),
                capped_publications=sum(r.get('candidate_cap_reached',False)for r in rows))
        nulls={}
        for mode in('noise_only','artifacts_only'):
            subset=[f for f in ok if f.get('mode')==mode]
            nulls[mode]={name:dict(fields=len(subset),fields_with_proposals=sum(f['methods'][name]['candidate_rows']>0 for f in subset),
                proposals=sum(f['methods'][name]['candidate_rows']for f in subset))for name in methods if name!='baseline'}
        result[kind]=dict(independent_parents=len({f['parent_id']for f in fs}),methods=methods,nulls=nulls)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,default=4);p.add_argument('--output',required=True)
    p.add_argument('--native-only',action='store_true');p.add_argument('--protocol',required=True);p.add_argument('--smoke',action='store_true');p.add_argument('--plan-only',action='store_true');a=p.parse_args()
    if not 1<=a.workers<=6:raise ValueError('bounded1..6workers')
    if Path(a.output).exists():raise ValueError('immutable output already exists')
    sources=[Path(__file__),HERE/'replay_guard.py',HERE/'joint_tracking.py',HERE/'joint_tracking.cpp',INF/'ml_inference/detector.py',INF/'ml_inference/model.py',
        INF/'ml_inference/prepare.py',INF/'training/simulate_v2.py',INF/'training/evaluate_background.py',
        INF/'training/calibration/instrument-epsf-bank.npz',REPO/'ml/pvusatov/releases/v3/model/ranker.onnx',REPO/'ml/pvusatov/releases/v3/model/metadata.json']
    hashes={str(p):digest(p)for p in sources};tasks,cachehashes=build_tasks();plans=[]
    for task in tasks:
        times=task['planned_times'];groups=automatic_groups(times)
        plans.append(dict(kind=task['kind'],parent_id=task['parent_id'],seed=task['seed'],trajectory_id=task.get('field',{}).get('trajectory_id'),
            brightness=task.get('field',{}).get('brightness'),groups=[dict(epochs=g,**plan_search(np.asarray(times)[list(g)],task['planned_shape'],reference_epoch_count=len(times)))for g in groups]))
    protocol=dict(schema_version=1,designation='DEVELOPMENT exact-Float32 replay guard correction; original v1errors preserved; no fitting/FINAL',source_sha256=hashes,
        native_cache_sha256=cachehashes,baseline_sha256=C13,thresholds=THRESHOLDS,statistics=STATISTICS,max_work_per_group=MAX_WORK,
        max_candidates_per_method=100,plans=plans,allplanned_fields=len(tasks),native_subset='direction0,all9speeds,brightness3/6/12;2TRAINparents',
        warning='spatial injection recovery is not confirmed motion; no Gaussian false-alarm calibration')
    protocol_path=Path(a.protocol)
    if protocol_path.exists():
        if json.loads(protocol_path.read_text())!=json.loads(json.dumps(protocol)):raise ValueError('existing protocol differs')
    else:atomic(protocol_path,protocol)
    if a.plan_only:print(json.dumps(dict(protocol=str(protocol_path),fields=len(tasks),work=sum(g['planned_pixel_epoch_tests']for p in plans for g in p['groups'])*2)));return
    if a.native_only:tasks=[t for t in tasks if t['kind']=='native']
    if a.smoke:tasks=tasks[:3]
    started=time.perf_counter();fields=[];journal=Path(a.output+'.jsonl')
    if journal.exists():raise ValueError('existing journal; use distinct output')
    with journal.open('x')as j,ProcessPoolExecutor(max_workers=a.workers)as pool:
        for f in pool.map(one,tasks,chunksize=1):
            fields.append(f);j.write(json.dumps(f,allow_nan=False)+'\n');j.flush()
            print(json.dumps(dict(completed=len(fields),planned=len(tasks),last_parent=f['parent_id'],error=f['error'],elapsed=time.perf_counter()-started)),flush=True)
    if any(digest(p)!=sha for p,sha in hashes.items()):raise ValueError('source changed mid-pilot; results not finalized')
    report=dict(protocol_sha256=digest(protocol_path),source_sha256=hashes,smoke=a.smoke,native_only=a.native_only,elapsed_seconds=time.perf_counter()-started,
        summary=summary(fields),fields=fields,limitations=['UNKNOWN native controls are not false positives','two native parents do not establish broad generalization',
        'joint positions fitted, not epoch peaks; no learned confidence','all-selected-epoch support required','Gaussian equal-noise response approximation; correlations uncalibrated'])
    atomic(a.output,report);print(json.dumps(dict(output=a.output,summary=report['summary'],elapsed=report['elapsed_seconds'])),flush=True)


if __name__=='__main__':main()
