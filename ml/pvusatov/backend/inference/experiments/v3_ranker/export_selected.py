"""Export exactly the selected cached estimator; no fitting or final data access.

This writes a DEVELOPMENT candidate. Only root's external trusted freeze may
open final data. Any numerical/rank/retention failure is recorded, never hidden
by selecting another model. Runtime carries ONNX/JSON only, never a pickle.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import inspect
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import joblib
import numpy as np
import onnx
import onnxruntime
import sklearn
import skl2onnx
from skl2onnx import to_onnx
import train_grid as grid
from select_cached import qualifies,write
from select_system import V2_SHA,scores,native_view
from selection_integrity import validate_hashes,validate_relocated_source_hashes,normalize_native_pair,shared_selection_cohort,selection_subset,paired_native_report
from experiments.v3_evaluation.paired import paired_report
from ml_inference.model import FEATURE_NAMES,SCORE_KIND,load_ranker


class RankParityError(ValueError):
    def __init__(self,details):
        super().__init__('protected score/review/output rank parity failed')
        self.details=details


def validate_invocation_sources(invocation,source_root=None,invocation_sha256=None):
    expected=invocation['source_sha256']
    if source_root is None:
        validate_hashes(expected)
        return dict(mode='original selection sources still at original paths',source_sha256=expected)
    root=Path(source_root).resolve()
    archived=root/'invocation-source.json';snapshot_path=root/'snapshot-manifest.json'
    snapshot=json.loads(snapshot_path.read_text())
    if json.loads(archived.read_text())!=invocation:raise ValueError('historical invocation contents differ')
    digest=grid.sha(archived)
    if snapshot.get('invocation_sha256')!=digest or (invocation_sha256 is not None and invocation_sha256!=digest):raise ValueError('historical invocation checksum differs')
    entries=snapshot.get('files',[])
    documented={entry['path']:entry['sha256'] for entry in entries}
    if documented!=expected or len(documented)!=len(entries):raise ValueError('historical source inventory differs')
    resolved={}
    for name,value in expected.items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('historical source path is not a preserved relative path')
        resolved[str(root/relative)]=value
    validate_hashes(resolved)
    return dict(mode='immutable historical selection source snapshot',source_root=str(root),invocation_sha256=digest,snapshot_manifest_sha256=grid.sha(snapshot_path),original_source_sha256=expected,resolved_snapshot_sha256=resolved,current_export_sources_recorded_separately=True)


def selected_from_report(report):
    rows=report.get('outcomes',[])
    if report.get('completed_configurations')!=132 or len(rows)!=132 or len({(r['profile'],r['id']) for r in rows})!=132:raise ValueError('complete unique132-configuration report required')
    if report.get('final_fields_opened') is not False:raise ValueError('final data must remain unopened')
    if report['shared_selection_cohort']['shared_eligible']!=2360 or report['shared_selection_cohort']['planned']!=2370:raise ValueError('fixed global selection cohort changed')
    eligible=[r for r in rows if r['eligible']]
    if not eligible:raise ValueError('no eligible candidate; retain production v2')
    winner=max(eligible,key=lambda r:r['selection_key'])
    if winner!=report.get('selected'):raise ValueError('selected candidate differs from fixed validation rule')
    return winner


def validate_rank_parity(fields,reference,runtime,raise_on_failure=True):
    if len(fields)!=len(reference) or len(fields)!=len(runtime):raise ValueError('rank parity field count differs')
    result=dict(fields=len(fields),candidate_rows=0,max_abs_error=0.,score_tolerance_violations=0,full_order_mismatches=0,review_budget_mismatches=0,top100_membership_mismatches=0,reference_top1=0,runtime_top1=0,reference_top3=0,runtime_top3=0,first_mismatches=[])
    for f,left,right in zip(fields,reference,runtime):
        a,b=np.asarray(left),np.asarray(right)
        if a.shape!=b.shape or len(a)!=len(f['matches']):raise ValueError('rank parity candidate count differs')
        result['score_tolerance_violations']+=int(not np.allclose(a,b,rtol=2e-6,atol=2e-6))
        result['candidate_rows']+=len(a)
        if len(a):result['max_abs_error']=max(result['max_abs_error'],float(np.max(abs(a-b))))
        x,y=np.argsort(-a,kind='stable'),np.argsort(-b,kind='stable')
        order_changed=not np.array_equal(x,y)
        result['full_order_mismatches']+=int(order_changed)
        result['review_budget_mismatches']+=int(any(not np.array_equal(x[:k],y[:k]) for k in [1,3]))
        result['top100_membership_mismatches']+=int(set(x[:100].tolist())!=set(y[:100].tolist()))
        labels=np.asarray(f['matches'],int)
        for k in [1,3]:
            result['reference_top'+str(k)]+=len(set(labels[x[:k]].tolist())-{-1,-2})
            result['runtime_top'+str(k)]+=len(set(labels[y[:k]].tolist())-{-1,-2})
        if order_changed and len(result['first_mismatches'])<20:
            positions=np.flatnonzero(x!=y)
            result['first_mismatches'].append(dict(identity={k:f[k] for k in ['seed','parent_id','trajectory_id','brightness'] if k in f},affected_ranks_one_based=(positions+1).tolist(),reference_order=x.tolist(),runtime_order=y.tolist(),reference_scores=a.tolist(),runtime_scores=b.tolist(),max_reference_gap_at_changed_positions=float(np.max(abs(a[x[positions]]-a[y[positions]])))))
    result['protected_policy_passes']=not any(result[k] for k in ['score_tolerance_violations','review_budget_mismatches','top100_membership_mismatches']) and all(result['reference_top'+str(k)]==result['runtime_top'+str(k)] for k in [1,3])
    result['policy']='Root-approved BEFORE FINAL amendment:np.allclose rtol=2e-6 and atol=2e-6; identical ordered top1/top3 and known retention in every field; identical top100 membership; other full-order changes reported, never claimed exact'
    if not result['protected_policy_passes'] and raise_on_failure:raise RankParityError(result)
    return result



def peak_rss_mib_from_linux_status(status):
    for line in status.splitlines():
        if line.startswith('VmHWM:'):
            parts=line.split()
            if len(parts)!=3 or parts[2]!='kB':raise ValueError('unexpected Linux VmHWM units')
            return float(parts[1])/1024
    raise ValueError('Linux process VmHWM missing; inherited rusage is not a runtime-only memory measure')


def _runtime_probe(output):
    # Deliberately imports only runtime dependencies in a fresh one-thread CPU
    # process; parent contains sklearn/caches and is not a runtime memory probe.
    code=inspect.getsource(peak_rss_mib_from_linux_status)+"\n"+"""import json,sys,time,resource,numpy as np
