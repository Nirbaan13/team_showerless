"""Bounded v3 forest ablation on cached whole-field train/validation rows."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import platform
import time
import numpy as np
from sklearn.ensemble import RandomForestClassifier,ExtraTreesClassifier
import sklearn
from training.train import evaluate
from ml_inference.model import FEATURE_NAMES,SCORE_KIND,load_ranker
from protocol import training_rows,recovery_report

DATA=None

def read(path):
    with gzip.open(path,'rt') as f:return json.load(f)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def initialize(paths):
    global DATA
    synthetic_train,synthetic_val,native_train,native_val=paths
    st=read(synthetic_train);sv=read(synthetic_val)
    nt=[read(p) for p in native_train];nv=[read(p) for p in native_val]
    groups_t={p['parent_id'] for p in nt};groups_v={p['parent_id'] for p in nv}
    if groups_t & groups_v:raise ValueError('native parent field leakage')
    train_hashes={s['sha256'] for p in nt for s in p['input_sources']}
    val_hashes={s['sha256'] for p in nv for s in p['input_sources']}
    if train_hashes & val_hashes:raise ValueError('native exposure leakage')
    if set(st['seeds']) & set(sv['seeds']):raise ValueError('synthetic field leakage')
    if any(p['partition']!='train' for p in nt) or any(p['partition']!='validation' for p in nv):raise ValueError('partition label mismatch')
    DATA=(st['fields'],sv['fields'],[f for p in nt for f in p['fields']],[f for p in nv for f in p['fields']])

def scorer(fields,forest):
    rows=np.asarray([r for f in fields for r in f['features']],np.float32).reshape(-1,6)
    values=forest.predict_proba(rows)[:,1] if len(rows) else np.asarray([])
    offset=0;lookup={}
    for f in fields:
        n=len(f['features']);lookup[id(f)]=values[offset:offset+n];offset+=n
    return lambda f:lookup[id(f)]

def native_report(fields,score):
    parents=sorted({f['parent_id'] for f in fields})
    reports={p:recovery_report([f for f in fields if f['parent_id']==p],score) for p in parents}
    summary=recovery_report(fields,score)
    summary['macro_parent_recall1']=float(np.mean([r['recall1'] for r in reports.values() if r['recall1'] is not None])) if reports else None
    summary['macro_parent_recall3']=float(np.mean([r['recall3'] for r in reports.values() if r['recall3'] is not None])) if reports else None
    summary['by_parent']=reports
    coverage=[f for f in fields if f['usable_center_epochs']>=3]
    summary['finite_center_coverage_ge3']=recovery_report(coverage,score)
    return summary

def synthetic_report(fields,score):
    report={str(k):evaluate(fields,score,k) for k in [1,3]}
    for k in [1,3]:
        report['macro_cadence_recall'+str(k)]=float(np.mean([evaluate([f for f in fields if f['metadata']['cadence_family']==c],score,k)['top_k_recall'] for c in range(4)]))
    return report

def metrics(sv,nv,forest):
    return dict(synthetic=synthetic_report(sv,scorer(sv,forest)),native=native_report(nv,scorer(nv,forest)))

def run_one(config):
    st,sv,nt,nv=DATA
    family,leaf,depth,features,mass=config
    x,y,w,origin=training_rows(st,nt,mass)
    cls=RandomForestClassifier if family=='rf' else ExtraTreesClassifier
    params=dict(n_estimators=160,min_samples_leaf=leaf,max_depth=depth,max_features=features,
                max_leaf_nodes=512,n_jobs=1,random_state=20261114)
    started=time.monotonic();forest=cls(**params).fit(x,y,sample_weight=w)
    result=metrics(sv,nv,forest)
    n=result['native'];s=result['synthetic']
    key=(n['macro_parent_recall1'] or 0,n['macro_parent_recall3'] or 0,s['macro_cadence_recall1'],s['macro_cadence_recall3'],s['3']['track_average_precision'] or 0)
    return dict(config=dict(family=family,native_positive_mass=mass,parameters=params),selection_key=list(key),validation=result,
                training=dict(rows=len(x),positives=int(y.sum()),native_positive_rows=sum(o!='synthetic' for o in origin),
                              source_feature_importances=dict(zip(FEATURE_NAMES,map(float,forest.feature_importances_)))),
                elapsed_seconds=time.monotonic()-started)

def run(args):
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    paths=(args.synthetic_train,args.synthetic_validation,args.native_train,args.native_validation)
    initialize(paths)
    st,sv,nt,nv=DATA
    if not nv:raise ValueError('native validation fields required before selection')
    baseline=dict(synthetic=synthetic_report(sv,lambda f:np.asarray(f['baseline'])),native=native_report(nv,lambda f:np.asarray(f['baseline'])))
    v2=load_ranker(args.baseline_model)
    v2report=dict(synthetic=synthetic_report(sv,scorer(sv,v2adapter(v2))),native=native_report(nv,scorer(nv,v2adapter(v2))))
    configs=list(itertools.product(['rf','extra'],[(4,12),(12,16),(32,None)],[1.,'sqrt'],args.native_masses))
    configs=[(family,leaf,depth,features,mass) for family,(leaf,depth),features,mass in configs]
    records=[]
    with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(paths,)) as pool:
        for i,r in enumerate(pool.map(run_one,configs),1):
            records.append(r)
            print(json.dumps(dict(index=i,total=len(configs),config=r['config'],key=r['selection_key'],native=r['validation']['native'],elapsed_seconds=r['elapsed_seconds'])),flush=True)
            (output/'grid-progress.json').write_text(json.dumps(dict(baseline=baseline,v2=v2report,experiments=records),indent=2,allow_nan=False)+'\n')
    selected=max(records,key=lambda r:r['selection_key'])
    family=selected['config']['family'];mass=selected['config']['native_positive_mass']
    x,y,w,origin=training_rows(st,nt,mass)
    cls=RandomForestClassifier if family=='rf' else ExtraTreesClassifier
    forest=cls(**selected['config']['parameters']).fit(x,y,sample_weight=w)
    import onnx
    import skl2onnx
    from skl2onnx import to_onnx
    graph=to_onnx(forest,x[:1],options={id(forest):{'zipmap':False}},target_opset=17)
    onnx.helper.set_model_props(graph,dict(schema_version='1',feature_names=json.dumps(list(FEATURE_NAMES)),class_labels='[0, 1]',score_kind=SCORE_KIND))
    onnx.checker.check_model(graph);artifact=output/'ranker.onnx';artifact.write_bytes(graph.SerializeToString())
    if artifact.stat().st_size>32*1024**2:raise ValueError('artifact exceeds32MiB')
    source_paths=[Path(p) for p in [__file__,'backend/inference/experiments/v3_ranker/protocol.py','backend/inference/experiments/v3_ranker/cache_native.py','backend/inference/experiments/v3_ranker/cache_synthetic.py','backend/inference/ml_inference/model.py','backend/inference/ml_inference/detector.py','backend/inference/ml_inference/prepare.py','backend/inference/training/simulate_v2.py','backend/inference/training/evaluate_background.py','backend/inference/training/train.py','backend/inference/training/weights.py']]
    manifest=dict(schema_version=1,model_generation=3,selected=selected,experiments=records,baseline=baseline,v2=v2report,
                  input_sha256={p:sha(p) for p in [args.synthetic_train,args.synthetic_validation,*args.native_train,*args.native_validation]},
                  source_sha256={str(p):sha(p) for p in source_paths},feature_names=list(FEATURE_NAMES),
                  selected_parameters=forest.get_params(),training=dict(rows=len(x),positive_rows=int(y.sum()),native_parents=sorted({f['parent_id'] for f in nt})),
                  native_validation_parents=sorted({f['parent_id'] for f in nv}),refit_validation=False,final_fields_opened=False,
                  selection_rule='native validation macro-parent recall1 then recall3 then synthetic validation macro-cadence recall1,recall3,candidateAP',
                  known_labels_only=True,native_unknowns_used_as_negatives=False,
                  versions=dict(python=platform.python_version(),numpy=np.__version__,sklearn=sklearn.__version__,skl2onnx=skl2onnx.__version__),
                  score_semantics='mean class1 weighted leaf fraction across decision trees; uncalibrated ranking only')
    (output/'training-manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    metadata=dict(schema_version=1,model_id='spherex-track-'+family+'-v3-development',sha256=sha(artifact),feature_names=list(FEATURE_NAMES),class_labels=[0,1],positive_class=1,score_kind=SCORE_KIND,status='experimental',score_description='Mean class1 weighted leaf fraction across trees; uncalibrated ranking only',training_manifest_sha256=sha(output/'training-manifest.json'))
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    ranker=load_ranker(output)
    probes=np.vstack([x[:256],np.asarray([r for f in sv for r in f['features']],np.float32)[:1024],np.asarray([r for f in nv for r in f['features']],np.float32)[:1024],np.random.default_rng(172019).uniform(0,300,(256,6))]).astype(np.float32)
    reference=forest.predict_proba(probes)[:,1];actual=ranker.score(probes)
    np.testing.assert_allclose(reference,actual,atol=2e-6,rtol=2e-6)
    (output/'parity-reference.json').write_text(json.dumps(dict(features=probes.tolist(),scores=reference.tolist(),max_abs_error=float(np.max(abs(reference-actual)))),indent=2)+'\n')
    freeze=dict(model_id=metadata['model_id'],sha256=metadata['sha256'],artifact_bytes=artifact.stat().st_size,final_fields_opened=False,selection_key=selected['selection_key'],frozen_files={p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='freeze.json'})
    (output/'freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    print('FROZEN '+json.dumps(freeze),flush=True)

class v2adapter:
    def __init__(self,r):self.r=r
    def predict_proba(self,x):
        p=self.r.score(x)
        return np.column_stack([1-p,p])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--synthetic-train',required=True);p.add_argument('--synthetic-validation',required=True)
    p.add_argument('--native-train',nargs='+',default=[]);p.add_argument('--native-validation',nargs='+',default=[])
    p.add_argument('--native-masses',nargs='+',type=float,default=[0,.5,2,8])
    p.add_argument('--baseline-model',default='backend/inference/models');p.add_argument('--workers',type=int,default=6)
    p.add_argument('--output',required=True)
    run(p.parse_args())
