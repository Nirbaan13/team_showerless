"""V4 graph contract: full X[N,D] -> artifact-bound subset -> score[N].

No refit occurs here. Tree objectives export as summed regression trees followed
by a fixed monotone sigmoid. Classification ensembles expose class-1 weighted
leaf fractions, without any calibrated probability interpretation.
"""
from __future__ import annotations
import json
import numpy as np
import onnx
from onnx import helper,TensorProto,numpy_helper
from tree_ranker import TreeRanker
SCORE_NUMERICS=dict(dtype='float32',unit_interval_roundoff_tolerance=2e-6,roundoff_action='clip')


def _threshold(value):
    # sklearn compares float32 inputs to float64 thresholds. Pick the largest
    # representable float32 <= threshold to preserve every finite input branch.
    result=np.float32(value)
    if float(result)>value:result=np.nextafter(result,np.float32(-np.inf))
    return float(result)


def _tree_graph(model,selected_name):
    attributes={name:[] for name in ['nodes_treeids','nodes_nodeids','nodes_featureids','nodes_modes','nodes_values','nodes_truenodeids','nodes_falsenodeids','nodes_missing_value_tracks_true','target_treeids','target_nodeids','target_ids','target_weights']}
    for tree_id,estimator in enumerate(model.estimators_):
        tree=estimator.tree_
        for node_id in range(tree.node_count):
            leaf=tree.children_left[node_id]==tree.children_right[node_id]
            record=dict(nodes_treeids=tree_id,nodes_nodeids=node_id,nodes_featureids=0 if leaf else int(tree.feature[node_id]),nodes_modes='LEAF' if leaf else 'BRANCH_LEQ',nodes_values=0. if leaf else _threshold(tree.threshold[node_id]),nodes_truenodeids=0 if leaf else int(tree.children_left[node_id]),nodes_falsenodeids=0 if leaf else int(tree.children_right[node_id]),nodes_missing_value_tracks_true=0)
            for key,value in record.items():attributes[key].append(value)
            if leaf:
                for key,value in dict(target_treeids=tree_id,target_nodeids=node_id,target_ids=0,target_weights=float(tree.value[node_id,0,0]*model.learning_rate)).items():attributes[key].append(value)
    return [helper.make_node('TreeEnsembleRegressor',[selected_name],['v4_raw_utility'],domain='ai.onnx.ml',n_targets=1,aggregate_function='SUM',post_transform='NONE',**attributes),helper.make_node('Sigmoid',['v4_raw_utility'],['v4_bounded_column'])], 'v4_bounded_column'



def _histogram_graph(model,selected_name):
    if np.asarray(model.classes_).tolist()!=[0,1] or model.n_trees_per_iteration_!=1:
        raise ValueError('only binary numeric histogram logit ensembles are supported')
    baseline=np.asarray(model._baseline_prediction,dtype=float)
    if baseline.size!=1 or not np.isfinite(baseline).all():raise ValueError('invalid binary logit baseline')
    attributes={name:[] for name in ['nodes_treeids','nodes_nodeids','nodes_featureids','nodes_modes','nodes_values','nodes_truenodeids','nodes_falsenodeids','nodes_missing_value_tracks_true','target_treeids','target_nodeids','target_ids','target_weights']}
    for tree_id,predictors in enumerate(model._predictors):
        if len(predictors)!=1:raise ValueError('multiclass boosting not supported')
        for node_id,node in enumerate(predictors[0].nodes):
            if node['is_categorical']:raise ValueError('categorical histogram splits not supported')
            leaf=bool(node['is_leaf'])
            record=dict(nodes_treeids=tree_id,nodes_nodeids=node_id,nodes_featureids=0 if leaf else int(node['feature_idx']),nodes_modes='LEAF' if leaf else 'BRANCH_LEQ',nodes_values=0. if leaf else _threshold(float(node['num_threshold'])),nodes_truenodeids=0 if leaf else int(node['left']),nodes_falsenodeids=0 if leaf else int(node['right']),nodes_missing_value_tracks_true=int(node['missing_go_to_left']))
            for key,value in record.items():attributes[key].append(value)
            if leaf:
                # sklearn predictor node values already include learning-rate shrinkage.
                for key,value in dict(target_treeids=tree_id,target_nodeids=node_id,target_ids=0,target_weights=float(node['value'])).items():attributes[key].append(value)
    node=helper.make_node('TreeEnsembleRegressor',[selected_name],['v4_raw_utility'],domain='ai.onnx.ml',n_targets=1,aggregate_function='SUM',post_transform='NONE',base_values=[float(baseline.ravel()[0])],**attributes)
    return [node,helper.make_node('Sigmoid',['v4_raw_utility'],['v4_bounded_column'])], 'v4_bounded_column'


