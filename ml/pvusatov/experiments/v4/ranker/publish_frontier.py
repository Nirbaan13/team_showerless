"""Publish all36 development outcomes/source bindings; never select a model."""
from pathlib import Path
import json,sys,csv,io,tempfile,os,shutil
import joblib
import numpy as np
from datasets import FEATURE_NAMES,sha
from threshold_probes import tree_arrays


def atomic(path,blob):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.writing-',delete=False)as stream:stream.write(blob);temporary=stream.name
    os.replace(temporary,path)


def main():
    owned=Path(__file__).resolve().parent;raw=Path('/tmp/spaceapps-v4-ranker');outcomes=raw/'frontier-onnx-v1/all-outcomes.json';report=json.loads(outcomes.read_text());thresholds=raw/'threshold-parity-v1/all-threshold-results.json';stress=json.loads(thresholds.read_text());paired=raw/'paired-development-v1.json';uncertainty=json.loads(paired.read_text())
    assert report['complete']and stress['complete']and len(report['experiments'])==len(stress['experiments'])==36
    tests={r['id']:r for r in stress['experiments']};ci={r['id']:r for r in uncertainty['experiments']};rows=[]
    for record in report['experiments']:
        identifier=record['id'];fit_path=raw/'frontier-v1'/(identifier+'.json');fit=json.loads(fit_path.read_text());assert sha(fit_path)==record['fit_record_sha256'];assert sha(fit['estimator_path'])==fit['estimator_sha256'];model=joblib.load(fit['estimator_path']);counts=np.zeros(30,int);trees=0
        for feature,_,_,_,leaf in tree_arrays(model):
            trees+=1
            for index in feature[~leaf]:counts[record['config']['selected_feature_indices'][int(index)]]+=1
        native=record['onnx_development']['native']['common_attributable'];synthetic=record['onnx_development']['synthetic']['all_planned'];quality=[i for i in [27,28,29]if counts[i]>0];selected_quality=[i for i in record['config']['selected_feature_indices']if i in [27,28,29]]
        entry=dict(id=identifier,family=record['config']['family'],subset=record['config']['subset'],native_mass=record['config']['native_mass'],training_label_policy=record['config'].get('training_label_policy','all_known'),pointwise_fraction=record['config']['pointwise_fraction'],native_K1=native['top1'],native_K3=native['top3'],synthetic_K1=synthetic['top1'],synthetic_K3=synthetic['top3'],native_K1_gain=native['top1']-309,native_K3_gain=native['top3']-347,synthetic_K1_gain=synthetic['top1']-249,synthetic_K3_gain=synthetic['top3']-451,eligible=record['eligibility']['eligible']and tests[identifier]['passes'],eligibility_reasons=record['eligibility']['reasons']+([]if tests[identifier]['passes']else['adversarial_threshold_parity_failure']),adversarial_pass=tests[identifier]['passes'],adversarial_probe_rows=tests[identifier].get('diagnostics',{}).get('probe_rows'),artifact_bytes=record['artifact_bytes'],model_sha256=record['model_sha256'],model_directory=record['model_directory'],trees=trees,split_nodes=int(counts.sum()),distinct_used_features=int(np.count_nonzero(counts)),selected_quality_columns=selected_quality,actually_used_quality_columns=quality,actually_used_quality_names=[FEATURE_NAMES[i]for i in quality],split_counts={FEATURE_NAMES[i]:int(n)for i,n in enumerate(counts)if n},comet_d2_rank=min(record['presets']['cases']['comet-d2']['known_residual_ranks']),comet_d6_rank=min(record['presets']['cases']['comet-d6']['known_residual_ranks']),native_paired=ci[identifier]['native'],synthetic_paired=ci[identifier]['synthetic'],strata=ci[identifier]['strata'])
        entry['root_review_min_native_budget_gain']=min(entry['native_K1_gain'],entry['native_K3_gain']);entry['root_review_min_synthetic_budget_gain']=min(entry['synthetic_K1_gain'],entry['synthetic_K3_gain']);rows.append(entry)
    result=dict(schema_version=4,scope='Complete36modelDEVELOPMENTreview; no candidate selected/frozen, FINALclosed',sources=dict(all_outcomes=dict(path=str(outcomes),sha256=sha(outcomes)),adversarial=dict(path=str(thresholds),sha256=sha(thresholds)),paired=dict(path=str(paired),sha256=sha(paired))),baseline=dict(native_K1=309,native_K3=347,native_detected=393,native_denominator=2160,native_independent_parents=8,synthetic_K1=249,synthetic_K3=451,synthetic_truth=2077,synthetic_independent_fields=1000),eligible_count=sum(r['eligible']for r in rows),experiments=rows,source_inputs=dict(native_main_v2_sha256='a175b4c349eb0fa89ef0ecebf86d5871cecb49c7b3b99556f2742deb4bc75a43'),selection_performed=False)
    atomic(owned/'development-frontier.json',(json.dumps(result,indent=2,allow_nan=False)+'\n').encode())
    columns=['id','family','subset','native_mass','training_label_policy','pointwise_fraction','native_K1','native_K3','synthetic_K1','synthetic_K3','eligible','adversarial_pass','artifact_bytes','trees','split_nodes','distinct_used_features','selected_quality_columns','actually_used_quality_columns','comet_d2_rank','comet_d6_rank','root_review_min_native_budget_gain','root_review_min_synthetic_budget_gain']
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(rows);atomic(owned/'development-frontier.csv',stream.getvalue().encode())
    for src,name in [(outcomes,'development-all36-outcomes.json'),(thresholds,'development-all36-threshold-parity.json'),(paired,'development-all36-paired.json')]:atomic(owned/name,src.read_bytes())
    snapshots=owned/'source-history/all36-validation-v1';snapshots.mkdir(exist_ok=True)
    for p in (raw/'frontier-onnx-v1/source-snapshots').iterdir():atomic(snapshots/p.name,p.read_bytes())
    atomic(snapshots/'invocation.json',(raw/'frontier-onnx-v1/invocation.json').read_bytes())
    for row in sorted(rows,key=lambda r:(r['root_review_min_native_budget_gain'],r['root_review_min_synthetic_budget_gain']),reverse=True)[:8]:print(json.dumps({k:row[k]for k in ['id','family','subset','native_mass','training_label_policy','native_K1','native_K3','synthetic_K1','synthetic_K3','eligible','actually_used_quality_columns','distinct_used_features','root_review_min_native_budget_gain','root_review_min_synthetic_budget_gain']}),flush=True)
    print(json.dumps(dict(eligible=result['eligible_count'],frontier_sha256=sha(owned/'development-frontier.json'),csv_sha256=sha(owned/'development-frontier.csv'))),flush=True)

if __name__=='__main__':main()
