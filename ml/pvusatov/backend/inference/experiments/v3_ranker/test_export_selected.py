import numpy as np
import pytest
from export_selected import selected_from_report,validate_rank_parity

def test_export_rejects_a_partial_grid_even_if_it_has_a_selected_candidate():
    with pytest.raises(ValueError,match='132'):
        selected_from_report(dict(final_fields_opened=False,completed_configurations=1,outcomes=[dict(id='x',eligible=True)],selected=dict(id='x'),shared_selection_cohort=dict(shared_eligible=2360)))

def test_small_float_error_cannot_hide_changed_review_order():
    field=dict(parent_id='p',seed=1,trajectory_id=0,brightness=3.,truth_count=1,matches=[0,-2])
    with pytest.raises(ValueError,match='rank'):
        validate_rank_parity([field],[np.asarray([.5000001,.5])],[np.asarray([.5,.5000001])])

def test_stable_exact_ties_preserve_candidate_order_and_both_budgets():
    field=dict(seed=1,truth_count=1,matches=[-1,0,-1])
    r=validate_rank_parity([field],[np.asarray([.5,.5,.1])],[np.asarray([.5,.5,.1])])
    assert r['reference_top1']==r['runtime_top1']==0
    assert r['reference_top3']==r['runtime_top3']==1

def test_low_order_swap_is_reported_when_all_protected_reviews_and_output_membership_match():
    a=np.linspace(.99,.01,120);a[99]=a[98]-1e-7;b=a.copy();b[98],b[99]=b[99],b[98]
    field=dict(seed=1,truth_count=1,matches=[0]+[-1]*119)
    r=validate_rank_parity([field],[a],[b])
    assert r['full_order_mismatches']==1
    assert r['review_budget_mismatches']==0
    assert r['top100_membership_mismatches']==0
    assert r['protected_policy_passes'] is True

def test_output_cap_membership_change_is_rejected_even_if_top3_is_identical():
    a=np.linspace(.99,.01,101);a[100]=a[99]-1e-7;b=a.copy();b[99],b[100]=b[100],b[99]
    field=dict(seed=1,truth_count=1,matches=[0]+[-1]*100)
    with pytest.raises(ValueError,match='parity'):
        validate_rank_parity([field],[a],[b])

def test_runtime_memory_uses_current_linux_process_high_water_not_inherited_rusage():
    from export_selected import peak_rss_mib_from_linux_status
    status='VmRSS:\t120000 kB\nVmHWM:\t132000 kB\n'
    assert peak_rss_mib_from_linux_status(status)==128.90625

def test_historical_selection_source_is_validated_without_rewriting_original_hashes(tmp_path,monkeypatch):
    import hashlib,json
    from export_selected import validate_invocation_sources
    monkeypatch.chdir(tmp_path)
    current=tmp_path/'code.py';current.write_text('new guarded evaluator')
    snapshot=tmp_path/'snapshot';snapshot.mkdir();(snapshot/'code.py').write_text('original selected evaluator')
    expected=hashlib.sha256((snapshot/'code.py').read_bytes()).hexdigest()
    invocation=dict(source_sha256={'code.py':expected},final_fields_opened=False)
    archived=snapshot/'invocation-source.json';archived.write_text(json.dumps(invocation))
    digest=hashlib.sha256(archived.read_bytes()).hexdigest()
    (snapshot/'snapshot-manifest.json').write_text(json.dumps(dict(invocation_sha256=digest,files=[dict(path='code.py',sha256=expected)])))
    with pytest.raises(ValueError,match='checksum'):
        validate_invocation_sources(invocation)
    binding=validate_invocation_sources(invocation,snapshot,invocation_sha256=digest)
    assert binding['mode']=='immutable historical selection source snapshot'
    assert invocation['source_sha256']=={'code.py':expected}
