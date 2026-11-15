"""Known-label rows and independent-group weights for V4 development only."""
from collections import Counter
import numpy as np


def labeled_rows(fields,kind):
    if kind not in {'synthetic','native_moving','native_stationary'}:
        raise ValueError('unknown scientific label provenance')
    rows=[];labels=[];groups=[];dimension=0
    for field in fields:
        features=field.get('features_v4',field['features'])
        if len(features):dimension=len(features[0])
        if kind!='synthetic' and not field['attribution_eligible']:continue
        if len(features)!=len(field['matches']):raise ValueError('feature/label row mismatch')
        group=str(field['seed']) if kind=='synthetic' else field['parent_id']
        for row,match in zip(features,field['matches']):
            if kind=='native_moving' and match<0:continue
            if kind=='native_stationary' and match!=-1:continue
            if kind=='synthetic' and match< -1:continue
            rows.append(row);labels.append(int(match>=0));groups.append(group)
    x=np.asarray(rows,dtype=np.float32).reshape(-1,dimension)
    if not np.isfinite(x).all():raise ValueError('nonfinite training features')
    return x,np.asarray(labels,dtype=np.int64),groups


def group_class_weights(labels,groups):
    y=np.asarray(labels);groups=np.asarray(groups)
    if y.shape!=groups.shape or not np.isin(y,[0,1]).all():raise ValueError('known class labels required')
    result=np.zeros(len(y),float)
    for label in np.unique(y):
        counts=Counter(groups[y==label])
        for group,count in counts.items():result[(y==label)&(groups==group)]=1/(len(counts)*count)
    return result*len(result)/result.sum() if len(result) else result


def pairwise_rows(fields,max_negatives=64,seed=20261115):
    """Symmetric within-field synthetic pairs; unknown rows never competitors.

    Half the budget uses high-heuristic known negatives, the remainder a seeded
    uniform sample. Each qualifying independent synthetic field has equal mass.
    Input features can be transformed first with training-only preprocessing.
    """
    rng=np.random.default_rng(seed);differences=[];labels=[];weights=[];dimension=0
    for field in fields:
        x=np.asarray(field.get('features_v4',field['features']),np.float64)
        if not len(x):continue
        dimension=x.shape[1];m=np.asarray(field['matches']);positive=np.flatnonzero(m>=0);negative=np.flatnonzero(m==-1)
        if not len(positive) or not len(negative):continue
        if len(negative)>max_negatives:
            heuristic=np.asarray(field.get('baseline',np.zeros(len(x))))
            hard=negative[np.argsort(-heuristic[negative],kind='stable')[:max_negatives//2]]
            rest=np.setdiff1d(negative,hard)
            negative=np.r_[hard,rng.choice(rest,max_negatives-len(hard),replace=False)]
        count=len(positive)*len(negative)
        for p in positive:
            for n in negative:
                delta=x[p]-x[n]
                differences.extend([delta,-delta]);labels.extend([1,0]);weights.extend([1/(2*count)]*2)
    matrix=np.asarray(differences,dtype=np.float64).reshape(-1,dimension)
    if not len(matrix):raise ValueError('no known within-field positive/negative pairs')
    return matrix,np.asarray(labels,dtype=np.int64),np.asarray(weights)*len(weights)/sum(weights)


def resolved_native_training_view(fields):
    """TRAIN-only ambiguity policy; unresolved positives become UNKNOWN, never0.

    Recompute true span on actual candidate epochs with finite covered centers.
    Evaluation/cache labels are untouched. Existing known artifact negatives and
    already-UNKNOWN competitors remain exactly as recorded.
    """
    transformed=[];report=dict(policy='native_positive_actual_matched_covered_epochs_ge3_and_true_span_ge3px',known_positive_before=0,known_positive_after=0,unresolved_became_unknown=0,per_parent={})
    for field in fields:
        if not field.get('attribution_eligible',True)or not any(m>=0 for m in field['matches']):transformed.append(field);continue
        if field.get('truth_kind')!='moving_injection':raise ValueError('native positive truth provenance differs')
        expected=np.asarray(field['expected_xy'],float);covered=np.asarray(field['center_usable_flags'],bool)
        if expected.ndim!=2 or expected.shape[1]!=2 or covered.shape!=(len(expected),):raise ValueError('native TRAIN truth/support geometry malformed')
        records=field['matched_geometry'];mapping={int(g['candidate_index']):g for g in records}
        if len(mapping)!=len(records):raise ValueError('duplicate matched geometry candidate index')
        matches=list(map(int,field['matches']));parent=field['parent_id'];counts=report['per_parent'].setdefault(parent,dict(before=0,after=0,unknown=0))
        for index,match in enumerate(matches):
            if match<0:continue
            if index not in mapping:raise ValueError('known moving positive lacks matched geometry')
            geometry=mapping[index];epochs=np.asarray(geometry['epochs'],int)
            actual_epochs=field['known_candidate_epochs'][index]if 'known_candidate_epochs'in field else field['candidate_epochs'][index]
            if int(geometry['truth_index'])!=match or not np.array_equal(epochs,np.asarray(actual_epochs,int))or np.any(epochs<0)or np.any(epochs>=len(expected)):raise ValueError('matched geometry is not the actual candidate')
            keep=epochs[covered[epochs]&np.isfinite(expected[epochs]).all(axis=1)]
            path=expected[keep];span=float(np.max(np.linalg.norm(path[:,None]-path[None,:],axis=-1)))if len(path)else 0.
            resolved=len(keep)>=3 and np.isfinite(geometry['true_displacement_px'])and geometry['true_displacement_px']>=3 and span>=3
            counts['before']+=1;report['known_positive_before']+=1
            if resolved:counts['after']+=1;report['known_positive_after']+=1
            else:
                matches[index]=-2;counts['unknown']+=1;report['unresolved_became_unknown']+=1
        transformed.append(dict(field,matches=matches))
    return transformed,report
