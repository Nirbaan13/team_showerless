"""Portable integrity and complete-cohort rejection checks; no raw data/model."""
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import shutil
import pytest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('portable_v4_verifier',HERE/'verify.py')
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)


def copy_bundle(tmp_path):
    target=tmp_path/'bundle'
    shutil.copytree(HERE,target,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
    return target


def change_payload(folder,mutation,reseal=False):
    path=folder/'scored-fields.json.gz'
    with gzip.open(path,'rt')as stream:data=json.load(stream)
    mutation(data)
    with gzip.open(path,'wt')as stream:json.dump(data,stream,separators=(',',':'))
    if reseal:
        manifest=json.loads((folder/'manifest.json').read_text())
        manifest['files'][path.name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
        (folder/'manifest.json').write_text(json.dumps(manifest))


def test_false_score_rejected_by_original_hash(tmp_path):
    bundle=copy_bundle(tmp_path)
    def mutation(data):
        data['native'][0]['fields'][0]['scores_v4'][0]=.1234567
    change_payload(bundle,mutation)
    with pytest.raises(ValueError,match='hash mismatch'):
        verifier.read_bundle(bundle)


def test_rank_preserving_score_tamper_rejected_after_resealing_all_local_hashes(tmp_path):
    bundle=copy_bundle(tmp_path)
    def mutation(data):
        for cache in data['native']:
            for field in cache['fields']:
                scores=field['scores_v4']
                if scores and min(scores)>0:
                    original_order=verifier.ordered(scores)
                    index=min(range(len(scores)),key=scores.__getitem__)
                    scores[index]*=.5
                    assert verifier.ordered(scores)==original_order
                    value={k:v for k,v in field.items()if k!='projection_sha256'}
                    field['projection_sha256']=hashlib.sha256(verifier.canonical(value)).hexdigest()
                    return
        raise AssertionError('controlled positive-score row missing')
    change_payload(bundle,mutation,reseal=True)
    with pytest.raises(ValueError,match='payload anchor'):
        verifier.read_bundle(bundle)


def test_missing_trial_rejected_even_with_resealed_file_hash(tmp_path):
    bundle=copy_bundle(tmp_path)
    change_payload(bundle,lambda data:data['native'][0]['fields'].pop(),reseal=True)
    with pytest.raises(ValueError,match='payload anchor'):
        verifier.read_bundle(bundle)


def test_corrupted_report_hash_rejected(tmp_path):
    bundle=copy_bundle(tmp_path)
    with (bundle/'canonical-report.json').open('a')as stream:stream.write(' ')
    with pytest.raises(ValueError,match='hash mismatch'):
        verifier.read_bundle(bundle)


def test_stable_ties_duplicate_truths_and_unknowns():
    assert verifier.ordered([.8,.8,.8])==[0,1,2]
    assert verifier.unique([0,0,1,-2],[0,1,2,3])==2
