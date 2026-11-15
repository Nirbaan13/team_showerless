from pathlib import Path
import sys
import numpy as np
import onnxruntime as ort
from sklearn.ensemble import ExtraTreesClassifier
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tree_ranker import TreeRanker
from export_graph import export_graph


def execute(graph,x):
    options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
    session=ort.InferenceSession(graph.SerializeToString(),sess_options=options,providers=['CPUExecutionProvider'])
    assert session.get_inputs()[0].name=='X' and session.get_inputs()[0].shape==[None,30]
    assert [o.name for o in session.get_outputs()]==['score']
    return session.run(['score'],{'X':x.astype(np.float32)})[0]


def test_forest_export_binds_selected_feature_order():
    x=np.random.default_rng(4).normal(size=(100,30)).astype(np.float32);indices=[7,2]
    y=(x[:,7]>x[:,2]).astype(int)
    estimator=ExtraTreesClassifier(n_estimators=8,min_samples_leaf=2,random_state=3,n_jobs=1).fit(x[:,indices],y)
    graph=export_graph(estimator,30,indices,{'score_kind':'mean_weighted_class1_leaf_fraction'})
    scores=execute(graph,x)
    np.testing.assert_allclose(scores,estimator.predict_proba(x[:,indices])[:,1],rtol=2e-6,atol=2e-6)


def test_ranker_export_preserves_branches_near_float32_thresholds():
    x=np.random.default_rng(7).normal(size=(80,30)).astype(np.float32);indices=[3,8]
    y=(x[:,3]*x[:,8]>0).astype(int);matches=np.where(y,np.arange(len(x)),-1)
    estimator=TreeRanker(n_estimators=10,min_samples_leaf=2,max_depth=2,pointwise_fraction=.5).fit(x[:,indices],y,np.ones(len(y)),[(np.arange(len(x)),matches)])
    probes=[row.copy() for row in x]
    for tree in estimator.estimators_:
        for feature,threshold in zip(tree.tree_.feature,tree.tree_.threshold):
            if feature<0:continue
            for value in [np.float32(threshold),np.nextafter(np.float32(threshold),np.float32(-np.inf)),np.nextafter(np.float32(threshold),np.float32(np.inf))]:
                row=x[0].copy();row[indices[feature]]=value;probes.append(row)
    probes=np.asarray(probes,np.float32)
    graph=export_graph(estimator,30,indices,{'score_kind':'sigmoid_listwise_utility'})
    scores=execute(graph,probes)
    assert scores.shape==(len(probes),) and np.all((scores>=0)&(scores<=1))
    np.testing.assert_allclose(scores,estimator.predict_score(probes[:,indices]),rtol=2e-6,atol=2e-6)


def test_binary_histogram_boosting_logit_and_threshold_parity():
    from sklearn.ensemble import HistGradientBoostingClassifier
    x=np.random.default_rng(11).normal(size=(150,30)).astype(np.float32);indices=[1,4,8]
    y=(x[:,1]**2+x[:,4]>.5).astype(int)
    estimator=HistGradientBoostingClassifier(max_iter=12,max_depth=3,min_samples_leaf=4,early_stopping=False,learning_rate=.13,random_state=4).fit(x[:,indices],y)
    probes=[row.copy()for row in x]
    for predictors in estimator._predictors:
        for predictor in predictors:
            for node in predictor.nodes:
                if node['is_leaf']:continue
                threshold=np.float32(node['num_threshold'])
                for value in [threshold,np.nextafter(threshold,np.float32(-np.inf)),np.nextafter(threshold,np.float32(np.inf))]:
                    row=x[0].copy();row[indices[int(node['feature_idx'])]]=value;probes.append(row)
    probes=np.asarray(probes,np.float32)
    graph=export_graph(estimator,30,indices,{'score_kind':'sigmoid_logit_utility'})
    np.testing.assert_allclose(execute(graph,probes),estimator.predict_proba(probes[:,indices])[:,1],rtol=2e-6,atol=2e-6)


def test_export_metadata_names_class_policy_and_score_semantics_are_bound():
    import json
    import pytest
    x=np.arange(40,dtype=np.float32).reshape(20,2);y=np.arange(20)%2
    model=ExtraTreesClassifier(n_estimators=2,random_state=3,n_jobs=1).fit(x,y)
    names=['feature'+str(i)for i in range(30)]
    graph=export_graph(model,30,[7,2],{'feature_names':names,'score_kind':'mean_weighted_class1_leaf_fraction'})
    props={p.key:p.value for p in graph.metadata_props}
    assert json.loads(props['selected_feature_names'])==[names[7],names[2]]
    assert json.loads(props['class_labels'])==[0,1] and props['positive_class']=='1'
    assert props['model_family']=='ExtraTreesClassifier'
    with pytest.raises(ValueError,match='score'):export_graph(model,30,[7,2],{'score_kind':'calibrated_planet_probability'})
