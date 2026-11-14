"""Weights for attributable native stationary artifacts, never unknown controls."""
from collections import Counter
import numpy as np
from protocol import training_rows as positive_rows


def training_rows(synthetic,native,native_positive_mass,artifacts,native_artifact_mass):
    if native_artifact_mass<0 or native_artifact_mass>=1+native_positive_mass:raise ValueError('artifact mass must preserve positive synthetic-negative mass')
    x,y,w,origin=positive_rows(synthetic,native,native_positive_mass)
    if not native_artifact_mass:return x,y,w,origin
    negatives=[(f['parent_id'],row) for f in artifacts if f['attribution_eligible'] for row,m in zip(f['features'],f['matches']) if m==-1]
    if not negatives:raise ValueError('known attributable artifact negatives required')
    counts=Counter(parent for parent,_ in negatives)
    class_mass=w[y==0].sum();fraction=native_artifact_mass/(1+native_positive_mass)
    w[y==0]*=1-fraction
    nw=np.asarray([class_mass*fraction/(len(counts)*counts[parent]) for parent,_ in negatives])
    x=np.vstack([x,np.asarray([row for _,row in negatives],np.float32)])
    y=np.r_[y,np.zeros(len(negatives),dtype=np.int64)]
    w=np.r_[w,nw];origin += ['native_artifact:'+parent for parent,_ in negatives]
    w*=len(w)/w.sum()
    return x,y,w,origin
