"""Bounded six-feature grouped-objective ablation; OLD DEVELOPMENT data only."""
from __future__ import annotations
import os
for _key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[_key]='1'
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import sys,json,gzip,hashlib,time,argparse
import numpy as np
import joblib
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
BASE=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(BASE/'backend/inference'),str(BASE/'backend/inference/experiments/v3_ranker')]
import train_grid as legacy
from protocol_artifacts import training_rows as legacy_rows
from ml_inference.model import load_ranker
from learning import labeled_rows,group_class_weights,pairwise_rows


def read(path):
    with gzip.open(path,'rt') as f:return json.load(f)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fields(paths):return [f for p in paths for f in read(p)['fields']]


def balanced_rows(st,nt,art,mass,cadence=False):
    blocks=[];ys=[];ws=[]
    for data,kind,budget in [(st,'synthetic',1),(nt,'native_moving',mass),(art,'native_stationary',mass)]:
        x,y,groups=labeled_rows(data,kind)
        if not budget or not len(x):continue
        w=group_class_weights(y,groups)
        if kind=='synthetic' and cadence:
            lookup={str(f['seed']):f['metadata']['cadence_family'] for f in data}
            strata=np.asarray([lookup[g] for g in groups])
            for label in [0,1]:
                strata_present=np.unique(strata[y==label])
                for c in strata_present:
                    mask=(y==label)&(strata==c);w[mask]/=w[mask].sum()*len(strata_present)
        else:
            for label in np.unique(y):w[y==label]/=w[y==label].sum()
        blocks.append(x);ys.append(y);ws.append(w*budget)
    x=np.vstack(blocks);y=np.concatenate(ys);w=np.concatenate(ws);w*=len(w)/w.sum()
    return x,y,w


def log_features(x):return np.sign(x)*np.log1p(np.abs(x))


class PairwiseUtility:
    def __init__(self,scaler,estimator):self.scaler=scaler;self.estimator=estimator
    def predict_proba(self,x):return self.estimator.predict_proba(self.scaler.transform(log_features(x)))


def evaluate(st,nt,predict,indices=None):
    def score(data):
        x=np.asarray([row for f in data for row in f['features']],np.float32).reshape(-1,6)
        if indices is not None:x=x[:,indices]
        values=predict(x) if len(x) else np.empty(0)
        lookup={};offset=0
        for f in data:
            length=len(f['features']);lookup[id(f)]=values[offset:offset+length];offset+=length
        return lambda f:lookup[id(f)]
    return dict(synthetic=legacy.synthetic_report(st,score(st)),native=legacy.native_report(nt,score(nt)))


