"""Prospective DEV association study; fixed models, no fitting or production edits."""
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse,gzip,hashlib,json,resource,time
from pathlib import Path
import numpy as np
from ml_inference.detector import difference_frames,_detect_peaks,link_detections
from ml_inference.model import load_ranker as load13
from training.simulate_v2 import simulate,load_bank
from ml.pvusatov.experiments.v4.detection.features import extract_features
from ml.pvusatov.experiments.v4.detection.runtime_model import load_ranker as load596
from ml.pvusatov.experiments.v4.operating_points.study import digest,atomic,image_hash,label_tracks,recovery,C13,C596,REPO,INF
from .policies import build_hypotheses,pair_exclusive,near_duplicate
HERE=Path(__file__).resolve().parent
SCRATCH=Path('/tmp/spaceapps-v4-association-pilot')
S={}


def initialize(path,sha):
    if digest(path)!=sha:raise ValueError('protocol changed')
    p=json.loads(Path(path).read_text())
    if p['synthetic_seeds']!=list(range(3806000,3806100))or p['min_snr']!=[3.,4.]:raise ValueError('undeclared DEV matrix')
    if any(digest(k)!=v for k,v in p['source_sha256'].items()):raise ValueError('source changed')
    for name,m in p['models'].items():
        if digest(Path(m['directory'])/'ranker.onnx')!=m['artifact_sha256']or digest(Path(m['directory'])/'metadata.json')!=m['metadata_sha256']:raise ValueError('model changed')
    S.update(protocol=p,C13=load13(p['models']['C13']['directory']),C596=load596(p['models']['C596']['directory']))
    if S['C13'].metadata['sha256']!=C13 or S['C596'].metadata['sha256']!=C596:raise ValueError('fixed artifact differs')
    S['bank']=load_bank(INF/'training/calibration/instrument-epsf-bank.npz')


def predict(images,times,outlier=None,bloom=None):
    residuals=difference_frames(images,leave_one_out=True);profiles={}
    for threshold in (3.,4.):
        started=time.process_time();peaks=[_detect_peaks(d,np.isfinite(d),.8,threshold,100,.8)for d in residuals]
        peak_cpu=time.process_time()-started
        # Actual legacy path is independently measured, rather than charged for rich full-pool extraction.
        started=time.process_time();baseline=link_detections(peaks,times,.5,60.,1.4,3)
        legacy_features=extract_features(images,times,baseline,psf_sigma=.8,outlier=outlier,bloom=bloom,residuals=residuals)
        baseline_matrix=np.asarray(legacy_features['features_v4'],np.float32)
        baseline_scores={m:S[m].score(baseline_matrix[:,:6]if m=='C13'else baseline_matrix)for m in ('C13','C596')}
        actual_baseline_cpu=time.process_time()-started
        started=time.process_time();pool,work=build_hypotheses(peaks,times,.5,60.,1.4,3);generation_cpu=time.process_time()-started
        tracks=[c for _,c in pool];started=time.process_time()
        result=extract_features(images,times,tracks,psf_sigma=.8,outlier=outlier,bloom=bloom,residuals=residuals)
        matrix=np.asarray(result['features_v4'],np.float32);scores={m:S[m].score(matrix[:,:6]if m=='C13'else matrix)for m in ('C13','C596')};feature_score_cpu=time.process_time()-started
        policies={}
        for name,fn in [('legacy',lambda:pair_exclusive(pool)),('learned_pair',lambda:pair_exclusive(pool,scores['C596'])),('near_duplicate',lambda:near_duplicate(pool))]:
            start=time.process_time()
            try:ids,account=fn();error=None
            except Exception as exc:ids=[];account=dict(complete=False);error=dict(type=type(exc).__name__,message=str(exc))
            policies[name]=dict(indices=ids,accounting=account,error=error,cpu_seconds=time.process_time()-start)
        ids=policies['legacy']['indices']
        if not policies['legacy']['error']:
            if [tracks[i]for i in ids]!=baseline:raise ValueError('unchanged baseline candidate parity failed')
            np.testing.assert_array_equal(matrix[ids],baseline_matrix)
            for m in scores:np.testing.assert_array_equal(scores[m][ids],baseline_scores[m])
        profiles[str(threshold)]=dict(tracks=tracks,features_v4=matrix.tolist(),candidate_ids=result['candidate_ids'],scores={m:s.tolist()for m,s in scores.items()},policies=policies,
            hypotheses=len(pool),work=work,peaks_per_epoch=[len(p)for p in peaks],peak_cap_reached=any(len(p)>=100 for p in peaks),
            peak_cpu_seconds=peak_cpu,actual_baseline_cpu_seconds=actual_baseline_cpu,pool_generation_cpu_seconds=generation_cpu,full_pool_feature_score_cpu_seconds=feature_score_cpu,
            baseline_exact_parity=not policies['legacy']['error'])
    return profiles


