"""Real trained-family loader specimens; never a release selection or refit."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
import joblib
from export_graph import export_graph
from datasets import BASE,FEATURE_NAMES,FEATURE_VERSION,FEATURE_CONTRACT_SHA256,read_cache,sha
sys.path.insert(0,str(BASE))
from experiments.v4.detection.runtime_model import load_ranker

FAMILIES=dict(extra=('ExtraTreesClassifier','mean_weighted_class1_leaf_fraction','Arithmetic mean class1 weighted leaf fractions across randomizedtrees; uncalibrated ranking'),hist=('HistGradientBoostingClassifier','sigmoid_logit_utility','Fixed sigmoid of binary boosted-tree logit utility; uncalibrated ranking'),ranknet=('RankNetTreeBoost','sigmoid_pairwise_utility','Fixed sigmoid of summed pairwise-ranking tree utility; not calibrated probability'),listnet=('ListNetTreeBoost','sigmoid_listwise_utility','Fixed sigmoid of summed listwise-ranking tree utility; not calibrated probability'))


def main():
    source=Path('/tmp/spaceapps-v4-ranker/frontier-v1');report=json.loads((source/'synthetic-progress.json').read_text());header,fields=read_cache('/tmp/spaceapps-v4-ranker/synthetic-validation-30-v1.json.gz','validation');matrix=np.vstack([f['features_v4']for f in fields]);lengths=[len(f['matches'])for f in fields];offset=np.cumsum([0]+lengths)
    output=Path('/tmp/spaceapps-v4-ranker/runtime-family-specimens');output.mkdir(exist_ok=True);records=[]
    for short,(family,kind,description)in FAMILIES.items():
        record=next(r for r in report['experiments']if r['config']['family']==short and r['config']['subset']=='noquality27' and r['config']['pointwise_fraction']==(.5 if short in ['ranknet','listnet']else 1))
        path=Path(record['estimator_path']);assert sha(path)==record['estimator_sha256'];estimator=joblib.load(path);indices=record['config']['selected_feature_indices']
        metadata=dict(schema_version=4,artifact_format='v4-score-vector-v1',model_id='spherex-v4-'+short+'-development-specimen',feature_names=list(FEATURE_NAMES),full_feature_count=30,selected_feature_indices=indices,selected_feature_names=[FEATURE_NAMES[i]for i in indices],feature_version=FEATURE_VERSION,feature_contract_sha256=FEATURE_CONTRACT_SHA256,feature_source_sha256=sha(BASE/'experiments/v4/detection/features.py'),detector_profile=header['detector_settings'],feature_options=dict(template_psf_sigma=.8),class_labels=[0,1],positive_class=1,model_family=family,score_kind=kind,score_description=description,algorithm_version_proposal='motion-v4-'+short+'-development',status='experimental',release_state='development family integration specimen; NOT SELECTED OR RELEASED',training_record_sha256=sha(source/(record['id']+'.json')),fitting_performed_during_export=False)
        directory=output/short;directory.mkdir(exist_ok=True);graph=export_graph(estimator,30,indices,metadata);artifact=directory/'ranker.onnx';artifact.write_bytes(graph.SerializeToString());metadata['sha256']=sha(artifact);(directory/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
        reference=estimator.predict_proba(matrix[:,indices])[:,1]
        try:
            ranker=load_ranker(directory);actual=ranker.score(matrix);close=bool(np.allclose(reference,actual,rtol=2e-6,atol=2e-6));differences=[]
            for i,field in enumerate(fields):
                left=np.argsort(-reference[offset[i]:offset[i+1]],kind='stable');right=np.argsort(-actual[offset[i]:offset[i+1]],kind='stable')
                if any(not np.array_equal(left[:k],right[:k])for k in [1,3]):differences.append(dict(seed=field['seed'],reference_top3=left[:3].tolist(),onnx_top3=right[:3].tolist()))
            proof=dict(family=family,model_sha256=metadata['sha256'],artifact_bytes=artifact.stat().st_size,loader_pass=True,synthetic_validation_fields=len(fields),rows=len(matrix),score_allclose_rtol=2e-6,score_allclose_atol=2e-6,score_allclose_pass=close,max_abs_error=float(np.max(abs(reference-actual))),ordered_top1_top3_changed_fields=differences,all_native_validation_checked=False,selection_performed=False)
        except Exception as error:
            import traceback
            proof=dict(family=family,model_sha256=metadata['sha256'],artifact_bytes=artifact.stat().st_size,loader_pass=False,error=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc()),selection_performed=False)
        (directory/'integration-parity.json').write_text(json.dumps(proof,indent=2)+'\n');records.append(dict(directory=str(directory),**proof));print(json.dumps(records[-1]),flush=True)
    (output/'summary.json').write_text(json.dumps(records,indent=2)+'\n')

if __name__=='__main__':main()