def run(args):
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    cache=Path('/tmp/spaceapps-v3-detection');artroot=Path('/tmp/spaceapps-v3-ranker/native-artifacts')
    inputs=dict(synthetic_train=[str(cache/'synthetic-sigma08-train.json.gz')],synthetic_validation=[str(cache/'synthetic-sigma08-validation.json.gz')],native_train=[str(cache/f'native-train{i:02d}-short-v2-sigma08.json.gz') for i in range(1,9)],native_artifacts=[str(artroot/f'train{i:02d}-stationary-sigma0.8.json.gz') for i in range(1,9)],native_validation=[*[str(cache/f'native-validation{i:02d}-short-v2-sigma08.json.gz') for i in range(1,4)],*[str(cache/f'native-validation-stress{i:02d}-short-v1-sigma08.json.gz') for i in range(1,3)],*[str(cache/f'native-validation{i:02d}-expanded-v1-sigma12-default-sigma08.json.gz') for i in range(6,12)]])
    allpaths=[p for group in inputs.values() for p in group]
    for p in allpaths:
        d=read(p)
        assert d['detector_settings']['psf_sigma']==.8 and d['detector_settings']['min_speed']==.5
        assert d['partition'] in {'train','validation'}
    st=fields(inputs['synthetic_train']);sv=fields(inputs['synthetic_validation']);nt=fields(inputs['native_train']);nv=fields(inputs['native_validation']);art=fields(inputs['native_artifacts'])
    assert {f['parent_id'] for f in nt}.isdisjoint({f['parent_id'] for f in nv})
    assert {f['seed'] for f in st}.isdisjoint({f['seed'] for f in sv})
    # A single profile and immutable attribution flags define one shared cohort.
    cohort=[dict(parent_id=f['parent_id'],seed=f['seed'],trajectory_id=f['trajectory_id'],brightness=f['brightness']) for f in nv if f['attribution_eligible']]
    configs=[dict(kind='forest',weight=w,mass=mass,drop_epoch=drop) for w,mass,drop in [('c13',2,False),('group',0,False),('group',.5,False),('group',2,False),('cadence_group',2,False),('c13',2,True),('group',2,True)]]+[dict(kind='pairwise_linear',C=c,drop_epoch=False) for c in [.01,.1,1.]]
    manifest=dict(schema_version=1,purpose=__doc__,scope='OLD DEVELOPMENT ONLY; no old/new FINAL accessed',planned_configurations=configs,inputs=inputs,input_sha256={p:sha(p) for p in allpaths},source_sha256={str(p):sha(p) for p in [Path(__file__),Path(__file__).with_name('learning.py'),Path(legacy.__file__),BASE/'backend/inference/experiments/v3_ranker/protocol.py',BASE/'backend/inference/experiments/v3_ranker/protocol_artifacts.py']},native_shared_cohort=cohort,native_shared_cohort_sha256=hashlib.sha256(json.dumps(cohort,sort_keys=True).encode()).hexdigest(),score_semantics='uncalibrated monotone ranking utility; pairwise sigmoid is not calibration',unknown_native_labels_used=False)
    (output/'inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
    c13=load_ranker(BASE/'releases/v3/model')
    baseline=evaluate(sv,nv,c13.score)
    print(json.dumps(dict(stage='baseline',native=baseline['native'],synthetic=baseline['synthetic'])),flush=True)
    rowcache={}
    for weight,mass in {(c['weight'],c['mass']) for c in configs if c['kind']=='forest'}:
        if weight=='c13':x,y,w,_=legacy_rows(st,nt,mass,art,mass)
        else:x,y,w=balanced_rows(st,nt,art,mass,cadence=weight=='cadence_group')
        rowcache[weight,mass]=(x,y,w)
    sx,_,_=labeled_rows(st,'synthetic');scaler=StandardScaler().fit(log_features(sx))
    transformed=[dict(f,features=scaler.transform(log_features(np.asarray(f['features'],float))).tolist()) if f['features'] else f for f in st]
    px,py,pw=pairwise_rows(transformed)
    def one(config):
        started=time.monotonic();identifier=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()[:16]
        if config['kind']=='forest':
            x,y,w=rowcache[config['weight'],config['mass']];indices=list(range(1,6)) if config['drop_epoch'] else list(range(6))
            model=ExtraTreesClassifier(n_estimators=160,max_depth=16,min_samples_leaf=12,max_features='sqrt',max_leaf_nodes=512,n_jobs=1,random_state=20261115).fit(x[:,indices],y,sample_weight=w)
            report=evaluate(sv,nv,lambda a:model.predict_proba(a)[:,1],indices)
            training=dict(rows=len(x),positive_rows=int(y.sum()),weights_min=float(w.min()),weights_max=float(w.max()),feature_importances=model.feature_importances_.tolist())
        else:
            model=PairwiseUtility(scaler,LogisticRegression(C=config['C'],fit_intercept=False,max_iter=300,solver='lbfgs').fit(px,py,sample_weight=pw))
            report=evaluate(sv,nv,lambda a:model.predict_proba(a)[:,1]);training=dict(pair_rows=len(px),native_pairs=0,reason='Native moving-trial competitors remain UNKNOWN; no native pair labels are assigned',coefficient=model.estimator.coef_.tolist())
        path=output/(identifier+'.joblib');joblib.dump(model,path,compress=3)
        result=dict(id=identifier,config=config,validation=report,training=training,elapsed_seconds=time.monotonic()-started,estimator=dict(path=str(path),sha256=sha(path)))
        (output/(identifier+'.json')).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        return result
    report=dict(schema_version=1,baseline=baseline,cohort_sha256=manifest['native_shared_cohort_sha256'],experiments=[])
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(one,c) for c in configs]):
            r=future.result();report['experiments'].append(r)
            (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
            n=r['validation']['native'];s=r['validation']['synthetic'];print(json.dumps(dict(completed=len(report['experiments']),config=r['config'],native_K1=n['top1'],native_K3=n['top3'],native_macro_K1=n['macro_parent_recall1'],native_macro_K3=n['macro_parent_recall3'],synthetic_K1=s['1']['recovered_in_top_k'],synthetic_K3=s['3']['recovered_in_top_k'],synthetic_cadence_K1=s['macro_cadence_recall1'],synthetic_cadence_K3=s['macro_cadence_recall3'],seconds=r['elapsed_seconds'])),flush=True)
    print('COMPLETE '+str(output/'report.json'),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',default='/tmp/spaceapps-v4-ranker/stage1-six');p.add_argument('--workers',type=int,default=4);run(p.parse_args())