from pathlib import Path
from ml_inference.model import load_ranker
p=Path(sys.argv[1]);r=load_ranker(p)
x=np.asarray(json.loads((p/'parity-reference.json').read_text())['features'],np.float32)[:1000]
for _ in range(3):r.score(x)
t=[]
for _ in range(20):
 a=time.perf_counter();r.score(x);t.append(time.perf_counter()-a)
print(json.dumps(dict(rows=len(x),repetitions=len(t),median_seconds=float(np.median(t)),p95_seconds=float(np.quantile(t,.95)),max_seconds=max(t),peak_rss_mib=peak_rss_mib_from_linux_status(Path('/proc/self/status').read_text()),inherited_rusage_maxrss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,memory_measurement='Linux VmHWM of the fresh runtime process; fork-inherited rusage retained separately',threads=dict(intra_op=1,inter_op=1))))
"""
    result=subprocess.run([sys.executable,'-c',code,str(output.resolve())],check=True,capture_output=True,text=True)
    probe=json.loads(result.stdout)
    probe['budgets']=dict(model_only_peak_rss_mib=1024,p95_1000row_seconds=1.,artifact_bytes=32*1024**2)
    if probe['peak_rss_mib']>1024 or probe['p95_seconds']>1:raise ValueError('isolated CPU/RSS model budget exceeded')
    return probe


def run(args):
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('export output must be a new empty candidate directory')
    report=json.loads(Path(args.selection_report).read_text());selected=selected_from_report(report)
    invocation=json.loads(Path(args.invocation_source).read_text())
    selection_source_binding=validate_invocation_sources(invocation,args.selection_source_root,invocation_sha256=grid.sha(args.invocation_source))
    inputs=report['training_manifests'][selected['cache']]
    current=json.loads((Path(selected['cache'])/'inputs.json').read_text())
    if current!=inputs:raise ValueError('fitting manifest changed since selection')
    validate_hashes(inputs['input_sha256']);resolved=validate_relocated_source_hashes(inputs['source_sha256'])
    validate_hashes({selected['estimator_cache_path']:selected['estimator_cache_sha256']})
    validate_hashes({report['baseline_synthetic_cache']:report['baseline_synthetic_sha256']})
    baseline_native=[];narrow_native=[]
    for p in report['native_cache_provenance']:
        validate_hashes({p['baseline_cache']:p['baseline_sha256'],p['candidate_cache']:p['candidate_sha256']})
        a,b=normalize_native_pair(grid.read(p['baseline_cache']),grid.read(p['candidate_cache']))
        baseline_native+=a['fields'];narrow_native+=b['fields']
    shared,denominators=shared_selection_cohort(baseline_native,narrow_native)
    if denominators!=report['shared_selection_cohort']:raise ValueError('shared trial cohort changed after selection')
    settings=inputs.get('detector_settings',grid.read(inputs['inputs']['native_train'][0])['detector_settings'])
    native=baseline_native if settings['psf_sigma']==1.2 else narrow_native
    paths=inputs['inputs'];synthetic=grid.read(paths['synthetic_validation'])['fields'];base_synthetic=grid.read(report['baseline_synthetic_cache'])['fields']
    train_synthetic=grid.read(paths['synthetic_train'])['fields'];train_native=[f for p in paths['native_train'] for f in grid.read(p)['fields']]
    if paths.get('native_artifacts'):
        from protocol_artifacts import training_rows
        artifacts=[f for p in paths['native_artifacts'] for f in grid.read(p)['fields']]
        x,y,w,origin=training_rows(train_synthetic,train_native,selected['config']['native_positive_mass'],artifacts,selected['config'].get('native_artifact_mass',0))
    else:
        from protocol import training_rows
        x,y,w,origin=training_rows(train_synthetic,train_native,selected['config']['native_positive_mass'])
    if len(x)!=selected['training']['rows'] or int(y.sum())!=selected['training']['positives']:raise ValueError('reconstructed fitting rows differ')
    forest=joblib.load(selected['estimator_cache_path'])
    expected_family='ExtraTreesClassifier' if selected['config']['family']=='extra' else 'RandomForestClassifier'
    if type(forest).__name__!=expected_family:raise ValueError('selected estimator family mismatch')
    graph=to_onnx(forest,x[:1],options={id(forest):{'zipmap':False}},target_opset=17)
    algorithm_version='motion-'+selected['config']['family']+'-v3-sigma'+str(settings['psf_sigma']).replace('.','')
    onnx.helper.set_model_props(graph,dict(schema_version='1',feature_names=json.dumps(list(FEATURE_NAMES)),class_labels='[0, 1]',score_kind=SCORE_KIND,detector_profile=json.dumps(settings,sort_keys=True),model_family=expected_family,algorithm_version_proposal=algorithm_version))
    onnx.checker.check_model(graph);artifact=output/'ranker.onnx';artifact.write_bytes(graph.SerializeToString())
    if artifact.stat().st_size>32*1024**2:raise ValueError('artifact exceeds32MiB')
    selection_copy=output/'system-validation-evaluation.json';shutil.copy2(args.selection_report,selection_copy)
    shutil.copy2(args.invocation_source,output/'selection-invocation-source.json')
    sources=list(Path('backend/inference/experiments/v3_ranker').glob('*.py'))+list(Path('backend/inference/experiments/v3_evaluation').glob('*.py'))+list(Path('backend/inference/experiments/v3_detection').glob('*.py'))+[Path('backend/inference')/p for p in ['ml_inference/model.py','ml_inference/detector.py','ml_inference/prepare.py','training/simulate_v2.py','training/train_v2.py','training/evaluate_background.py','training/train.py','training/weights.py']]
    source_inventory={str(p):grid.sha(p) for p in sources}
    manifest=dict(schema_version=1,release_state='development export in progress, FINAL UNOPENED',final_fields_opened=False,model_fitted_during_export=False,
        base_commit_at_export=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),selected_configuration=selected,training_manifest=inputs,
        fitting_rows=len(x),fitting_positive_rows=int(y.sum()),class_weight_totals={str(k):float(w[y==k].sum()) for k in [0,1]},resolved_fitting_sources=resolved,
        detector_profile=settings,model_family=expected_family,artifact_sha256=grid.sha(artifact),source_sha256=source_inventory,
        complete132_outcome_report_sha256=grid.sha(selection_copy),selection_source_binding=selection_source_binding,selection_invocation_sha256=grid.sha(output/'selection-invocation-source.json'),shared_selection_cohort=denominators,
        input_sha256={**inputs['input_sha256'],report['baseline_synthetic_cache']:report['baseline_synthetic_sha256'],**{p[k]:p[k.replace('_cache','_sha256')] for p in report['native_cache_provenance'] for k in ['baseline_cache','candidate_cache']}},
        versions=dict(python=platform.python_version(),numpy=np.__version__,sklearn=sklearn.__version__,onnx=onnx.__version__,onnxruntime=onnxruntime.__version__,skl2onnx=skl2onnx.__version__))
    write(output/'training-manifest.json',manifest)
    metadata=dict(schema_version=1,model_id='spherex-track-'+selected['config']['family']+'-v3',sha256=grid.sha(artifact),feature_names=list(FEATURE_NAMES),class_labels=[0,1],positive_class=1,score_kind=SCORE_KIND,
        status='experimental',release_state='development export in progress, FINAL UNOPENED',model_family=expected_family,detector_profile=settings,
        algorithm_version_proposal=algorithm_version,
        score_description='Arithmetic mean of class-1 weighted leaf fractions across the named randomized decision-tree ensemble; an uncalibrated ranking value, not a planet probability',training_manifest_sha256=grid.sha(output/'training-manifest.json'))
    write(output/'metadata.json',metadata);ranker=load_ranker(output);runtime=grid.v2adapter(ranker)
    ns=scores(native,forest);nr=scores(native,runtime);ss=scores(synthetic,forest);sr=scores(synthetic,runtime)
    parity=dict(native=validate_rank_parity(native,ns,nr,raise_on_failure=False),synthetic=validate_rank_parity(synthetic,ss,sr,raise_on_failure=False))
    if not all(r['protected_policy_passes'] for r in parity.values()):
        metadata['release_state']='EXPORT FAILED BEFORE FINAL';write(output/'metadata.json',metadata)
        write(output/'export-failure.json',dict(status='EXPORT FAILED BEFORE FINAL',selected_id=selected['id'],model_sha256=grid.sha(artifact),rank_parity=parity,final_fields_opened=False))
        raise RankParityError(parity)
    v2=load_ranker(args.baseline_model)
    if v2.metadata['sha256']!=V2_SHA:raise ValueError('frozen v2 baseline changed')
    ba=grid.v2adapter(v2);bn=scores(baseline_native,ba);bs=scores(base_synthetic,ba)
    bfields,bvalues=selection_subset(baseline_native,bn,shared);cfields,cvalues=selection_subset(native,nr,shared)
    actual_native=paired_native_report(bfields,cfields,bvalues,cvalues)
    actual_syn=grid.synthetic_report(synthetic,grid.scorer(synthetic,runtime))
    actual=dict(native=native_view(actual_native,'candidate'),synthetic=actual_syn)
    expected=selected['validation']
    for k in [1,3]:
        assert actual['native']['top'+str(k)]==expected['native']['top'+str(k)]
        assert actual['native']['macro_parent_recall'+str(k)]==expected['native']['macro_parent_recall'+str(k)]
        assert actual_syn[str(k)]['recovered_in_top_k']==expected['synthetic'][str(k)]['recovered_in_top_k']
    profile=report['profiles'][selected['profile']]
    eligible=qualifies(actual,profile['deployed_heuristic'],profile['baseline_v2']) and qualifies(actual,profile['candidate_profile_heuristic'],profile['baseline_v2'])
    if not eligible:raise ValueError('exported model no longer passes fixed validation eligibility')
    write(output/'export-validation.json',dict(score_and_protected_review_parity=parity,eligibility_after_export=eligible,shared_selection_actual=actual,full_native_system=paired_native_report(baseline_native,native,bn,nr),full_synthetic_system=paired_report(base_synthetic,synthetic,bs,sr),final_fields_opened=False))
    nv=np.asarray([r for f in native for r in f['features']],np.float32).reshape(-1,6);sv=np.asarray([r for f in synthetic for r in f['features']],np.float32).reshape(-1,6)
    probes=np.vstack([x[:256],sv[:1024],nv[:2048],np.random.default_rng(172019).uniform(0,300,(256,6))]).astype(np.float32)
    reference=forest.predict_proba(probes)[:,1];actual_scores=ranker.score(probes);np.testing.assert_allclose(reference,actual_scores,atol=2e-6,rtol=2e-6)
    write(output/'parity-reference.json',dict(features=probes.tolist(),scores=reference.tolist(),max_abs_error=float(np.max(abs(reference-actual_scores)))))
    write(output/'runtime-probe.json',_runtime_probe(output))
    prior=Path(args.prior_export_failure)
    if prior.is_file():
        shutil.copy2(prior,output/'prior-export-failure.json')
        manifest['export_guard_amendment']=dict(recorded_before_final=True,prior_failure_sha256=grid.sha(prior),reason='One float32 accumulation swap at ranks99/100 changed no protected review/output membership; original failure and artifact retained. No model refit or second candidate.',policy=parity['native']['policy'])
    manifest['release_state']='development-frozen candidate, FINAL UNOPENED'
    manifest['validation_export_policy']=parity['native']['policy']
    write(output/'training-manifest.json',manifest)
    metadata['release_state']='development-frozen candidate, FINAL UNOPENED'
    metadata['training_manifest_sha256']=grid.sha(output/'training-manifest.json')
    write(output/'metadata.json',metadata)
    freeze=dict(schema_version=1,release_state='development-frozen candidate, FINAL UNOPENED',frozen_utc=datetime.now(timezone.utc).isoformat(),final_fields_opened=False,
        model_id=metadata['model_id'],model_sha256=grid.sha(artifact),artifact_bytes=artifact.stat().st_size,model_family=expected_family,detector_profile=settings,
        selected_configuration=selected['id'],source_sha256=source_inventory,input_sha256=manifest['input_sha256'],source_snapshot_before_audit=report['source_snapshot'],
        file_sha256={p.name:grid.sha(p) for p in output.iterdir() if p.is_file()},trusted_external_root_freeze_required=True)
    write(output/'freeze.json',freeze)
    print('DEVELOPMENT_FROZEN '+json.dumps(freeze),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selection-report',required=True);p.add_argument('--invocation-source',required=True);p.add_argument('--selection-source-root');p.add_argument('--output',required=True)
    p.add_argument('--baseline-model',default='backend/inference/models');p.add_argument('--prior-export-failure',default='backend/inference/models/experiments/v3-selected-candidate/export-failure.json');run(p.parse_args())
