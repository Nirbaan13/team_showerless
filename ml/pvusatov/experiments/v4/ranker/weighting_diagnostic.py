"""Isolate sample-weight components and repeat fixed seeds on old DEV only."""
from __future__ import annotations
import os
for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[name]='1'
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json,hashlib,time
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from learning import labeled_rows,group_class_weights
import stage1


def ordinary_rows(st,nt,art,mass=2):
    blocks=[];labels=[];weights=[]
    for data,kind,budget in [(st,'synthetic',1),(nt,'native_moving',mass),(art,'native_stationary',mass)]:
        x,y,groups=labeled_rows(data,kind);w=np.ones(len(y))
        if kind=='synthetic':
            for label in [0,1]:w[y==label]/=sum(y==label)
        else:
            counts=Counter(groups);w=np.asarray([1/(len(counts)*counts[g]) for g in groups])
        blocks.append(x);labels.append(y);weights.append(w*budget)
    x=np.vstack(blocks);y=np.concatenate(labels);w=np.concatenate(weights);w*=len(w)/w.sum()
    return x,y,w


def concentration(weights,labels,groups):
    result={};groups=np.asarray(groups)
    for label in [0,1]:
        select=labels==label;mass=np.asarray([weights[select&(groups==group)].sum() for group in np.unique(groups[select])]);mass/=mass.sum()
        result[str(label)]=dict(groups=len(mass),effective_groups=float(1/np.sum(mass*mass)),max_group_fraction=float(mass.max()),row_weight_effective_rows=float(weights[select].sum()**2/np.square(weights[select]).sum()))
    return result


def main():
    initial=Path('/tmp/spaceapps-v4-ranker/stage1-six');manifest=json.loads((initial/'inputs.json').read_text());inputs=manifest['inputs']
    st=stage1.fields(inputs['synthetic_train']);sv=stage1.fields(inputs['synthetic_validation']);nt=stage1.fields(inputs['native_train']);nv=stage1.fields(inputs['native_validation']);art=stage1.fields(inputs['native_artifacts'])
    for path,expected in manifest['input_sha256'].items():assert stage1.sha(path)==expected
    original=stage1.legacy_rows(st,nt,2,art,2)[:3]
    uniform=ordinary_rows(st,nt,art)
    grouped=stage1.balanced_rows(st,nt,art,2)
    assert np.array_equal(original[0],uniform[0]) and np.array_equal(uniform[0],grouped[0])
    x,y,gw=grouped;epoch=np.minimum(x[:,0].astype(int),5);nsynthetic=sum(len(f['features']) for f in st);synth=np.arange(len(x))<nsynthetic
    ge=gw.copy()
    for epoch_group in np.unique(epoch[synth]):
        p=synth&(y==1)&(epoch==epoch_group);n=synth&(y==0)&(epoch==epoch_group)
        if p.any() and n.any():
            ratio=(gw[p].sum()/gw[synth&(y==1)].sum())/(gw[n].sum()/gw[synth&(y==0)].sum());ge[n]*=np.clip(ratio,.05,50.)
    ge[synth&(y==0)]*=gw[synth&(y==0)].sum()/ge[synth&(y==0)].sum();ge*=len(ge)/ge.sum()
    policies=dict(original_epoch=original,row_uniform=uniform,field_uniform=grouped,field_then_epoch=(x,y,ge))
    groups=[str(f['seed']) for f in st for row in f['features']]
    summary={name:concentration(w[:nsynthetic],labels[:nsynthetic],groups) for name,(_,labels,w) in policies.items()}
    configurations=[dict(policy=name,seed=seed) for name in policies for seed in [20261115,20261116,20261117,20261118]]
    output=Path('/tmp/spaceapps-v4-ranker/weighting-diagnostic');output.mkdir(exist_ok=True)
    invocation=dict(schema_version=4,purpose=__doc__,input_manifest_sha256=stage1.sha(initial/'inputs.json'),source_sha256={str(p):stage1.sha(p) for p in [Path(__file__),Path(stage1.__file__),Path(__file__).with_name('learning.py')]},planned_configurations=configurations,synthetic_train_weight_concentration=summary)
    (output/'inputs.json').write_text(json.dumps(invocation,indent=2)+'\n')
    def one(config):
        started=time.monotonic();x,y,w=policies[config['policy']]
        estimator=ExtraTreesClassifier(n_estimators=160,max_depth=16,min_samples_leaf=12,max_features='sqrt',max_leaf_nodes=512,n_jobs=1,random_state=config['seed']).fit(x,y,sample_weight=w)
        result=stage1.evaluate(sv,nv,lambda a:estimator.predict_proba(a)[:,1]);return dict(config=config,validation=result,elapsed_seconds=time.monotonic()-started)
    report=dict(invocation=invocation,experiments=[])
    with ThreadPoolExecutor(max_workers=4) as pool:
        for task in as_completed([pool.submit(one,c) for c in configurations]):
            r=task.result();report['experiments'].append(r);n=r['validation']['native'];s=r['validation']['synthetic'];print(json.dumps(dict(completed=len(report['experiments']),config=r['config'],native=[n['top1'],n['top3']],synthetic=[s['1']['recovered_in_top_k'],s['3']['recovered_in_top_k']])),flush=True)
            (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print('COMPLETE',flush=True)

if __name__=='__main__':main()