def finish(profiles,truth,native,controls=None):
    output={}
    for threshold,p in profiles.items():
        tracks=p['tracks'];labels=label_tracks(tracks,truth,native);policies={}
        for name,policy in p['policies'].items():
            ids=policy['indices'];subset=[labels[i]for i in ids];models={}
            for m,scores in p['scores'].items():
                order=np.argsort(-np.asarray(scores)[ids],kind='stable');models[m]=recovery(subset,order)
            preexisting=False
            if controls is not None:
                cp=controls[threshold];ct=[cp['tracks'][i]for i in cp['policies'][name]['indices']]
                preexisting=any(x>=0 for x in label_tracks(ct,truth,True))
            policies[name]={**policy,'candidate_rows':len(ids),'matches':subset,'models':models,'preexisting_control_match':preexisting,'attribution_eligible':not preexisting,
                'unknown_rows':sum(x<0 for x in subset)if native else None}
        output[threshold]={**{k:v for k,v in p.items()if k not in ('tracks','policies')},'policies':policies,'matches':labels,
            'full_pool_detected':len({x for x in labels if x>=0}),'candidate_epochs':[list(t.epochs)for t in tracks],'candidate_positions_xy':[t.positions_xy for t in tracks]}
    return output


def one(task):
    start=time.perf_counter();cpu=time.process_time();identity={};truth=[]
    try:
        if task['kind']=='synthetic':
            seed=task['seed']
            if seed not in S['protocol']['synthetic_seeds']:raise ValueError('undeclared DEVELOPMENT seed')
            images,times,truth,mode,metadata=simulate(seed,S['bank'],extended=seed%3==0,varying_psf=True)
            outlier=bloom=None;identity=dict(kind='synthetic',seed=seed,parent_id=str(seed),case_id=str(seed),mode=mode,simulation_metadata=metadata)
        else:
            if digest(task['path'])!=task['sha256']or digest(task['metadata'])!=task['metadata_sha256']:raise ValueError('packet changed')
            meta=json.loads(Path(task['metadata']).read_text());identity={k:v for k,v in meta.items()if k not in ('truth','image_sha256','finite_mask_sha256')}
            with np.load(task['path'])as packet:images=packet['images'];times=packet['times'];outlier=packet['outlier'];bloom=packet['bloom'];bloom=None if bloom.size==0 else bloom
        profiles=predict(images,times,outlier,bloom)
        # Truth never enters proposals/features/scoring/association.
        if task['kind']!='synthetic':truth=meta['truth']
        controls=None
        if task['kind']=='native':
            with gzip.open(SCRATCH/'fields'/(task['parent_id']+'-control.json.gz'),'rt')as stream:control=json.load(stream)
            from ml_inference.detector import Candidate
            controls={}
            for t,p in control['profiles'].items():
                ct=[Candidate(tuple(e),tuple(map(tuple,xy)),(),0.,0.,0.)for e,xy in zip(p['candidate_epochs'],p['candidate_positions_xy'])]
                controls[t]=dict(tracks=ct,policies=p['policies'])
        row=dict(**identity,truth_count=len(truth),expected_xy=[np.asarray(x).tolist()for x in truth],times_hours=np.asarray(times).tolist(),shape=list(images.shape),image_sha256=image_hash(images),finite_mask_sha256=image_hash(np.isfinite(images)),
            profiles=finish(profiles,truth,task['kind']!='synthetic',controls),cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-start,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    except Exception as exc:
        row=dict(**(identity or task),task_error=dict(type=type(exc).__name__,message=str(exc)),profiles={},truth_count=None if task['kind']=='synthetic'else(0 if task['kind']=='native_control'else 1),cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-start,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    key=identity.get('case_id',str(task.get('seed',task.get('metadata','error'))).replace('/','_'));path=SCRATCH/'fields'/(key+'.json.gz');atomic(path,row)
    compact={k:v for k,v in row.items()if k not in ('expected_xy','simulation_metadata','profiles')}
    compact['profiles']={t:{k:v for k,v in p.items()if k not in ('features_v4','scores','candidate_ids','matches','candidate_epochs','candidate_positions_xy','policies')}for t,p in row['profiles'].items()}
    for t,p in row['profiles'].items():compact['profiles'][t]['policies']={name:{k:v for k,v in q.items()if k not in ('indices','matches')}for name,q in p['policies'].items()}
    return dict(path=str(path),sha256=digest(path),field=compact)


def plan():
    old=json.loads((HERE.parent/'operating_points/protocol.json').read_text());native=old['native']
    for name,info in native.items():info['seed']=3806201 if name=='v4-train01'else 3806203
    sources=list(HERE.glob('*.py'))+[HERE.parent/'operating_points/study.py',HERE.parent/'detection/features.py',HERE.parent/'detection/runtime_model.py',INF/'training/simulate_v2.py',INF/'training/evaluate_background.py',INF/'training/calibration/instrument-epsf-bank.npz']+list((INF/'ml_inference').glob('*.py'))
    return dict(schema_version=1,designation='Prospective DEVELOPMENT/TRAIN-only association ablation; no model/default/promotion selection',synthetic_seeds=list(range(3806000,3806100)),native=native,models=old['models'],min_snr=[3.,4.],
        options=dict(psf_sigma=.8,max_peaks=100,min_epochs=3,min_speed=.5,max_speed=60.,match_radius=1.4,min_support=.8,max_link_checks=2000000,max_hypotheses=50000),
        policies=dict(legacy='baseline-score ordered pair-exclusive; exact original parity',learned_pair='fixed C596 ordered pair-exclusive; no refitting',near_duplicate='baseline-score order; suppress only maxcommonXYdistance<=1px across>=3 and>=80%shorter epochs; diagnostic grouping not identity truth'),
        policy_caps=dict(budgeted_index_pair_operations=10000000,near_duplicate_exact_comparisons=1000000,on_exceed='withhold partial policy; preserve allplanned error'),
        native_matrix=dict(speeds=[.1,1.,10.],direction_ids=[0,1,2],brightness=[3.,12.,48.],latent='same seeded RNG origin+angle per speed/direction; supported finite centre legacy amplitude rule; no recentering'),
        evaluation='truth only after predictions; per-policy preexisting controls independently attributed; UNKNOWN=-2 never real negative; report allplanned and common attribution; full-pool availability is proposal diagnostic, not reviewed recovery',
        resources=dict(workers=4,math_threads=1,budget_gib=8),source_sha256={str(p):digest(p)for p in sources})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',action='store_true');args=parser.parse_args();path=HERE/'protocol.json'
    if args.plan:
        if path.exists():raise ValueError('protocol already exists')
        atomic(path,plan());print('PROTOCOL',digest(path),flush=True);return
    sha=digest(path);initialize(path,sha)
    from .native_packets import prepare_packets
    tasks=prepare_packets(S['protocol'],SCRATCH);atomic(HERE/'results/packet-manifest.json',tasks)
    entries=[];started=time.perf_counter()
    with ProcessPoolExecutor(4,initializer=initialize,initargs=(str(path),sha))as pool:
        for batch in ([t for t in tasks if t['kind']=='native_control'],[dict(kind='synthetic',seed=s)for s in S['protocol']['synthetic_seeds']]+[t for t in tasks if t['kind']=='native']):
            for future in as_completed([pool.submit(one,t)for t in batch]):
                entry=future.result();entries.append(entry)
                if len(entries)%10==0:print('DONE',len(entries),'errors',sum('task_error'in e['field']for e in entries),'seconds',round(time.perf_counter()-started,1),flush=True)
    if digest(path)!=sha or any(digest(k)!=v for k,v in S['protocol']['source_sha256'].items()):raise ValueError('source/protocol churn')
    atomic(HERE/'results/run.json',dict(protocol_sha256=sha,entries=entries,wall_seconds=time.perf_counter()-started));print('COMPLETE',len(entries),flush=True)
if __name__=='__main__':main()
