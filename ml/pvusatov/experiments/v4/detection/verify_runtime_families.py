"""DEVELOPMENT verification only: compare inference graphs with trusted fitted models.

Training packages are imported solely by this verification script; runtime_model
does not import them. No model fitting or final-data access occurs here.
"""
from pathlib import Path
import gzip
import hashlib
import json
import sys
import time
import numpy as np
from ml.pvusatov.experiments.v4.detection.runtime_model import load_ranker

REPO=Path(__file__).resolve().parents[5]


def run(output,specimen_root=None):
    import joblib
    sys.path.insert(0,str(REPO/'ml/pvusatov/experiments/v4/ranker'))
    base=Path('/tmp/spaceapps-v4-ranker');cache=base/'synthetic-validation-30-v1.json.gz'
    with gzip.open(cache,'rt')as stream:data=json.load(stream)
    assert data['partition']=='validation'
    fields=data['fields'];matrix=np.vstack([np.asarray(f['features_v4'],np.float32).reshape(len(f['matches']),30)for f in fields])
    lengths=[len(f['matches'])for f in fields];offsets=np.cumsum([0]+lengths)
    progress=json.loads((base/'frontier-v1/synthetic-progress.json').read_text());records=[]
    specimens=Path(specimen_root or base/'runtime-family-specimens')
    presets_path=Path(__file__).with_name('results')/'preset-feature-cache.json';presets=json.loads(presets_path.read_text())
    for family in ['extra','hist','ranknet','listnet']:
        record=next(r for r in progress['experiments']if r['config']['family']==family and r['config']['subset']=='noquality27'
                    and r['config']['pointwise_fraction']==(.5 if family in ['ranknet','listnet']else 1))
        directory=specimens/family;metadata=json.loads((directory/'metadata.json').read_text())
        path=Path(record['estimator_path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==record['estimator_sha256']
        estimator=joblib.load(path)
        if hasattr(estimator,'n_jobs'):estimator.n_jobs=1
        indices=metadata['selected_feature_indices'];reference=estimator.predict_proba(matrix[:,indices])[:,1]
        started=time.perf_counter();ranker=load_ranker(directory);actual=ranker.score(matrix);elapsed=time.perf_counter()-started
        assert np.allclose(actual,reference,rtol=2e-6,atol=2e-6);changed=[]
        raw=ranker._session.run(['score'],{'X':matrix})[0];membership={99:[],100:[]}
        for i,field in enumerate(fields):
            start,end=offsets[i:i+2];a=np.argsort(-reference[start:end],kind='stable');b=np.argsort(-actual[start:end],kind='stable')
            if any(not np.array_equal(a[:k],b[:k])for k in [1,3]):changed.append(field['seed'])
            raw_order=np.argsort(-raw[start:end],kind='stable')
            for k in membership:
                if set(raw_order[:k])!=set(b[:k]):membership[k].append(field['seed'])
        assert not changed
        preset_proof={}
        for name,case in presets['cases'].items():
            px=np.asarray(case['features_v4'],np.float32).reshape(-1,30);ref=estimator.predict_proba(px[:,indices])[:,1];out=ranker.score(px)
            assert np.allclose(ref,out,rtol=2e-6,atol=2e-6)
            left=np.argsort(-ref,kind='stable');right=np.argsort(-out,kind='stable')
            assert all(np.array_equal(left[:k],right[:k])for k in [1,3])
            ranks={int(i):j+1 for j,i in enumerate(right)}
            preset_proof[name]=dict(rows=len(px),ordered_top1_top3_equal=True,
                known_target_ranks=[ranks[i]for i,m in enumerate(case['matches'])if m>=0],
                known_bloom_unscored=case['c13_known_bloom_target_published'])
        proof=dict(family=metadata['model_family'],artifact_sha256=hashlib.sha256((directory/'ranker.onnx').read_bytes()).hexdigest(),
            metadata_sha256=hashlib.sha256((directory/'metadata.json').read_bytes()).hexdigest(),reference_estimator_sha256=record['estimator_sha256'],
            validation_fields=len(fields),candidate_rows=len(matrix),max_abs_score_error=float(np.max(abs(actual-reference))),
            score_allclose_rtol=2e-6,score_allclose_atol=2e-6,ordered_top1_top3_changed_fields=changed,
            score_numerics=ranker.metadata.get('score_numerics'),numeric_clip_count=int(np.sum(actual!=raw)),
            raw_score_range=[float(raw.min()),float(raw.max())],adapter_score_range=[float(actual.min()),float(actual.max())],
            raw_vs_adapter_top100_membership_changed_fields=membership[100],raw_vs_adapter_quota99_membership_changed_fields=membership[99],
            presets=preset_proof,cpu_provider=ranker._session.get_providers(),load_and_score_wall_seconds=elapsed,selection_performed=False)
        records.append(proof);print(json.dumps(proof),flush=True)
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(dict(schema_version=1,scope='development-only-family-integration',final_read=False,fit_performed=False,
        feature_cache_sha256=hashlib.sha256(cache.read_bytes()).hexdigest(),preset_cache_sha256=hashlib.sha256(presets_path.read_bytes()).hexdigest(),
        loader_source_sha256=hashlib.sha256(Path(__file__).with_name('runtime_model.py').read_bytes()).hexdigest(),records=records),indent=2)+'\n')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--specimen-root');a=p.parse_args();run(a.output,a.specimen_root)
