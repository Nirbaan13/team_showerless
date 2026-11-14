"""Fit reusable v3 research estimators once; pickle stays in /tmp, never runtime.

Additional predeclared development validation fields can be scored without
refitting this identical whole-field training matrix.
"""
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import time
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier,ExtraTreesClassifier
import train_grid as grid
from protocol import training_rows

CACHE=None

def initialize(paths,cache):
    global CACHE
    CACHE=Path(cache);CACHE.mkdir(parents=True,exist_ok=True)
    grid.initialize(paths)

def fit(config):
    family,leaf,depth,features,mass=config
    identifier=hashlib.sha256(json.dumps(config).encode()).hexdigest()[:16]
    st,sv,nt,nv=grid.DATA
    x,y,w,origin=training_rows(st,nt,mass)
    params=dict(n_estimators=160,min_samples_leaf=leaf,max_depth=depth,max_features=features,max_leaf_nodes=512,n_jobs=1,random_state=20261114)
    cls=RandomForestClassifier if family=='rf' else ExtraTreesClassifier
    started=time.monotonic();forest=cls(**params).fit(x,y,sample_weight=w)
    path=CACHE/(identifier+'.joblib');joblib.dump(forest,path,compress=3)
    report=grid.metrics(sv,nv,forest)
    record=dict(id=identifier,config=dict(family=family,native_positive_mass=mass,parameters=params),validation=report,
                training=dict(rows=len(x),positives=int(y.sum()),native_positive_rows=sum(o!='synthetic' for o in origin)),
                estimator_cache_path=str(path),estimator_cache_sha256=grid.sha(path),elapsed_seconds=time.monotonic()-started)
    (CACHE/(identifier+'.json')).write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    return record

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--synthetic-train',required=True);p.add_argument('--synthetic-validation',required=True)
    p.add_argument('--native-train',nargs='+',required=True);p.add_argument('--native-validation',nargs='+',required=True)
    p.add_argument('--cache',required=True);p.add_argument('--workers',type=int,default=4);args=p.parse_args()
    paths=(args.synthetic_train,args.synthetic_validation,args.native_train,args.native_validation)
    cache=Path(args.cache);cache.mkdir(parents=True,exist_ok=True)
    manifest=dict(inputs=dict(synthetic_train=args.synthetic_train,synthetic_validation=args.synthetic_validation,native_train=args.native_train,native_validation=args.native_validation),
                  input_sha256={s:grid.sha(s) for s in [args.synthetic_train,args.synthetic_validation,*args.native_train,*args.native_validation]},
                  source_sha256={str(s):grid.sha(s) for s in [Path(__file__),Path(grid.__file__),Path('backend/inference/experiments/v3_ranker/protocol.py')]},
                  score_semantics='meanclass1 weightedleaf fraction, uncalibratedranking',runtime_pickle_forbidden=True)
    (cache/'inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
    configs=[(family,leaf,depth,features,mass) for family,(leaf,depth),features,mass in itertools.product(['rf','extra'],[(4,12),(12,16),(32,None)],[1.,'sqrt'],[0,.5,2,8])]
    rows=[]
    with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(paths,str(cache))) as pool:
        pending=[pool.submit(fit,c) for c in configs]
        for task in as_completed(pending):
            r=task.result();rows.append(r)
            print(json.dumps(dict(completed=len(rows),total=len(configs),id=r['id'],config=r['config'],native=r['validation']['native'],elapsed_seconds=r['elapsed_seconds'])),flush=True)
            (cache/'grid-progress.json').write_text(json.dumps(dict(experiments=rows),indent=2,allow_nan=False)+'\n')
    print('ALL_CACHED '+str(cache),flush=True)
