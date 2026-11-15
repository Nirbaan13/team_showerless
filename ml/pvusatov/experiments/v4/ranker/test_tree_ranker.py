"""Check ranking math and real nonlinear fit independently of cached labels."""
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tree_ranker import query_derivatives,TreeRanker


def test_listwise_derivative_matches_loss_finite_difference():
    scores=np.array([.2,-.5,.8]);matches=np.array([0,-1,-1]);gradient,hessian,loss=query_derivatives(scores,matches,'listnet')
    numerical=[]
    for i in range(3):
        delta=np.zeros(3);delta[i]=1e-6
        high=query_derivatives(scores+delta,matches,'listnet')[2]
        low=query_derivatives(scores-delta,matches,'listnet')[2]
        numerical.append((high-low)/2e-6)
    np.testing.assert_allclose(gradient,-np.array(numerical),atol=1e-8)
    assert np.all(hessian>=0) and np.isclose(gradient.sum(),0)


def test_pairwise_never_uses_unknown_as_a_negative():
    score=np.array([0.,0.,100.]);matches=np.array([0,-1,-2])
    gradient,hessian,loss=query_derivatives(score,matches,'ranknet')
    np.testing.assert_allclose(gradient,[.5,-.5,0.])
    assert hessian[2]==0 and np.isclose(loss,np.log(2))


def test_listwise_weights_objects_equally_when_positive_tracks_duplicate():
    score=np.zeros(4);matches=np.array([0,0,1,-1])
    gradient,_,_=query_derivatives(score,matches,'listnet')
    np.testing.assert_allclose(gradient,[0.,0.,.25,-.25])


def test_real_tree_fit_learns_nonlinear_same_query_order():
    x=np.array([[0,0],[0,1],[1,0],[1,1]],dtype=np.float32)
    labels=np.array([1,0,0,1]);queries=[(np.arange(4),np.array([0,-1,-1,1]))]
    model=TreeRanker(objective='listnet',n_estimators=30,max_depth=2,min_samples_leaf=1,learning_rate=.1,pointwise_fraction=0).fit(x,labels,np.ones(4),queries)
    scores=model.predict_score(x)
    assert min(scores[[0,3]])>max(scores[[1,2]])
    assert np.all((scores>=0)&(scores<=1))
