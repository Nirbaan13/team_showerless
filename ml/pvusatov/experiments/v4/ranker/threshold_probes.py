"""Path-consistent adversarial float32 threshold neighbors; no science labels."""
from __future__ import annotations
import numpy as np


def tree_arrays(model):
    if hasattr(model,'_predictors'):
        for predictors in model._predictors:
            if len(predictors)!=1:raise ValueError('only binary numeric histogram trees supported')
            nodes=predictors[0].nodes
            if np.any(nodes['is_categorical']):raise ValueError('categorical split unsupported')
            yield nodes['feature_idx'],nodes['num_threshold'],nodes['left'],nodes['right'],nodes['is_leaf'].astype(bool)
    else:
        for estimator in model.estimators_:
            t=estimator.tree_
            yield t.feature,t.threshold,t.children_left,t.children_right,t.children_left==t.children_right


def floor32(value):
    result=np.float32(value)
    return np.nextafter(result,np.float32(-np.inf))if float(result)>float(value)else result


def threshold_probes(model,indices,base_full):
    indices=np.asarray(indices,int);base_full=np.asarray(base_full,np.float32);k=len(indices)
    probes=[];diagnostics=dict(internal_nodes=0,covered_internal_nodes=0,path_reach_assertions=0,trees=0,source='numeric path constraints; not additional physical observations')
    for feature,threshold,left,right,leaf in tree_arrays(model):
        diagnostics['trees']+=1;pending=[(0,np.full(k,-np.inf,np.float32),np.full(k,np.inf,np.float32))]
        while pending:
            node,lower,upper=pending.pop()
            if leaf[node]:continue
            diagnostics['internal_nodes']+=1;f=int(feature[node]);cut=floor32(threshold[node])
            values=[cut,np.nextafter(cut,np.float32(-np.inf)),np.nextafter(cut,np.float32(np.inf))]
            base=np.minimum(np.maximum(base_full[indices],lower),upper);variants=[]
            for value in values:
                if not np.isfinite(value)or value<lower[f]or value>upper[f]:continue
                selected=base.copy();selected[f]=value;variants.append(selected)
            if not variants:raise ValueError('split has no feasible finite float32 neighbor')
            # Verify by walking the original tree, independently of export/ORT.
            reached=0;row=variants[0]
            while reached!=node:
                if leaf[reached]:raise ValueError('claimed threshold path is unreachable')
                reached=int(left[reached]if float(row[int(feature[reached])])<=float(threshold[reached])else right[reached])
            diagnostics['path_reach_assertions']+=1;diagnostics['covered_internal_nodes']+=1
            for selected in variants:
                row=base_full.copy();row[indices]=selected;probes.append(row)
            hi=upper.copy();hi[f]=min(hi[f],cut)
            lo=lower.copy();lo[f]=max(lo[f],np.nextafter(cut,np.float32(np.inf)))
            if np.all(lower<=hi):pending.append((int(left[node]),lower.copy(),hi))
            if np.all(lo<=upper):pending.append((int(right[node]),lo,upper.copy()))
    result=np.asarray(probes,np.float32)if probes else base_full.reshape(1,-1).copy();diagnostics['probe_rows']=len(result)
    if not np.isfinite(result).all():raise ValueError('nonfinite numeric probe')
    return result,diagnostics
