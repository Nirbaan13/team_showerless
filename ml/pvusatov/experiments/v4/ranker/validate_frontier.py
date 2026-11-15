"""All36 V4 development exports/parity/outcomes; no fitting or final selection.

Fitting records and all old family specimens remain byte-immutable. Numerical
adapter policy is explicit. Raw scores/models are scratch-only, all failures stay
in the complete report, and only root can select/freeze the final candidate.
"""
from __future__ import annotations
import os
for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[name]='1'
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import argparse,json,sys,time,traceback,hashlib,gc
import numpy as np
import joblib,onnx
from datasets import BASE,sha,read_cache,native_moving_validation,recovery_report,FEATURE_NAMES,FEATURE_VERSION,FEATURE_CONTRACT_SHA256
from frontier import configurations,resolved_configurations
from export_graph import export_graph,SCORE_NUMERICS
from code_binding import verify_module
import datasets,frontier,learning,tree_ranker,export_graph as exporter,code_binding
sys.path.insert(0,str(BASE))
from experiments.v4.detection import runtime_model
FAMILIES=dict(extra=('ExtraTreesClassifier','mean_weighted_class1_leaf_fraction','Arithmetic mean class1 weighted leaf fractions; uncalibrated ranking'),hist=('HistGradientBoostingClassifier','sigmoid_logit_utility','Fixed sigmoid of summed binary boosted-tree logit; uncalibrated ranking'),ranknet=('RankNetTreeBoost','sigmoid_pairwise_utility','Fixed sigmoid of summed pairwise-ranking tree utility; not calibrated probability'),listnet=('ListNetTreeBoost','sigmoid_listwise_utility','Fixed sigmoid of summed listwise-ranking tree utility; not calibrated probability'))


def atomic_json(path,value):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.writing')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temporary.replace(path)


def identity(field):return {key:field[key]for key in ['parent_id','seed','trajectory_id','brightness']if key in field}


def field_split(values,fields):return list(np.split(values,np.cumsum([len(f['matches'])for f in fields])[:-1]))


def parity(fields,reference,actual):
    expected=field_split(reference,fields);observed=field_split(actual,fields)
    report=dict(fields=len(fields),rows=len(reference),rtol=2e-6,atol=2e-6,score_allclose=bool(np.allclose(reference,actual,rtol=2e-6,atol=2e-6)),max_abs_error=float(np.max(abs(reference-actual)))if len(reference)else 0.,ordered_top1_top3_changed_fields=[],known_retention_changed_fields=[],raw_top100_membership_changed_fields=[],residual_quota99_membership_changed_fields=[],full_order_changed_field_count=0,low_order_examples=[])
    for field,left,right in zip(fields,expected,observed):
        a=np.argsort(-left,kind='stable');b=np.argsort(-right,kind='stable');tag=identity(field)
        if any(not np.array_equal(a[:k],b[:k])for k in [1,3]):report['ordered_top1_top3_changed_fields'].append(tag)
        matches=np.asarray(field['matches'],int)
        if any({int(v)for v in matches[a[:k]]if v>=0}!={int(v)for v in matches[b[:k]]if v>=0}for k in [1,3]):report['known_retention_changed_fields'].append(tag)
        if set(a[:100])!=set(b[:100]):report['raw_top100_membership_changed_fields'].append(tag)
        if set(a[:99])!=set(b[:99]):report['residual_quota99_membership_changed_fields'].append(tag)
        if not np.array_equal(a,b):
            report['full_order_changed_field_count']+=1
            if len(report['low_order_examples'])<25:
                different=np.flatnonzero(a!=b);first=int(different[0]);i=int(a[first]);j=int(b[first]);report['low_order_examples'].append(dict(field=tag,first_differing_rank=first+1,reference_candidate_index=i,onnx_candidate_index=j,reference_score_gap=float(left[i]-left[j]),onnx_score_gap=float(right[i]-right[j])))
    report['protected_pass']=report['score_allclose']and not report['ordered_top1_top3_changed_fields']and not report['known_retention_changed_fields']
    return report


def score_runtime(ranker,x):
    return np.concatenate([ranker.score(x[start:start+40000])for start in range(0,len(x),40000)])if len(x)else np.empty(0,np.float32)


def presets_score(payload,model,ranker,indices):
    result={};parity_ok=True
    for name,field in payload['cases'].items():
        x=np.asarray(field['features_v4'],np.float32).reshape(-1,30);actual=ranker.score(x);reference=model.predict_proba(x[:,indices])[:,1]if len(x)else np.empty(0)
        p=parity([dict(field,seed=name)],reference,actual);parity_ok &= p['protected_pass'];order=np.argsort(-actual,kind='stable');known=np.flatnonzero(np.asarray(field['matches'])>=0)
        bloom=field['bloom_tracks'];protected=min(3,len(x));published_bloom=bloom[:100-protected]
        result[name]=dict(parity=p,known_residual_ranks=[int(np.flatnonzero(order==i)[0]+1)for i in known],known_bloom_retained=any(b.get('known_target_match')for b in published_bloom),bloom_unscored=all(b['score']is None and b['photometry']is False and b['ml_ranked']is False for b in bloom))
    d2=result['comet-d2']['known_residual_ranks'];d6=result['comet-d6']['known_residual_ranks'];checks=dict(d2_rank1=bool(d2)and min(d2)<=1,d6_rank_le4=bool(d6)and min(d6)<=4,vesta_bloom_retained=all(result[n]['known_bloom_retained']for n in ['vesta-d3','vesta-d6']),all_bloom_unscored=all(r['bloom_unscored']for r in result.values()),protected_onnx_parity=parity_ok)
    return dict(cases=result,checks=checks,passes=all(checks.values()),d6_preferred_rank_le3=bool(d6)and min(d6)<=3,scope='ExistingDEVELOPMENTviews/twoknownobjects; unmatchedtracksUNKNOWN, nevertraininglabels')


