"""Class-conditional acquisition-domain audit on TRAIN parent groups only."""
from pathlib import Path
import sys,json,gzip,hashlib
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import roc_auc_score,balanced_accuracy_score
from learning import labeled_rows,group_class_weights


def load(paths):
    rows=[]
    for path in paths:
        with gzip.open(path,'rt') as f:rows.extend(json.load(f)['fields'])
    return rows


def run():
    scratch=Path('/tmp/spaceapps-v4-ranker/stage1-six');manifest=json.loads((scratch/'inputs.json').read_text())
    inputs=manifest['inputs'];st=load(inputs['synthetic_train']);nt=load(inputs['native_train']);art=load(inputs['native_artifacts'])
    sx,sy,sg=labeled_rows(st,'synthetic');px,py,pg=labeled_rows(nt,'native_moving');nx,ny,ng=labeled_rows(art,'native_stationary')
    reports={}
    for label,native_x,native_groups in [(1,px,pg),(0,nx,ng)]:
        mask=sy==label;x=np.vstack([sx[mask],native_x]);domain=np.r_[np.zeros(mask.sum(),int),np.ones(len(native_x),int)]
        groups=np.asarray(['synthetic:'+s for s,m in zip(sg,mask) if m]+['native:'+g for g in native_groups])
        native_parents=sorted(set(native_groups));parent_fold={p:i%3 for i,p in enumerate(native_parents)}
        fold=np.r_[[int(s)%3 for s,m in zip(sg,mask) if m],[parent_fold[g] for g in native_groups]]
        experiments={}
        for name,indices in [('all_features',list(range(6))),('without_epoch',list(range(1,6))),('epoch_only',[0])]:
            predictions=np.zeros(len(x));folds=[]
            for k in range(3):
                train=fold!=k;validation=~train;assert set(groups[train]).isdisjoint(set(groups[validation]))
                estimator=ExtraTreesClassifier(n_estimators=100,max_depth=8,min_samples_leaf=4,n_jobs=1,random_state=20261115).fit(x[train][:,indices],domain[train],sample_weight=group_class_weights(domain[train],groups[train]))
                predictions[validation]=estimator.predict_proba(x[validation][:,indices])[:,1]
                folds.append(dict(fold=k,native_validation_rows=int(np.count_nonzero(domain[validation])),native_validation_parents=sorted({g for g in groups[validation] if g.startswith('native:')}),domain_auc=float(roc_auc_score(domain[validation],predictions[validation]))))
            experiments[name]=dict(group_disjoint_train_only_oof_domain_auc=float(roc_auc_score(domain,predictions)),balanced_accuracy=float(balanced_accuracy_score(domain,predictions>=.5)),folds=folds)
        reports['known_moving_positive' if label else 'known_stationary_artifact_negative']=dict(native_rows=len(native_x),native_train_parents=len(native_parents),synthetic_rows=int(mask.sum()),experiments=experiments,native_feature_quantiles=np.quantile(native_x,[0,.1,.5,.9,1],axis=0).tolist(),synthetic_feature_quantiles=np.quantile(sx[mask],[0,.1,.5,.9,1],axis=0).tolist())
    report=dict(scope='TRAIN-only group-disjoint cross-validation; no DEV validation or FINAL observations',purpose=__doc__,input_manifest_sha256=hashlib.sha256((scratch/'inputs.json').read_bytes()).hexdigest(),unknown_real_controls_used=False,interpretation='Domain separability is class-conditional acquisition shortcut risk, not proof a motion ranker uses it. Native artifact92rows are correlated across7parents and are a small negative-ground-truth sample.',reports=reports)
    output=Path('/tmp/spaceapps-v4-ranker/class-conditional-domain.json');output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({name:{experiment:result['group_disjoint_train_only_oof_domain_auc'] for experiment,result in item['experiments'].items()} for name,item in reports.items()}),flush=True)

if __name__=='__main__':run()
