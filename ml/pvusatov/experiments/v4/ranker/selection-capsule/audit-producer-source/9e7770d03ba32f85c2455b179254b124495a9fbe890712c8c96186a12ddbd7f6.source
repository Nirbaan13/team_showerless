"""Audit/root-selected frozen RankNet capsule; NO REFIT, no FINAL data access."""
from pathlib import Path
import gzip,json,sys,types,inspect,hashlib,datetime,tempfile,os,subprocess
import numpy as np
import onnx,joblib
from datasets import BASE,sha,FEATURE_NAMES
from threshold_probes import threshold_probes
from validate_frontier import atomic_json
from code_binding import verify_module
sys.path.insert(0,str(BASE))
from experiments.v4.detection import runtime_model
ID='fc3378f486961a8c'
MODEL_SHA='c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'


def atomic_bytes(path,blob):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.writing-',delete=False)as stream:stream.write(blob);temporary=stream.name
    os.replace(temporary,path)


def main():
    owned=Path(__file__).resolve().parent;capsule=owned/'selection-capsule';capsule.mkdir(exist_ok=False);scratch=Path('/tmp/spaceapps-v4-ranker/selected-review');scratch.mkdir(exist_ok=True)
    source=Path('/tmp/spaceapps-v4-ranker/frontier-v1');fitting_path=source/(ID+'.json');fit=json.loads(fitting_path.read_text());inputs_path=source/'synthetic-inputs.json';inputs=json.loads(inputs_path.read_text());release=BASE/'releases/v4/model';metadata=json.loads((release/'metadata.json').read_text());selection=BASE/'experiments/v4/evaluation/selection.json';choice=json.loads(selection.read_text())
    assert choice['selected_candidate']['experiment_id']==ID and sha(release/'ranker.onnx')==MODEL_SHA==metadata['sha256']
    assert sha(fitting_path)==metadata['training_record_sha256']and sha(inputs_path)==fit['training_input_manifest_sha256'];assert sha(fit['estimator_path'])==fit['estimator_sha256']
    assert inputs['phase']=='synthetic'and inputs['native_training_parents']==[]and inputs['native_validation_parents']==[]
    assert fit['config']['native_mass']==0 and fit['config']['pointwise_fraction']==0 and fit['config']['family']=='ranknet'and fit['config']['subset']=='noquality27'
    assert metadata['selected_feature_indices']==list(range(27))and metadata['selected_feature_names']==list(FEATURE_NAMES[:27])
    model=joblib.load(fit['estimator_path']);assert model.objective=='ranknet'and model.pointwise_fraction==0 and model.n_features_in_==27
    source_inventory=[]
    for original,expected in inputs['source_sha256'].items():
        archived=owned/'source-history/frontier-synthetic-v1'/(Path(original).name+'.source');assert sha(archived)==expected
        destination=capsule/'selected-fitting-source'/(expected+'.source');atomic_bytes(destination,archived.read_bytes());source_inventory.append(dict(original=original,sha256=expected,snapshot=str(destination.relative_to(BASE))))
    atomic_bytes(capsule/'selected-fit-record.json',fitting_path.read_bytes());atomic_bytes(capsule/'selected-fitting-inputs.json',inputs_path.read_bytes());atomic_bytes(capsule/'root-selection.json',selection.read_bytes());atomic_bytes(capsule/'original-development-metadata.json',(Path('/tmp/spaceapps-v4-ranker/frontier-onnx-v1')/ID/'metadata.json').read_bytes())
    all_models=[]
    for path in sorted(source.glob('*.json')):
        if len(path.stem)!=16:continue
        record=json.loads(path.read_text())
        if 'config'not in record:continue
        all_models.append(dict(id=record['id'],fit_record_sha256=sha(path),estimator_path=record.get('estimator_path'),estimator_sha256=record.get('estimator_sha256'),config=record['config']))
        atomic_bytes(capsule/'all36-fitting-records'/path.name,path.read_bytes())
    assert len(all_models)==36
    for phase in ['synthetic','native','resolved']:atomic_bytes(capsule/'all36-inputs'/(phase+'.json'),(source/(phase+'-inputs.json')).read_bytes())
    # Reconstruct query indices using the EXACT original fitting producer text.
    original_frontier=next(x for x in source_inventory if Path(x['original']).name=='frontier.py');module=types.ModuleType('selected_original_fitting_producer');module.__file__=original_frontier['original'];blob=(BASE/original_frontier['snapshot']).read_bytes();exec(compile(blob,module.__file__,'exec',dont_inherit=True),module.__dict__)
    training_path=next(p for p in inputs['input_sha256']if 'synthetic-train' in p);assert sha(training_path)==inputs['input_sha256'][training_path]
    with gzip.open(training_path,'rt')as handle:train=json.load(handle)
    assert train['partition']=='train'and train['seeds']==list(range(3000000,3005000))and len(train['fields'])==5000
    fields=train['fields'];matches=[int(m)for f in fields for m in f['matches']];assert all(m>=-1 for m in matches);q=module.queries(fields);informative=[(indices,m)for indices,m in q if np.any(m>=0)and np.any(m==-1)];active=set(int(i)for indices,_ in informative for i in indices);pair_count=sum(int(np.count_nonzero(m>=0))*int(np.count_nonzero(m==-1))for _,m in informative)
    training_audit=dict(loaded_fields=5000,loaded_candidate_rows=len(matches),known_positive_rows=sum(m>=0 for m in matches),known_negative_rows=sum(m==-1 for m in matches),unknown_rows=sum(m< -1 for m in matches),positive_containing_queries=len(q),informative_queries=len(informative),active_unique_rows=len(active),known_positive_negative_pairs=pair_count,native_pixel_rows_fitted=0,native_unknown_rows_fitted=0,pointwise_loss_fraction=0,pairing='Withinindependentsyntheticfieldonly; allpositiveobjectsweighted equally, duplicatedtracksobjectnormalized;64negativecap halfhighheuristic/halfseededuniform',noninformative_fields='No gradient in pureRankNet for fieldswithoutknownpositive/negativecomparisons; loadedrowcount is not activefitrowcount',validation_used_by_fit=False,final_used=False,seed_reservations=dict(train=[3000000,3004999],validation=[3100000,3100999]))
    # Independent structural comparison of every node/leaf to the cached model.
    graph=onnx.load_model_from_string((release/'ranker.onnx').read_bytes());node=graph.graph.node[1];a={attribute.name:onnx.helper.get_attribute_value(attribute)for attribute in node.attribute};nodes={(int(t),int(n)):i for i,(t,n)in enumerate(zip(a['nodes_treeids'],a['nodes_nodeids']))};leaves={(int(t),int(n)):float(v)for t,n,v in zip(a['target_treeids'],a['target_nodeids'],a['target_weights'])};checked_nodes=checked_leaves=0
    for t,tree_model in enumerate(model.estimators_):
        tree=tree_model.tree_
        for n in range(tree.node_count):
            index=nodes[t,n];leaf=tree.children_left[n]==tree.children_right[n];assert a['nodes_modes'][index]==(b'LEAF'if leaf else b'BRANCH_LEQ')
            if leaf:
                expected=np.float32(tree.value[n,0,0]*model.learning_rate);assert np.float32(leaves[t,n]).tobytes()==expected.tobytes();checked_leaves+=1
            else:
                assert a['nodes_featureids'][index]==tree.feature[n]and a['nodes_truenodeids'][index]==tree.children_left[n]and a['nodes_falsenodeids'][index]==tree.children_right[n];cut=np.float32(tree.threshold[n]);cut=np.nextafter(cut,np.float32(-np.inf))if float(cut)>tree.threshold[n]else cut;assert np.float32(a['nodes_values'][index]).tobytes()==cut.tobytes()
            checked_nodes+=1
    assert a['n_targets']==1 and a['aggregate_function']==b'SUM'and a['post_transform']==b'NONE'and not any(a.get('base_values',[]))
    graph_audit=dict(actual_graph_sha256=MODEL_SHA,weighted_graph_proto_sha256=hashlib.sha256(graph.graph.SerializeToString()).hexdigest(),trees=len(model.estimators_),checked_nodes=checked_nodes,checked_leaves=checked_leaves,all_weights_and_branches_match_cached_estimator_exact_float32=True,selected_columns=list(range(27)),quality_columns_used=False,score='fixedsigmoidofsumtreeutility; explicitfloat32roundoffclip2e-6; notcalibratedprobability')
    val_path=Path('/tmp/spaceapps-v4-ranker/synthetic-validation-30-v1.json.gz')
    with gzip.open(val_path,'rt')as handle:validation=json.load(handle)
    observed=np.asarray([row for f in validation['fields']for row in f['features_v4']][:2048],np.float32);thresholds,_=threshold_probes(model,list(range(27)),np.zeros(30,np.float32));indices=np.linspace(0,len(thresholds)-1,1536,dtype=int);probes=np.vstack([observed,thresholds[indices]])
    ranker=runtime_model.load_ranker(release);actual=ranker.score(probes);reference=model.predict_proba(probes[:,:27])[:,1];assert np.allclose(actual,reference,rtol=2e-6,atol=2e-6)
    parity=scratch/'parity-reference.json';atomic_json(parity,dict(features=probes.tolist(),scores=actual.tolist(),sklearn_reference_scores=reference.tolist(),model_sha256=MODEL_SHA,feature_names=list(FEATURE_NAMES),sources='2048NEWsyntheticDEVmeasuredrows+1536pathconsistentnumericthresholdneighbors; noFINALpixels/features/labels',max_export_abs_error=float(np.max(abs(actual-reference)))))
    atomic_json(capsule/'training-audit.json',training_audit);atomic_json(capsule/'graph-estimator-audit.json',graph_audit)
    manifest=dict(schema_version=4,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),state='ROOTdevelopment-selected frozenweights; NEWFINALUNOPENED',selected_id=ID,root_selection_sha256=sha(selection),selected_model=dict(path=str(release/'ranker.onnx'),sha256=MODEL_SHA,bytes=(release/'ranker.onnx').stat().st_size,metadata_sha256=sha(release/'metadata.json')),estimator=dict(path=fit['estimator_path'],sha256=fit['estimator_sha256']),selected_training_sources=source_inventory,all36_models=all_models,all36_reports={name:sha(owned/name)for name in ['development-frontier.json','development-frontier.csv','development-all36-outcomes.json','development-all36-threshold-parity.json','development-all36-paired.json']},training_audit_sha256=sha(capsule/'training-audit.json'),graph_audit_sha256=sha(capsule/'graph-estimator-audit.json'),parity_reference=dict(path=str(parity),sha256=sha(parity),rows=len(probes)),knownlabel_policy='Selectedfit syntheticknownpositive-v-knownnegativewithinfieldpairs ONLY; nativeUNKNOWNnevernegatives; native/newFINALnotfitted',graph_export_refit=False,selection_after_final=False)
    atomic_json(capsule/'manifest.json',manifest);print(json.dumps(dict(manifest_sha256=sha(capsule/'manifest.json'),training=training_audit,graph=graph_audit,parity_reference=manifest['parity_reference'])),flush=True)

if __name__=='__main__':main()