def export_graph(model,full_dimension,indices,metadata):
    indices=list(map(int,indices))
    if not indices or len(indices)!=len(set(indices))or min(indices)<0 or max(indices)>=full_dimension:raise ValueError('invalid ordered feature subset')
    if model.n_features_in_!=len(indices):raise ValueError('selected feature dimension mismatch')
    select=helper.make_node('Gather',['X','v4_feature_indices'],['v4_selected'],axis=1)
    index_tensor=numpy_helper.from_array(np.asarray(indices,np.int64),name='v4_feature_indices')
    axes=numpy_helper.from_array(np.asarray([1],np.int64),name='v4_squeeze_axis')
    from sklearn.ensemble import HistGradientBoostingClassifier
    if isinstance(model,(TreeRanker,HistGradientBoostingClassifier)):
        nodes,column=(_tree_graph(model,'v4_selected') if isinstance(model,TreeRanker) else _histogram_graph(model,'v4_selected'))
        nodes=[select,*nodes,helper.make_node('Squeeze',[column,'v4_squeeze_axis'],['score'])]
        graph=helper.make_graph(nodes,'v4_rank_utility',[helper.make_tensor_value_info('X',TensorProto.FLOAT,[None,full_dimension])],[helper.make_tensor_value_info('score',TensorProto.FLOAT,[None])],initializer=[index_tensor,axes])
        artifact=helper.make_model(graph,producer_name='spaceapps-v4-ranker',opset_imports=[helper.make_opsetid('',17),helper.make_opsetid('ai.onnx.ml',3)],ir_version=8)
    else:
        from skl2onnx import to_onnx
        from skl2onnx.common.data_types import FloatTensorType
        if np.asarray(model.classes_).tolist()!=[0,1]:raise ValueError('known [0,1] classes required')
        artifact=to_onnx(model,initial_types=[('X',FloatTensorType([None,len(indices)]))],options={id(model):{'zipmap':False}},target_opset=17)
        old_input=artifact.graph.input[0].name;probabilities=artifact.graph.output[1].name
        for node in artifact.graph.node:
            for i,name in enumerate(node.input):
                if name==old_input:node.input[i]='v4_selected'
        artifact.graph.node.insert(0,select)
        artifact.graph.initializer.extend([index_tensor,axes,numpy_helper.from_array(np.asarray([1],np.int64),name='v4_positive_class')])
        artifact.graph.node.extend([helper.make_node('Gather',[probabilities,'v4_positive_class'],['v4_bounded_column'],axis=1),helper.make_node('Squeeze',['v4_bounded_column','v4_squeeze_axis'],['score'])])
        del artifact.graph.input[:];artifact.graph.input.append(helper.make_tensor_value_info('X',TensorProto.FLOAT,[None,full_dimension]))
        del artifact.graph.output[:];artifact.graph.output.append(helper.make_tensor_value_info('score',TensorProto.FLOAT,[None]))
    if isinstance(model,TreeRanker):
        family='RankNetTreeBoost' if model.objective=='ranknet' else 'ListNetTreeBoost'
        kind='sigmoid_pairwise_utility' if model.objective=='ranknet' else 'sigmoid_listwise_utility'
    elif isinstance(model,HistGradientBoostingClassifier):family='HistGradientBoostingClassifier';kind='sigmoid_logit_utility'
    else:family=type(model).__name__;kind='mean_weighted_class1_leaf_fraction'
    if metadata.get('score_kind',kind)!=kind:raise ValueError('score semantics do not match fitted estimator')
    if metadata.get('model_family',family)!=family:raise ValueError('model family does not match fitted estimator')
    if metadata.get('class_labels',[0,1])!=[0,1]or metadata.get('positive_class',1)!=1:raise ValueError('known class policy mismatch')
    if metadata.get('score_numerics',SCORE_NUMERICS)!=SCORE_NUMERICS:raise ValueError('unsupported score roundoff policy')
    properties=dict(metadata,score_numerics=SCORE_NUMERICS,schema_version=4,artifact_format='v4-score-vector-v1',full_feature_count=full_dimension,selected_feature_indices=indices,class_labels=[0,1],positive_class=1,model_family=family,score_kind=kind)
    if 'feature_names' in metadata:
        if len(metadata['feature_names'])!=full_dimension:raise ValueError('full feature order dimension mismatch')
        names=[metadata['feature_names'][i]for i in indices]
        if metadata.get('selected_feature_names',names)!=names:raise ValueError('selected feature order mismatch')
        properties['selected_feature_names']=names
    helper.set_model_props(artifact,{name:value if isinstance(value,str)else json.dumps(value,sort_keys=True) for name,value in properties.items()})
    onnx.checker.check_model(artifact)
    return artifact
