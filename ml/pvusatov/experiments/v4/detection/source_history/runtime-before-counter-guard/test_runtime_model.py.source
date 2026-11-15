"""Actual small ONNX graphs test the NEW V4 inference contract, without fitting."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import onnx
from onnx import helper,TensorProto,numpy_helper
from ml.pvusatov.experiments.v4.detection import features
from ml.pvusatov.experiments.v4.detection.runtime_model import load_ranker,Ranker


def metadata(family='RankNetTreeBoost'):
    kinds={'ExtraTreesClassifier':'mean_weighted_class1_leaf_fraction',
           'HistGradientBoostingClassifier':'sigmoid_logit_utility',
           'RankNetTreeBoost':'sigmoid_pairwise_utility','ListNetTreeBoost':'sigmoid_listwise_utility'}
    return dict(schema_version=4,artifact_format='v4-score-vector-v1',model_id='toy-v4',
        feature_names=list(features.FEATURE_NAMES),full_feature_count=30,
        selected_feature_indices=[0,2],selected_feature_names=[features.FEATURE_NAMES[i]for i in [0,2]],
        feature_version=features.FEATURE_VERSION,feature_contract_sha256=features.FEATURE_CONTRACT_SHA256,
        feature_source_sha256=hashlib.sha256(Path(features.__file__).read_bytes()).hexdigest(),
        detector_profile=dict(min_snr=4.,max_peaks=100,psf_sigma=.8,min_speed=.5,max_speed=60.,
                              match_radius=1.4,min_epochs=3,min_support=.8,leave_one_out=True),
        feature_options=dict(template_psf_sigma=.8),class_labels=[0,1],positive_class=1,
        score_numerics=dict(dtype='float32',unit_interval_roundoff_tolerance=2e-6,roundoff_action='clip'),
        model_family=family,score_kind=kinds[family],score_description='Uncalibrated toy ranking function.',
        algorithm_version_proposal='motion-v4-toy')


def graph(meta):
    indices=numpy_helper.from_array(np.asarray([0,2],np.int64),name='v4_feature_indices')
    axis=numpy_helper.from_array(np.asarray([1],np.int64),name='v4_squeeze_axis')
    nodes=[helper.make_node('Gather',['X','v4_feature_indices'],['v4_selected'],axis=1)]
    shared=dict(nodes_treeids=[0,0,0],nodes_nodeids=[0,1,2],nodes_featureids=[0,0,0],
        nodes_modes=['BRANCH_LEQ','LEAF','LEAF'],nodes_values=[0.,0.,0.],
        nodes_truenodeids=[1,0,0],nodes_falsenodeids=[2,0,0],nodes_missing_value_tracks_true=[0,0,0])
    tensors=[indices,axis]
    if meta['model_family']=='ExtraTreesClassifier':
        nodes.append(helper.make_node('TreeEnsembleClassifier',['v4_selected'],['label','probabilities'],domain='ai.onnx.ml',
            classlabels_int64s=[0,1],class_treeids=[0,0],class_nodeids=[1,2],class_ids=[0,0],class_weights=[.2,.8],post_transform='NONE',**shared))
        tensors.append(numpy_helper.from_array(np.asarray([1],np.int64),name='v4_positive_class'))
        nodes.append(helper.make_node('Gather',['probabilities','v4_positive_class'],['column'],axis=1))
    else:
        nodes.append(helper.make_node('TreeEnsembleRegressor',['v4_selected'],['utility'],domain='ai.onnx.ml',n_targets=1,
            aggregate_function='SUM',post_transform='NONE',target_treeids=[0,0],target_nodeids=[1,2],target_ids=[0,0],target_weights=[-1.,1.],**shared))
        nodes.append(helper.make_node('Sigmoid',['utility'],['column']))
    nodes.append(helper.make_node('Squeeze',['column','v4_squeeze_axis'],['score']))
    g=helper.make_graph(nodes,'v4_toy',[helper.make_tensor_value_info('X',TensorProto.FLOAT,[None,30])],
        [helper.make_tensor_value_info('score',TensorProto.FLOAT,[None])],initializer=tensors)
    model=helper.make_model(g,opset_imports=[helper.make_opsetid('',17),helper.make_opsetid('ai.onnx.ml',3)],ir_version=8)
    helper.set_model_props(model,{k:v if isinstance(v,str)else json.dumps(v,sort_keys=True)for k,v in meta.items()})
    return model


class ModelPolicy(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def save(self,meta=None,model=None):
        meta=metadata()if meta is None else meta;model=graph(meta)if model is None else model
        blob=model.SerializeToString();(self.directory/'ranker.onnx').write_bytes(blob)
        (self.directory/'metadata.json').write_text(json.dumps({**meta,'sha256':hashlib.sha256(blob).hexdigest()}))
        return model,meta
    def rejection(self):
        with patch('onnxruntime.InferenceSession',side_effect=AssertionError('ORT opened before policy rejection')):
            with self.assertRaises(ValueError):load_ranker(self.directory)

    def test_actual_utility_and_forest_scores_and_empty_inputs(self):
        for family in ['RankNetTreeBoost','ListNetTreeBoost','HistGradientBoostingClassifier','ExtraTreesClassifier']:
            with self.subTest(family=family):
                self.save(metadata(family));ranker=load_ranker(self.directory);x=np.zeros((2,30),np.float32);x[:,0]=[-1.,1.]
                expected=[.2,.8]if family=='ExtraTreesClassifier'else[.26894142,.73105858]
                np.testing.assert_allclose(ranker.score(x),expected,atol=1e-7)
                self.assertEqual(ranker.score(np.empty((0,30))).shape,(0,))
                self.assertEqual(ranker._session.get_providers(),['CPUExecutionProvider'])

    def test_source_or_contract_or_embedded_metadata_tampering_rejected(self):
        for key,value in [('feature_source_sha256','0'*64),('feature_contract_sha256','0'*64),('model_family','ListNetTreeBoost')]:
            model,meta=self.save();meta[key]=value;self.save(meta,model);self.rejection()

    def test_artifact_byte_tampering_rejected_before_ort(self):
        self.save();p=self.directory/'ranker.onnx';p.write_bytes(p.read_bytes()+b'changed');self.rejection()

    def test_family_must_be_a_supported_string(self):
        for value in [None,[],{},'unreviewed-family']:
            model,meta=self.save();meta['model_family']=value;self.save(meta,model);self.rejection()

    def test_actual_subset_gather_indices_cannot_disagree(self):
        model,meta=self.save();model.graph.initializer[0].CopyFrom(numpy_helper.from_array(np.asarray([2,0],np.int64),name='v4_feature_indices'))
        self.save(meta,model);self.rejection()

    def test_actual_tree_input_cannot_bypass_feature_subset(self):
        model,meta=self.save();model.graph.node[1].input[0]='X';self.save(meta,model);self.rejection()

    def test_actual_classifier_class_and_positive_column_are_bound(self):
        for target in ('labels','column'):
            model,meta=self.save(metadata('ExtraTreesClassifier'))
            if target=='labels':next(a for a in model.graph.node[1].attribute if a.name=='classlabels_int64s').ints[1]=2
            else:model.graph.initializer[2].CopyFrom(numpy_helper.from_array(np.asarray([0],np.int64),name='v4_positive_class'))
            self.save(meta,model);self.rejection()

    def test_external_data_huge_tensor_and_custom_operator_rejected(self):
        for target in ('external','shape','operator'):
            model,meta=self.save()
            if target=='external':
                tensor=model.graph.initializer[0];tensor.data_location=TensorProto.EXTERNAL
                tensor.external_data.add(key='location',value='never-read.bin')
            elif target=='shape':model.graph.initializer[0].dims[0]=10**12
            else:model.graph.node[2].domain='untrusted';model.graph.node[2].op_type='Custom'
            self.save(meta,model);self.rejection()

    def test_cyclic_tree_and_wrong_feature_number_rejected(self):
        for target in ('cycle','feature'):
            model,meta=self.save();key='nodes_truenodeids'if target=='cycle'else'nodes_featureids'
            next(a for a in model.graph.node[1].attribute if a.name==key).ints[0]=0 if target=='cycle'else 29
            self.save(meta,model);self.rejection()

    def test_duplicate_external_json_and_onnx_properties_rejected(self):
        self.save();p=self.directory/'metadata.json';s=p.read_text();p.write_text(s[:-1]+',"schema_version":4}');self.rejection()
        model,meta=self.save();model.metadata_props.add(key='model_id',value='duplicate');self.save(meta,model);self.rejection()

    def test_embedded_nested_boolean_cannot_impersonate_integer_index(self):
        model,meta=self.save()
        next(p for p in model.metadata_props if p.key=='selected_feature_indices').value='[false,2]'
        self.save(meta,model);self.rejection()

    def test_score_rejects_bad_shapes_nonfinite_float32_overflow_and_strings(self):
        self.save();ranker=load_ranker(self.directory)
        for x in [np.ones(30),np.ones((2,29)),np.full((1,30),np.nan),np.full((1,30),1e300),np.full((1,30),'1')]:
            with self.subTest(shape=x.shape),self.assertRaises(ValueError):ranker.score(x)

    def test_declared_numeric_policy_is_mandatory_and_bound(self):
        for changed in [None,dict(dtype='float32',unit_interval_roundoff_tolerance=1e-4,roundoff_action='clip')]:
            model,meta=self.save()
            if changed is None:del meta['score_numerics']
            else:meta['score_numerics']=changed
            self.save(meta,model);self.rejection()

    def test_float32_roundoff_boundaries_clip_but_genuine_overshoot_rejects(self):
        class Output:
            def __init__(self,value):self.value=value
            def run(self,names,inputs):return[np.full(len(inputs['X']),self.value,np.float32)]
        upper=np.float32(1+2e-6);lower=np.float32(-2e-6)
        for value,want in [(upper,1.),(lower,0.),(np.float32(1+1e-6),1.)]:
            self.assertEqual(float(Ranker(Output(value),metadata()).score(np.zeros((1,30)))[0]),want)
        for value in [np.nextafter(upper,np.float32(np.inf)),np.nextafter(lower,np.float32(-np.inf)),np.float32(1+1e-4),np.nan]:
            with self.assertRaises(ValueError):Ranker(Output(value),metadata()).score(np.zeros((1,30)))

    def test_real_exported_160_tree_pure_leaves_zero_and_one(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ranker'))
        from sklearn.ensemble import ExtraTreesClassifier
        from export_graph import export_graph
        x=np.asarray([[-1.]]*20+[[1.]]*20,np.float32);y=np.asarray([0]*20+[1]*20)
        estimator=ExtraTreesClassifier(n_estimators=160,max_depth=1,n_jobs=1,random_state=3800001).fit(x,y)
        meta=metadata('ExtraTreesClassifier');meta['selected_feature_indices']=[0];meta['selected_feature_names']=[features.FEATURE_NAMES[0]]
        artifact=export_graph(estimator,30,[0],meta);self.save(meta,artifact);ranker=load_ranker(self.directory)
        full=np.zeros((2,30),np.float32);full[:,0]=[-1.,1.]
        np.testing.assert_array_equal(estimator.predict_proba(x[[0,-1]])[:,1],[0.,1.])
        np.testing.assert_array_equal(ranker.score(full),[0.,1.])


if __name__=='__main__':unittest.main()
