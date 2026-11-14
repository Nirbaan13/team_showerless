"""Historical SAME-DETECTOR development ablations; release freezing disabled.

Use select_system.py for deployed-system comparison and final candidate selection.
No estimator refit or final image read. Historical source remains snapshotted.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import platform
import time
import joblib
import numpy as np
import onnx
import onnxruntime
import sklearn
import skl2onnx
from skl2onnx import to_onnx
import train_grid as grid
from protocol import training_rows
from ml_inference.model import FEATURE_NAMES,SCORE_KIND,load_ranker


def write(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def key(r):
    n=r['native'];s=r['synthetic']
    return [n['macro_parent_recall1'],n['macro_parent_recall3'],s['macro_cadence_recall1'],s['macro_cadence_recall3'],s['3']['track_average_precision'] or 0]


def qualifies(r,baseline,v2):
    n=r['native'];s=r['synthetic']
    return n['macro_parent_recall1']>=max(baseline['native']['macro_parent_recall1'],v2['native']['macro_parent_recall1']) and n['macro_parent_recall3']>=max(baseline['native']['macro_parent_recall3'],v2['native']['macro_parent_recall3']) and s['macro_cadence_recall1']>=max(baseline['synthetic']['macro_cadence_recall1'],v2['synthetic']['macro_cadence_recall1']) and s['macro_cadence_recall3']>=max(baseline['synthetic']['macro_cadence_recall3'],v2['synthetic']['macro_cadence_recall3'])


def run(args):
    if not args.evaluate_only:
        raise ValueError('Historical same-detector evaluator cannot freeze release candidates; use select_system.py')
    from selection_integrity import validate_hashes,validate_relocated_source_hashes
    cache=Path(args.cache);inputs=json.loads((cache/'inputs.json').read_text());paths=inputs['inputs']
    validate_hashes(inputs['input_sha256'])
    validate_relocated_source_hashes(inputs['source_sha256'])
    records=[json.loads(p.read_text()) for p in sorted(cache.glob('*.json')) if p.name not in ['inputs.json','grid-progress.json']]
    expected=inputs.get('planned_configurations',48)
    if len(records)!=expected:raise ValueError(f'all {expected} primary experiments required, found {len(records)}')
    validation=args.native_validation or paths['native_validation']
    grid.initialize((paths['synthetic_train'],paths['synthetic_validation'],paths['native_train'],validation))
    st,sv,nt,nv=grid.DATA
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    baseline=dict(native=grid.native_report(nv,lambda f:np.asarray(f['baseline'])),synthetic=grid.synthetic_report(sv,lambda f:np.asarray(f['baseline'])))
    v2ranker=load_ranker(args.baseline_model)
    v2=grid.metrics(sv,nv,grid.v2adapter(v2ranker))
    outcomes=[]
    for i,r in enumerate(records,1):
        p=Path(r['estimator_cache_path'])
        if grid.sha(p)!=r['estimator_cache_sha256']:raise ValueError('cachedestimatorchecksum mismatch')
        forest=joblib.load(p)
        result=grid.metrics(sv,nv,forest)
        outcomes.append(dict(id=r['id'],config=r['config'],training=r['training'],validation=result,selection_key=key(result),eligible=qualifies(result,baseline,v2)))
        print(json.dumps(dict(index=i,id=r['id'],native=result['native'],eligible=outcomes[-1]['eligible'])),flush=True)
    eligible=[r for r in outcomes if r['eligible']]
    report=dict(baseline=baseline,v2=v2,experiments=outcomes,all_primary_configurations_reported=True,final_fields_opened=False)
    write(output/'validation-evaluation.json',report)
    if not eligible:raise ValueError('no forest meets nativebothbudgets andsyntheticbaseline safeguards')
    selected=max(eligible,key=lambda r:r['selection_key'])
    if args.evaluate_only:
        write(output/'selected-development.json',selected)
        print('DEVELOPMENT_SELECTION '+json.dumps(selected),flush=True)
        return
    selected_record=next(r for r in records if r['id']==selected['id']);forest=joblib.load(selected_record['estimator_cache_path'])
    artifact_paths=paths.get('native_artifacts',[])
    if artifact_paths:
        from protocol_artifacts import training_rows as artifact_training_rows
        artifacts=[f for p in artifact_paths for f in grid.read(p)['fields']]
        x,y,w,origin=artifact_training_rows(st,nt,selected['config']['native_positive_mass'],artifacts,selected['config'].get('native_artifact_mass',0))
    else:
        x,y,w,origin=training_rows(st,nt,selected['config']['native_positive_mass'])
    graph=to_onnx(forest,x[:1],options={id(forest):{'zipmap':False}},target_opset=17)
    onnx.helper.set_model_props(graph,dict(schema_version='1',feature_names=json.dumps(list(FEATURE_NAMES)),class_labels='[0, 1]',score_kind=SCORE_KIND))
    onnx.checker.check_model(graph);artifact=output/'ranker.onnx';artifact.write_bytes(graph.SerializeToString())
    if artifact.stat().st_size>32*1024**2:raise ValueError('artifactexceeds32MiB')
    source_paths=list(Path('backend/inference/experiments/v3_ranker').glob('*.py'))+[Path('backend/inference')/p for p in ['ml_inference/model.py','ml_inference/detector.py','ml_inference/prepare.py','training/simulate_v2.py','training/train_v2.py','training/evaluate_background.py','training/train.py','training/weights.py']]
    cachepaths=[paths['synthetic_train'],paths['synthetic_validation'],*paths['native_train'],*validation,*artifact_paths]
    partition_provenance={p:{k:v for k,v in grid.read(p).items() if k not in ['fields','control']} for p in cachepaths}
    write(output/'data-partitions.json',partition_provenance)
    manifest=dict(schema_version=1,model_generation=3,detector_settings=inputs.get('detector_settings',grid.read(paths['native_train'][0])['detector_settings']),selected=selected,training_source_freeze=inputs,training_candidates=len(x),training_positive_candidates=int(y.sum()),
                  input_sha256={p:grid.sha(p) for p in cachepaths},source_sha256={str(p):grid.sha(p) for p in source_paths},
                  feature_names=list(FEATURE_NAMES),selected_parameters=forest.get_params(),native_training_parents=sorted({f['parent_id'] for f in nt}),native_validation_parents=sorted({f['parent_id'] for f in nv}),
                  final_fields_opened=False,refit_validation=False,known_labels_only=True,native_unknowns_used_as_negatives=False,
                  selection_rule='Development amendment before expanded eleven-parent scoring: exclude native macro K1/K3 or synthetic macro-cadence K1/K3 below either heuristic or v2; then maximize native validation macro-parent K1, K3, synthetic macro K1, K3, AP',
                  artifacts_include_estimator_pickle=False,versions=dict(python=platform.python_version(),numpy=np.__version__,sklearn=sklearn.__version__,skl2onnx=skl2onnx.__version__,onnx=onnx.__version__,onnxruntime=onnxruntime.__version__))
    write(output/'training-manifest.json',manifest)
    family=selected['config']['family']
    metadata=dict(schema_version=1,model_id='spherex-track-'+family+'-v3',model_family=type(forest).__name__,training_detector_settings=manifest['detector_settings'],sha256=grid.sha(artifact),feature_names=list(FEATURE_NAMES),class_labels=[0,1],positive_class=1,score_kind=SCORE_KIND,status='experimental',score_description='Mean class-1 weighted leaf fraction across randomized decision trees; uncalibrated ranking, not planet probability',training_manifest_sha256=grid.sha(output/'training-manifest.json'))
    write(output/'metadata.json',metadata);ranker=load_ranker(output)
    svx=np.asarray([r for f in sv for r in f['features']],np.float32).reshape(-1,6)
    nvx=np.asarray([r for f in nv for r in f['features']],np.float32).reshape(-1,6)
    probes=np.vstack([x[:256],svx[:1024],nvx[:2048],np.random.default_rng(172019).uniform(0,300,(256,6))]).astype(np.float32)
    reference=forest.predict_proba(probes)[:,1];actual=ranker.score(probes)
    np.testing.assert_allclose(reference,actual,atol=2e-6,rtol=2e-6)
    write(output/'parity-reference.json',dict(features=probes.tolist(),scores=reference.tolist(),max_abs_error=float(np.max(abs(reference-actual)))))
    frozen_metrics=grid.metrics(sv,nv,grid.v2adapter(ranker))
    for cohort in ['native','synthetic']:
        if cohort=='native':
            assert frozen_metrics[cohort]['top1']==selected['validation'][cohort]['top1']
            assert frozen_metrics[cohort]['top3']==selected['validation'][cohort]['top3']
        else:
            for k in ['1','3']:assert frozen_metrics[cohort][k]['recovered_in_top_k']==selected['validation'][cohort][k]['recovered_in_top_k']
    controls={}
    for p in validation:
        data=grid.read(p);rows=np.asarray(data['control']['features'],np.float32).reshape(-1,6)
        scores=ranker.score(rows)
        controls[data['parent_id']]=dict(labels='unknown physicalidentities; never fittingnegatives',features=rows.tolist(),scores=scores.tolist(),model_order=np.argsort(-scores,kind='stable').tolist())
    write(output/'unmodified-validation-controls.json',controls)
    frozen=dict(model_id=metadata['model_id'],frozen_utc=datetime.now(timezone.utc).isoformat(),sha256=metadata['sha256'],artifact_bytes=artifact.stat().st_size,final_fields_opened=False,selected_configuration=selected['id'],selection_key=selected['selection_key'],source_sha256=manifest['source_sha256'],input_sha256=manifest['input_sha256'],file_sha256={p.name:grid.sha(p) for p in output.iterdir() if p.is_file() and p.name!='freeze.json'})
    write(output/'freeze.json',frozen)
    print('FROZEN '+json.dumps(frozen),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',required=True);p.add_argument('--output',required=True);p.add_argument('--evaluate-only',action='store_true')
    p.add_argument('--native-validation',nargs='+');p.add_argument('--baseline-model',default='backend/inference/models')
    run(p.parse_args())
