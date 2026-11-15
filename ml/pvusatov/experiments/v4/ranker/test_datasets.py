from pathlib import Path
import sys
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from datasets import read_cache,recovery_report


def test_final_nonexistent_path_rejected_before_open(tmp_path):
    with pytest.raises(ValueError,match='FINAL'):read_cache(tmp_path/'final-missing.json.gz','train')


def test_unknown_cannot_be_recovered_and_common_mask_is_shared():
    fields=[dict(parent_id='a',truth_count=1,matches=[-2,0],attribution_eligible=True),dict(parent_id='b',truth_count=1,matches=[0],attribution_eligible=False)]
    scores=[np.array([1.,.5]),np.array([1.])]
    r=recovery_report(fields,scores)
    assert r['all_planned']['top1']==1 and r['all_planned']['truth_count']==2
    assert r['common_attributable']['top1']==0 and r['common_attributable']['top3']==1
    assert r['common_attributable']['macro_parent_recall1']==0


def make_cache(tmp_path,**overrides):
    import gzip,json
    from datasets import FEATURE_NAMES,FEATURE_VERSION,FEATURE_CONTRACT_SHA256,BASE,sha
    payload=dict(partition='train',feature_names=list(FEATURE_NAMES),feature_version=FEATURE_VERSION,feature_contract_sha256=FEATURE_CONTRACT_SHA256,feature_source_sha256=sha(BASE/'experiments/v4/detection/features.py'),detector_settings=dict(psf_sigma=.8,min_speed=.5),baseline_model_sha256='c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204',summary=dict(evaluation_complete=True),fields=[])
    payload.update(overrides);path=tmp_path/'development.json.gz'
    with gzip.open(path,'wt')as f:json.dump(payload,f)
    return path


def test_native_nested_completion_is_accepted(tmp_path):
    header,fields=read_cache(make_cache(tmp_path),'train')
    assert header['summary']['evaluation_complete'] is True and fields==[]


def test_conflicting_completion_claims_are_rejected(tmp_path):
    with pytest.raises(ValueError,match='completion'):read_cache(make_cache(tmp_path,evaluation_complete=False),'train')


def test_wrong_c13_baseline_binding_is_rejected(tmp_path):
    with pytest.raises(ValueError,match='baseline'):read_cache(make_cache(tmp_path,evaluation_complete=True,baseline_model_sha256='0'*64),'train')


def test_primary_native_validation_excludes_stationary_zero_truth_queries():
    from datasets import native_moving_validation
    fields=[dict(parent_id='v4-validation01',truth_kind='moving_injection',truth_count=1)for _ in range(2)]+[dict(parent_id='v4-validation01',truth_kind='stationary_injected_artifact',truth_count=0)]
    moving=native_moving_validation(fields,expected_parents=1,expected_trials=2)
    assert len(moving)==2 and all(f['truth_count']==1 for f in moving)
    with pytest.raises(ValueError,match='planned'):native_moving_validation(fields,expected_parents=1,expected_trials=3)