def eligible(metrics,baseline,parity_reports,presets,config,artifact_bytes):
    reasons=[];deltas=[]
    for cohort in ['all_planned','common_attributable']:
        for k in [1,3]:
            key='macro_parent_recall'+str(k);delta=metrics['native'][cohort][key]-baseline['native'][cohort][key];deltas.append(delta)
            if delta< -1e-12:reasons.append('native_'+cohort+'_'+key+'_regression')
            for macro in ['macro_field_recall','macro_cadence_recall']:
                key=macro+str(k);delta=metrics['synthetic'][cohort][key]-baseline['synthetic'][cohort][key];deltas.append(delta)
                if delta< -1e-12:reasons.append('synthetic_'+cohort+'_'+key+'_regression')
    if not any(d>1e-12 for d in deltas):reasons.append('no_positive_protected_budget_improvement')
    if any(not p['protected_pass']for p in parity_reports.values()):reasons.append('protected_ONNX_parity_failure')
    if not presets['passes']:reasons.append('known_development_preset_gate_failure')
    if config['diagnostic_only']:reasons.append('preregistered_direct_availability_diagnostic_only')
    if artifact_bytes>32*1024**2:reasons.append('artifact_exceeds32MiB')
    return dict(eligible=not reasons,reasons=reasons,control_workload_ratio=1.,candidate_pool='EXACTsamefixedsigma0.8pool; allunknowncontrolsremainunlabeled',selection_performed=False)


