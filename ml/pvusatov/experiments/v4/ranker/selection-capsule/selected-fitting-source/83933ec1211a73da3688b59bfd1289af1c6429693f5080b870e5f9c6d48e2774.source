"""Small CPU Newton-boosted trees for explicit RankNet/ListNet utility objectives.

Queries contain known synthetic labels only; UNKNOWN=-2 is never a negative.
Optional pointwise log-loss uses separately known labels and explicit weights.
The final fixed sigmoid is monotone, bounds API output and is NOT calibration.
"""
from __future__ import annotations
import numpy as np
from scipy.special import expit,logsumexp
from sklearn.tree import DecisionTreeRegressor


def query_derivatives(scores,matches,objective):
    scores=np.asarray(scores,dtype=float);matches=np.asarray(matches,dtype=int)
    if scores.shape!=matches.shape or not np.isfinite(scores).all():raise ValueError('invalid query')
    gradient=np.zeros(len(scores));hessian=np.zeros(len(scores));positive=np.flatnonzero(matches>=0);negative=np.flatnonzero(matches==-1)
    if not len(positive):return gradient,hessian,0.
    objects,counts=np.unique(matches[positive],return_counts=True);frequency=dict(zip(objects,counts))
    positive_mass=np.asarray([1/(len(objects)*frequency[matches[i]]) for i in positive])
    if objective=='listnet':
        known=np.flatnonzero(matches>=-1);normalizer=logsumexp(scores[known]);probability=np.exp(scores[known]-normalizer)
        gradient[known]=-probability;gradient[positive]+=positive_mass
        hessian[known]=probability*(1-probability)
        loss=float(normalizer-np.dot(positive_mass,scores[positive]))
    elif objective=='ranknet':
        if not len(negative):return gradient,hessian,0.
        margin=scores[positive,None]-scores[negative][None,:];misorder=expit(-margin)
        pair_mass=positive_mass[:,None]/len(negative);g=misorder*pair_mass;h=misorder*(1-misorder)*pair_mass
        gradient[positive]=g.sum(axis=1);gradient[negative]=-g.sum(axis=0)
        hessian[positive]=h.sum(axis=1);hessian[negative]=h.sum(axis=0)
        loss=float(np.sum(np.logaddexp(0.,-margin)*pair_mass))
    else:raise ValueError('objective must be listnet or ranknet')
    return gradient,hessian,loss


class TreeRanker:
    def __init__(self,*,objective='listnet',n_estimators=120,max_depth=3,min_samples_leaf=24,learning_rate=.05,pointwise_fraction=.5,l2_leaf=1e-3,random_state=20261115):
        self.objective=objective;self.n_estimators=n_estimators;self.max_depth=max_depth
        self.min_samples_leaf=min_samples_leaf;self.learning_rate=learning_rate
        self.pointwise_fraction=pointwise_fraction;self.l2_leaf=l2_leaf;self.random_state=random_state
        if objective not in {'listnet','ranknet'} or not 0<=pointwise_fraction<=1:raise ValueError('invalid ranking objective')

    def get_params(self,deep=True):
        return {name:getattr(self,name) for name in ['objective','n_estimators','max_depth','min_samples_leaf','learning_rate','pointwise_fraction','l2_leaf','random_state']}

    def fit(self,x,labels,weights,queries):
        x=np.asarray(x,np.float32);labels=np.asarray(labels,int);weights=np.asarray(weights,float)
        if x.ndim!=2 or labels.shape!=(len(x),)or weights.shape!=labels.shape or not np.isfinite(x).all()or not np.isin(labels,[0,1]).all()or not np.isfinite(weights).all()or np.any(weights<0)or weights.sum()<=0:raise ValueError('finite known training rows required')
        weights=weights/weights.sum();queries=list(queries)
        if not queries and self.pointwise_fraction<1:raise ValueError('ranking requires known queries')
        scores=np.zeros(len(x));self.estimators_=[];self.train_loss_=[];self.n_features_in_=x.shape[1]
        active_queries=[(np.asarray(indices,int),np.asarray(matches,int)) for indices,matches in queries if np.any(np.asarray(matches)>=0)]
        if any(np.any(matches< -1)for _,matches in active_queries):raise ValueError('UNKNOWN rows must be excluded from ranking queries')
        for iteration in range(self.n_estimators):
            probability=expit(scores);fraction=self.pointwise_fraction
            gradient=fraction*weights*(labels-probability);hessian=fraction*weights*probability*(1-probability)
            loss=fraction*float(np.dot(weights,np.logaddexp(0,scores)-labels*scores))
            if fraction<1:
                for indices,matches in active_queries:
                    g,h,qloss=query_derivatives(scores[indices],matches,self.objective);scale=(1-fraction)/len(active_queries)
                    gradient[indices]+=scale*g;hessian[indices]+=scale*h;loss+=scale*qloss
            active=hessian>1e-15
            if active.sum()<2:raise ValueError('ranking objective has insufficient active rows')
            response=np.clip(gradient[active]/hessian[active],-10.,10.)
            tree=DecisionTreeRegressor(max_depth=self.max_depth,min_samples_leaf=self.min_samples_leaf,criterion='squared_error',random_state=self.random_state+iteration).fit(x[active],response,sample_weight=hessian[active])
            # Diagonal-Hessian tree structure, then L2-regularized Newton leaf updates.
            leaves=tree.apply(x[active]);g=gradient[active];h=hessian[active]
            for leaf in np.unique(leaves):
                mask=leaves==leaf
                tree.tree_.value[leaf,0,0]=np.clip(g[mask].sum()/(h[mask].sum()+self.l2_leaf),-10.,10.)
            self.estimators_.append(tree);scores+=self.learning_rate*tree.predict(x);self.train_loss_.append(loss)
        importance=np.sum([tree.feature_importances_ for tree in self.estimators_],axis=0)
        self.feature_importances_=importance/importance.sum() if importance.sum() else importance
        return self

    def decision_function(self,x):
        x=np.asarray(x,np.float32)
        if x.ndim!=2 or x.shape[1]!=self.n_features_in_ or not np.isfinite(x).all():raise ValueError('invalid ranking feature matrix')
        result=np.zeros(len(x))
        for tree in self.estimators_:result+=self.learning_rate*tree.predict(x)
        return result

    def predict_score(self,x):return expit(self.decision_function(x))

    def predict_proba(self,x):
        score=self.predict_score(x)
        return np.column_stack([1-score,score])
