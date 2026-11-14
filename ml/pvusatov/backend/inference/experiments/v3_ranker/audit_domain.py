"""Positive-only acquisition-domain audit; this is not a motion ranker."""
import argparse
from pathlib import Path
import json
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score,balanced_accuracy_score
import train_grid as grid
from ml_inference.model import FEATURE_NAMES

def positives(fields):
    return np.asarray([r for f in fields if f.get('attribution_eligible',True) for r,m in zip(f['features'],f['matches']) if m>=0],np.float32).reshape(-1,6)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',required=True);p.add_argument('--native-validation',nargs='+',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    inputs=json.loads((Path(args.cache)/'inputs.json').read_text())['inputs']
    st=grid.read(inputs['synthetic_train'])['fields'];sv=grid.read(inputs['synthetic_validation'])['fields']
    nt=[f for p in inputs['native_train'] for f in grid.read(p)['fields']];nv=[f for p in args.native_validation for f in grid.read(p)['fields']]
    a,b,c,d=map(positives,[st,nt,sv,nv]);x=np.vstack([a,b]);y=np.r_[np.zeros(len(a),int),np.ones(len(b),int)];vx=np.vstack([c,d]);vy=np.r_[np.zeros(len(c),int),np.ones(len(d),int)]
    reports={}
    for label,indices in [('all_features',list(range(6))),('without_epoch',[1,2,3,4,5]),('epoch_only',[0])]:
        f=RandomForestClassifier(n_estimators=100,max_depth=8,min_samples_leaf=8,class_weight='balanced',n_jobs=1,random_state=20261114).fit(x[:,indices],y)
        scores=f.predict_proba(vx[:,indices])[:,1]
        reports[label]=dict(heldout_domain_auc=float(roc_auc_score(vy,scores)),balanced_accuracy=float(balanced_accuracy_score(vy,scores>=.5)),feature_importance={FEATURE_NAMES[i]:float(v) for i,v in zip(indices,f.feature_importances_)})
    report=dict(purpose='Distinguish native versus synthetic acquisition among KNOWN POSITIVES ONLY; this is not a motion classifier, no unknown control labels are assigned.',interpretation='High separability establishes acquisition-domain shortcut risk for native-positive-only augmentation; it does not establish that the motion ranker uses that shortcut. Compare all native_mass=0 ablations and known stationary-source artifact audit.',train_native_positive_rows=len(b),train_synthetic_positive_rows=len(a),validation_native_positive_rows=len(d),validation_synthetic_positive_rows=len(c),experiments=reports,
                feature_quantiles={label:np.quantile(values,[0,.1,.5,.9,1],axis=0).tolist() for label,values in [('synthetic_train_positive',a),('native_train_positive',b),('synthetic_validation_positive',c),('native_validation_positive',d)]})
    Path(args.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(reports),flush=True)
