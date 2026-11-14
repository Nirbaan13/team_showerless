"""Profile-matched sigma0.8 forest grid with attributable stationary artifacts.

84 primary configurations: 12 forest profiles times native mass0 once, and
native masses0.5/2/8 each with stationary-artifact mass0 or equal native mass.
Unknown real rows are never negatives. Estimator pickles remain scratch only.
"""
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import time
import joblib
from sklearn.ensemble import RandomForestClassifier,ExtraTreesClassifier
import train_grid as grid
from protocol_artifacts import training_rows

ARTIFACTS=None
CACHE=None

def initialize(paths,artifact_paths,cache):
    global ARTIFACTS,CACHE
    grid.initialize(paths)
    all_paths=[paths[0],paths[1],*paths[2],*paths[3],*artifact_paths]
    for p in all_paths:
        d=grid.read(p)
        if d['detector_settings']['psf_sigma']!=.8 or d['detector_settings']['min_snr']!=4:raise ValueError('mixed detector profile forbidden')
    ARTIFACTS=[f for p in artifact_paths for f in grid.read(p)['fields']]
    if {f['parent_id'] for f in ARTIFACTS}-{f['parent_id'] for f in grid.DATA[2]}:raise ValueError('artifact group outside train')
    CACHE=Path(cache)

def fit(config):
    family,leaf,depth,features,mass,artifact_mass=config
    identifier=hashlib.sha256(json.dumps(config).encode()).hexdigest()[:16]
    st,sv,nt,nv=grid.DATA
    x,y,w,origin=training_rows(st,nt,mass,ARTIFACTS,artifact_mass)
    params=dict(n_estimators=160,min_samples_leaf=leaf,max_depth=depth,max_features=features,max_leaf_nodes=512,n_jobs=1,random_state=20261114)
    cls=RandomForestClassifier if family=='rf' else ExtraTreesClassifier
    started=time.monotonic();forest=cls(**params).fit(x,y,sample_weight=w)
    path=CACHE/(identifier+'.joblib');joblib.dump(forest,path,compress=3)
    report=grid.metrics(sv,nv,forest)
    record=dict(id=identifier,config=dict(family=family,native_positive_mass=mass,native_artifact_mass=artifact_mass,parameters=params),validation=report,
                training=dict(rows=len(x),positives=int(y.sum()),native_positive_rows=sum(o.startswith('native:') for o in origin),native_artifact_negative_rows=sum(o.startswith('native_artifact:') for o in origin)),
                estimator_cache_path=str(path),estimator_cache_sha256=grid.sha(path),elapsed_seconds=time.monotonic()-started)
    (CACHE/(identifier+'.json')).write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    return record

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--synthetic-train',required=True);p.add_argument('--synthetic-validation',required=True)
    p.add_argument('--native-train',nargs='+',required=True);p.add_argument('--native-validation',nargs='+',required=True)
    p.add_argument('--native-artifacts',nargs='+',required=True);p.add_argument('--cache',required=True);p.add_argument('--workers',type=int,default=6);args=p.parse_args()
    paths=(args.synthetic_train,args.synthetic_validation,args.native_train,args.native_validation)
    cache=Path(args.cache);cache.mkdir(parents=True,exist_ok=True)
    manifest=dict(planned_configurations=84,detector_settings=grid.read(args.synthetic_train)['detector_settings'],inputs=dict(synthetic_train=args.synthetic_train,synthetic_validation=args.synthetic_validation,native_train=args.native_train,native_validation=args.native_validation,native_artifacts=args.native_artifacts),
                  input_sha256={s:grid.sha(s) for s in [args.synthetic_train,args.synthetic_validation,*args.native_train,*args.native_validation,*args.native_artifacts]},
                  source_sha256={str(s):grid.sha(s) for s in [Path(__file__),Path(grid.__file__),Path('backend/inference/experiments/v3_ranker/protocol.py'),Path('backend/inference/experiments/v3_ranker/protocol_artifacts.py')]},
                  score_semantics='Mean class-1 weighted leaf fraction; uncalibrated ranking',runtime_pickle_forbidden=True,
                  artifact_truth='Fixed sky source, constant flux law shared with moving positives, actual native WCS/ePSF; no imposed velocity/jitter; strict attribution and preexisting-control exclusion')
    (cache/'inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
    configs=[]
    for family,(leaf,depth),features in itertools.product(['rf','extra'],[(4,12),(12,16),(32,None)],[1.,'sqrt']):
        configs.append((family,leaf,depth,features,0,0))
        for mass,artifact in itertools.product([.5,2,8],[False,True]):configs.append((family,leaf,depth,features,mass,mass if artifact else 0))
    assert len(configs)==84
    rows=[]
    with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(paths,args.native_artifacts,str(cache))) as pool:
        pending=[pool.submit(fit,c) for c in configs]
        for task in as_completed(pending):
            r=task.result();rows.append(r)
            print(json.dumps(dict(completed=len(rows),total=len(configs),id=r['id'],config=r['config'],native=r['validation']['native'],elapsed_seconds=r['elapsed_seconds'])),flush=True)
            (cache/'grid-progress.json').write_text(json.dumps(dict(experiments=rows),indent=2,allow_nan=False)+'\n')
    print('ALL_CACHED '+str(cache),flush=True)
