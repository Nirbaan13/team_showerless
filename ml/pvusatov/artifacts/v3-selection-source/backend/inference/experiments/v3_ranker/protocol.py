"""Training and recovery accounting for explicitly labeled v3 development rows.

Native matches -2 mean scientifically unknown and are never fitting negatives.
Only synthetic rows have known negative identities. Native derivatives stay
with their independent parent field; all weighting is computed on train only.
"""
from collections import Counter
import numpy as np
from training.train import feature_matrix
from training.weights import epoch_stratum_weights


def training_rows(synthetic,native,native_positive_mass=1):
    if native_positive_mass<0:raise ValueError('native mass must be nonnegative')
    x,y=feature_matrix(synthetic)
    if not np.any(y==0) or not np.any(y==1):raise ValueError('both synthetic classes required')
    w=epoch_stratum_weights(x,y)
    w[y==1]/=w[y==1].sum();w[y==0]/=w[y==0].sum()
    origin=['synthetic']*len(x)
    positives=[(f['parent_id'],row) for f in native if f['attribution_eligible'] for row,m in zip(f['features'],f['matches']) if m>=0]
    if positives and native_positive_mass:
        counts=Counter(p for p,_ in positives)
        w[y==0]*=1+native_positive_mass
        native_w=np.asarray([native_positive_mass/(len(counts)*counts[p]) for p,_ in positives])
        x=np.vstack([x,np.asarray([r for _,r in positives],np.float32)])
        y=np.r_[y,np.ones(len(positives),dtype=np.int64)]
        w=np.r_[w,native_w]
        origin += ['native:'+p for p,_ in positives]
    w*=len(w)/w.sum()
    return x,y,w,origin


def recovery_report(fields,score):
    eligible=[f for f in fields if f['attribution_eligible']]
    result=dict(planned_injections=len(fields),eligible_injections=len(eligible),detected=0,top1=0,top3=0,
                candidate_rows=sum(len(f['features']) for f in fields),unknown_real_candidates_are_unlabeled=True)
    for f in eligible:
        match=np.asarray(f['matches'],int)>=0
        result['detected']+=int(match.any())
        if not len(match):continue
        order=np.argsort(-np.asarray(score(f)),kind='stable')
        for k in [1,3]:result['top'+str(k)]+=int(match[order[:k]].any())
    denominator=result['eligible_injections']
    result['recall1']=result['top1']/denominator if denominator else None
    result['recall3']=result['top3']/denominator if denominator else None
    return result
