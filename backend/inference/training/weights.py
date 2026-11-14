"""Training-only nuisance-stratum weights computed exclusively from synthetic rows."""
import numpy as np


def epoch_stratum_weights(features,labels):
    """Match negative epoch-group prevalence to positives before class balancing.

Groups are 3, 4, and >=5 linked epochs. This prevents a synthetic selection
shortcut from treating almost every >=4-epoch real residual as a true source.
Weights retain all features and are bounded to avoid a rare row dominating.
No real labels, coordinates or test rows enter these weights.
"""
    x=np.asarray(features);y=np.asarray(labels)
    if x.ndim!=2 or x.shape[1]!=6 or y.shape!=(len(x),)or not np.isin(y,[0,1]).all():
        raise ValueError('expected labeled six-feature training rows')
    positives=int(np.count_nonzero(y==1));negatives=int(np.count_nonzero(y==0))
    if not positives or not negatives:raise ValueError('both classes required for nuisance weighting')
    groups=np.minimum(x[:,0].astype(int),5);weights=np.ones(len(y),dtype=float)
    for group in np.unique(groups):
        p=int(np.count_nonzero((groups==group)&(y==1)))
        n=int(np.count_nonzero((groups==group)&(y==0)))
        if p and n:
            ratio=(p/positives)/(n/negatives)
            weights[(groups==group)&(y==0)]=np.clip(ratio,.05,50.)
    return weights


def weight_metadata(features,labels,weights):
    x=np.asarray(features);y=np.asarray(labels);groups=np.minimum(x[:,0].astype(int),5)
    return dict(method='negative epoch-stratum marginal matched to synthetic positives, groups3/4/>=5, capped[0.05,50], combined with balanced class weights',
                groups={str(int(group)):dict(positive_rows=int(np.count_nonzero((groups==group)&(y==1))),
                                             negative_rows=int(np.count_nonzero((groups==group)&(y==0))),
                                             mean_negative_multiplier=float(np.mean(weights[(groups==group)&(y==0)]))if np.any((groups==group)&(y==0))else None)
                        for group in np.unique(groups)})
