"""Distinct pre-final numerics policy specimens; preserve every weighted graph byte."""
from pathlib import Path
import json,sys
import numpy as np
import onnx,joblib
from datasets import BASE,sha,read_cache
from export_graph import SCORE_NUMERICS
from code_binding import verify_module
sys.path.insert(0,str(BASE))
from experiments.v4.detection import runtime_model


def main():
    checked_code=verify_module(runtime_model)
    source=Path('/tmp/spaceapps-v4-ranker/runtime-family-specimens');output=Path('/tmp/spaceapps-v4-ranker/runtime-family-specimens-numerics-v2');output.mkdir(exist_ok=False)
    _,fields=read_cache('/tmp/spaceapps-v4-ranker/synthetic-validation-30-v1.json.gz','validation');x=np.vstack([f['features_v4']for f in fields]);cuts=np.cumsum([0]+[len(f['matches'])for f in fields])
    presets=BASE/'experiments/v4/detection/results/preset-feature-cache.json';assert sha(presets)=='0acd2fff5d0427cc2179641606db9d918c78725af3c6ae127940b08410dabf3d';preset_payload=json.loads(presets.read_text())
    records=[]
    for name in ['extra','hist','ranknet','listnet']:
        old=source/name;metadata=json.loads((old/'metadata.json').read_text());graph=onnx.load_model_from_string((old/'ranker.onnx').read_bytes());weighted_sha=__import__('hashlib').sha256(graph.graph.SerializeToString()).hexdigest()
        training_path=next(p for p in Path('/tmp/spaceapps-v4-ranker/frontier-v1').glob('*.json')if sha(p)==metadata['training_record_sha256']);training=json.loads(training_path.read_text());assert sha(training['estimator_path'])==training['estimator_sha256'];model=joblib.load(training['estimator_path']);indices=metadata['selected_feature_indices']
        metadata['score_numerics']=SCORE_NUMERICS
        properties={p.key:p.value for p in graph.metadata_props};properties['score_numerics']=json.dumps(SCORE_NUMERICS,sort_keys=True);onnx.helper.set_model_props(graph,properties)
        assert __import__('hashlib').sha256(graph.graph.SerializeToString()).hexdigest()==weighted_sha
        folder=output/name;folder.mkdir();artifact=folder/'ranker.onnx';artifact.write_bytes(graph.SerializeToString());metadata['sha256']=sha(artifact);(folder/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
        ranker=runtime_model.load_ranker(folder);actual=ranker.score(x);reference=model.predict_proba(x[:,indices])[:,1];mismatch=[];raw100=[];quota99=[];orders=[]
        for i,field in enumerate(fields):
            a=np.argsort(-reference[cuts[i]:cuts[i+1]],kind='stable');b=np.argsort(-actual[cuts[i]:cuts[i+1]],kind='stable')
            if any(not np.array_equal(a[:k],b[:k])for k in [1,3]):mismatch.append(field['seed'])
            if set(a[:100])!=set(b[:100]):raw100.append(field['seed'])
            if set(a[:99])!=set(b[:99]):quota99.append(field['seed'])
            if not np.array_equal(a,b):orders.append(field['seed'])
        case_results={}
        for case,field in preset_payload['cases'].items():
            matrix=np.asarray(field['features_v4'],np.float32).reshape(-1,30);observed=ranker.score(matrix);expected=model.predict_proba(matrix[:,indices])[:,1];a=np.argsort(-expected,kind='stable');b=np.argsort(-observed,kind='stable');known=np.flatnonzero(np.asarray(field['matches'])>=0)
            case_results[case]=dict(score_allclose=bool(np.allclose(observed,expected,rtol=2e-6,atol=2e-6)),ordered_top1_top3_equal=all(np.array_equal(a[:k],b[:k])for k in [1,3]),known_residual_ranks=[int(np.flatnonzero(b==v)[0]+1)for v in known],all_unmatched_unknown=True)
        record=dict(family=name,directory=str(folder),old_model_sha256=sha(old/'ranker.onnx'),new_model_sha256=metadata['sha256'],weighted_graph_proto_sha256=weighted_sha,weighted_graph_exactly_unchanged=True,score_numerics=SCORE_NUMERICS,score_allclose=bool(np.allclose(reference,actual,rtol=2e-6,atol=2e-6)),max_abs_error=float(np.max(abs(reference-actual))),synthetic_dev_fields=len(fields),rows=len(x),ordered_top1_top3_changed_fields=mismatch,raw_top100_membership_changes=raw100,residual_quota99_membership_changes=quota99,full_order_changed_fields=orders,presets=case_results,all_native_validation_checked=False,selection_performed=False,runtime_code_check=checked_code)
        (folder/'integration-parity.json').write_text(json.dumps(record,indent=2)+'\n');records.append(record);print(json.dumps({k:v for k,v in record.items()if k not in ['runtime_code_check','presets','full_order_changed_fields']}),flush=True)
    (output/'summary.json').write_text(json.dumps(records,indent=2)+'\n')

if __name__=='__main__':main()