def main(args):
    source=Path(args.estimators);output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
    checks=[verify_module(m)for m in [sys.modules[__name__],datasets,frontier,learning,tree_ranker,exporter,code_binding,runtime_model]]
    plans=configurations()+resolved_configurations();root=Path('/tmp/spaceapps-v4-native-cache/main-v2');run_manifest=root/'development-run-manifest.json'
    if sha(run_manifest)!='a175b4c349eb0fa89ef0ecebf86d5871cecb49c7b3b99556f2742deb4bc75a43':raise ValueError('native completed-run manifest changed')
    synthetic=Path('/tmp/spaceapps-v4-ranker/synthetic-validation-30-v1.json.gz');header,sv=read_cache(synthetic,'validation');native_paths=[root/f'v4-validation{i:02d}-both.json.gz'for i in range(1,9)];nv=[]
    for p in native_paths:_,f=read_cache(p,'validation');nv.extend(f)
    nv=native_moving_validation(nv);sx=np.vstack([f['features_v4']for f in sv]);nx=np.vstack([f['features_v4']for f in nv]);datasets_fields=dict(synthetic=sv,native=nv);matrices=dict(synthetic=sx,native=nx)
    baseline=dict(synthetic=recovery_report(sv,[f['scores_c13']for f in sv],True),native=recovery_report(nv,[f['scores_c13']for f in nv]))
    preset_path=BASE/'experiments/v4/detection/results/preset-feature-cache.json';assert sha(preset_path)=='0acd2fff5d0427cc2179641606db9d918c78725af3c6ae127940b08410dabf3d';preset_payload=json.loads(preset_path.read_text());assert preset_payload['fitting_forbidden']is True
    records={}
    for c in plans:
        path=source/(c['id']+'.json');record=json.loads(path.read_text());assert record['config']==c
        if record['error']:records[c['id']]=record;continue
        if sha(record['estimator_path'])!=record['estimator_sha256']:raise ValueError('estimator bytes changed '+c['id'])
        phase='resolved'if c.get('training_label_policy')else'synthetic'if c['native_mass']==0 else'native'
        assert sha(source/(phase+'-inputs.json'))==record['training_input_manifest_sha256'];records[c['id']]=record
    manifest=dict(schema_version=4,purpose=__doc__,root_native_run_sha256=sha(run_manifest),input_sha256={str(p):sha(p)for p in [synthetic,*native_paths,preset_path]},fitting_record_sha256={c['id']:sha(source/(c['id']+'.json'))for c in plans},configs=plans,source_checks=checks,score_numerics=SCORE_NUMERICS,all8new_native_validation_parents_required=True,native_planned_moving_derivatives=len(nv),synthetic_fields=len(sv),source_scope='No old/pilot/main-v1nativefit, no old/newFINALdata',candidate_pool_unchanged=True)
    atomic_json(output/'invocation.json',manifest)
    snapshot=output/'source-snapshots';snapshot.mkdir()
    for c in checks:
        path=Path(c['path']);assert sha(path)==c['source_sha256'];(snapshot/(c['source_sha256']+'.source')).write_bytes(path.read_bytes())
    def one(config):
        started=time.monotonic();identifier=config['id'];record=records[identifier];folder=output/identifier;folder.mkdir()
        if record.get('error'):return dict(id=identifier,config=config,error=record['error'],eligibility=dict(eligible=False,reasons=['fit_failed']))
        try:
            model=joblib.load(record['estimator_path']);indices=config['selected_feature_indices'];reference={k:model.predict_proba(x[:,indices])[:,1]for k,x in matrices.items()};skmetrics={k:recovery_report(datasets_fields[k],field_split(v,datasets_fields[k]),k=='synthetic')for k,v in reference.items()}
            family,kind,description=FAMILIES[config['family']];metadata=dict(schema_version=4,artifact_format='v4-score-vector-v1',model_id='spherex-v4-development-'+identifier,feature_names=list(FEATURE_NAMES),full_feature_count=30,selected_feature_indices=indices,selected_feature_names=[FEATURE_NAMES[i]for i in indices],feature_version=FEATURE_VERSION,feature_contract_sha256=FEATURE_CONTRACT_SHA256,feature_source_sha256=sha(BASE/'experiments/v4/detection/features.py'),detector_profile=header['detector_settings'],feature_options=dict(template_psf_sigma=.8),class_labels=[0,1],positive_class=1,model_family=family,score_kind=kind,score_description=description,score_numerics=SCORE_NUMERICS,algorithm_version_proposal='motion-v4-'+config['family']+'-'+identifier,status='experimental',release_state='Developmentfrontierexport; NOTSELECTEDORRELEASED',training_record_sha256=sha(source/(identifier+'.json')),fitting_performed_during_export=False)
            graph=export_graph(model,30,indices,metadata);graph.graph.name='spherex-v4-score-vector';artifact=folder/'ranker.onnx';artifact.write_bytes(graph.SerializeToString());metadata['sha256']=sha(artifact);atomic_json(folder/'metadata.json',metadata);ranker=runtime_model.load_ranker(folder)
            actual={k:score_runtime(ranker,x)for k,x in matrices.items()};p={k:parity(datasets_fields[k],reference[k],v)for k,v in actual.items()};metrics={k:recovery_report(datasets_fields[k],field_split(v,datasets_fields[k]),k=='synthetic')for k,v in actual.items()};presets=presets_score(preset_payload,model,ranker,indices);scores_manifest={}
            for k in matrices:
                for label,values in [('reference',reference[k]),('onnx',actual[k])]:
                    path=folder/(k+'-'+label+'.npy');np.save(path,values,allow_pickle=False);scores_manifest[k+'_'+label]=dict(path=str(path),sha256=sha(path),rows=len(values))
            result=dict(id=identifier,config=config,model_sha256=metadata['sha256'],artifact_bytes=artifact.stat().st_size,model_directory=str(folder),fit_record_sha256=metadata['training_record_sha256'],sklearn_development=skmetrics,onnx_development=metrics,parity=p,presets=presets,eligibility=eligible(metrics,baseline,p,presets,config,artifact.stat().st_size),scores=scores_manifest,error=None,elapsed_seconds=time.monotonic()-started)
        except Exception as error:result=dict(id=identifier,config=config,sklearn_development=locals().get('skmetrics'),error=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc()),eligibility=dict(eligible=False,reasons=['export_or_runtime_validation_failed']),elapsed_seconds=time.monotonic()-started)
        atomic_json(folder/'report.json',result);return result
    results=[]
    with ThreadPoolExecutor(max_workers=args.workers)as pool:
        for task in as_completed([pool.submit(one,c)for c in plans]):
            r=task.result();results.append(r);atomic_json(output/'progress.json',dict(baseline=baseline,experiments=results,planned=36,selection_performed=False));summary=dict(completed=len(results),id=r['id'],config=r['config'],eligible=r['eligibility'],error=r.get('error'),seconds=r.get('elapsed_seconds'))
            if not r.get('error'):summary.update(native_K=[r['onnx_development']['native']['common_attributable']['top'+str(k)]for k in [1,3]],synthetic_K=[r['onnx_development']['synthetic']['all_planned']['top'+str(k)]for k in [1,3]])
            print(json.dumps(summary),flush=True)
    atomic_json(output/'all-outcomes.json',dict(schema_version=4,baseline=baseline,experiments=results,complete=len(results)==36,invocation_sha256=sha(output/'invocation.json'),all_primary_outcomes_retained=True,selection_performed=False))
    print('COMPLETEALL36',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--estimators',default='/tmp/spaceapps-v4-ranker/frontier-v1');parser.add_argument('--output',default='/tmp/spaceapps-v4-ranker/frontier-onnx-v1');parser.add_argument('--workers',type=int,default=2);args=parser.parse_args()
    if not 1<=args.workers<=4:parser.error('boundedvalidationworkers1..4')
    main(args)
