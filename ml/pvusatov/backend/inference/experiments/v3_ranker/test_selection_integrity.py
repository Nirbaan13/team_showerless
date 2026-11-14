import gzip
import hashlib
import json
import pytest
from selection_integrity import validate_hashes,normalize_native_pair,paired_native_report

def test_mutated_training_cache_is_rejected_before_model_selection(tmp_path):
    path=tmp_path/'train-cache.json';path.write_text('original')
    expected=hashlib.sha256(path.read_bytes()).hexdigest();path.write_text('changed')
    with pytest.raises(ValueError,match='checksum'):
        validate_hashes({str(path):expected})

def test_verified_source_can_restore_missing_latent_metadata_without_changing_candidates(tmp_path):
    trial=dict(parent_id='p',seed=1,trajectory_id=0,brightness=3.,truth_count=1,expected_xy=[[1,2],[2,2],[3,2]],injected_flux=4.,speed_px_hour=1.,origin_xy=[1,2],velocity_xy_hour=[1,0],usable_center_epochs=3,matches=[0],features=[[3,0,8,5,.1,.5]],baseline=[10],attribution_eligible=True)
    baseline=dict(parent_id='p',partition='validation',input_sources=[dict(sha256='nativebytes')],times_hours=[0,1,2],registered_shape=[3,10,10],center_deg=[1,2],detector_settings=dict(psf_sigma=1.2,min_speed=.5),fields=[trial])
    path=tmp_path/'baseline.json.gz'
    with gzip.open(path,'wt') as f:json.dump(baseline,f)
    ct=dict(trial);ct.pop('origin_xy');ct.pop('velocity_xy_hour');ct['features']=[[3,.1,9,6,.2,.4]]
    candidate={k:v for k,v in baseline.items() if k not in ['registered_shape','fields']};candidate.update(shape=[3,10,10],detector_settings=dict(psf_sigma=.8,min_speed=.5),fields=[ct],source_cache=str(path),source_cache_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    left,right=normalize_native_pair(baseline,candidate)
    assert right['fields'][0]['origin_xy']==[1,2]
    assert right['fields'][0]['features']==ct['features']
    assert 'origin_xy' not in candidate['fields'][0]

def test_common_attribution_does_not_hide_raw_planned_recovery():
    def field(i,eligible,matches):
        return dict(parent_id='p',seed=1,trajectory_id=i,brightness=3.,truth_count=1,expected_xy=[[1,2],[2,2],[3,2]],injected_flux=4.,speed_px_hour=1.,usable_center_epochs=3,matches=matches,attribution_eligible=eligible)
    baseline=[field(0,False,[0]),field(1,True,[0])]
    candidate=[field(0,True,[-2]),field(1,True,[0,-2])]
    report=paired_native_report(baseline,candidate,[[1],[1]],[[1],[1,2]],bootstrap_samples=20)
    assert report['all_planned']['trials']==2
    assert report['all_planned']['baseline']['top1']==2
    assert report['common_attributable']['trials']==1
    assert report['common_attributable']['baseline']['top1']==1
    assert report['common_attributable']['candidate']['top1']==0

def test_legacy_same_detector_tool_cannot_freeze_a_release_candidate():
    from types import SimpleNamespace
    from select_cached import run
    with pytest.raises(ValueError,match='cannot freeze'):
        run(SimpleNamespace(evaluate_only=False,cache='/nonexistent-legacy-cache'))
