"""Pure research accounting tests; no new observations, models or latents."""
import importlib.util
from pathlib import Path
import pytest


def module():
    path=Path(__file__).with_name('accounting.py')
    assert path.is_file(), 'association accounting not implemented'
    spec=importlib.util.spec_from_file_location('association_test_accounting',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def test_both_retained_pools_use_c596_ranking_and_original_review_budgets():
    a=module()
    # A's pruning order puts pool0 first; the review order must still use C596.
    result=a.policy_counts([-2,0,0,1],[.1,.9,.8,.7],[0,1,2,3],[2.,2.,2.,4.])
    assert result['top1']==1 and result['top3']==2 and result['detected']==2
    assert result['resolved_top1']==0 and result['resolved_top3']==1
    assert result['unresolved_top1']==1 and result['candidate_rows']==4


def test_duplicate_truths_and_unknowns_do_not_inflate_recovery():
    a=module();result=a.policy_counts([0,0,-2],[.9,.8,.7],[0,1,2],[4.,4.,None])
    assert result['top3']==result['detected']==1
    assert result['resolved_top3']==1 and result['unresolved_top3']==0


def test_common_attribution_is_intersection_of_both_policy_controls():
    a=module()
    assert a.common_attribution([0,-2],{'legacy':[1],'learned_pair':[0]}) == {
        'eligible':False,'preexisting':{'legacy':False,'learned_pair':True}}
    assert a.common_attribution([-2,-2],{'legacy':[0],'learned_pair':[1]})['eligible'] is True


def test_geometric_diagnostic_never_filters_primary_truth_denominator():
    a=module();counts=a.policy_counts([0],[.5],[0],[.2])
    row=dict(seed=4100001,truth_count=1,error=None,attribution_eligible=True,
             policies={'legacy':counts,'learned_pair':counts})
    result=a.paired([row],samples=20,seed=2026111502)
    assert result['all_planned']['truth_count']==1
    assert result['all_planned']['legacy']['top1']==1
    assert result['all_planned']['legacy']['resolved_top1']==0


def test_empty_fields_keep_workload_and_groups_without_fabricated_recall():
    a=module();positive=a.policy_counts([0],[.8],[0],[4.]);empty=a.policy_counts([-1],[.8],[0],[None])
    rows=[dict(seed=4100001,truth_count=1,error=None,attribution_eligible=True,policies={'legacy':positive,'learned_pair':positive}),
          dict(seed=4100000,truth_count=0,error=None,attribution_eligible=True,policies={'legacy':empty,'learned_pair':empty})]
    report=a.paired(rows,samples=20,seed=2026111502)['all_planned']
    assert report['trials']==2 and report['independent_groups']==2 and report['groups_with_truth']==1
    assert report['legacy']['candidate_rows']==2 and report['legacy']['macro_recall1']==1.


def test_errors_and_unknown_truths_cannot_disappear_into_a_successful_report():
    a=module();row=dict(seed=4100000,truth_count=None,error={'phase':'simulation'},attribution_eligible=None,policies={})
    result=a.paired([row],samples=20,seed=2026111502)
    assert result['complete'] is False and result['planned_trials']==1 and result['error_trials']==1
    assert result['all_planned'] is None and result['common_attributable'] is None


def test_invalid_retained_indices_or_nonfinite_scores_reject():
    a=module()
    with pytest.raises(ValueError):a.policy_counts([0],[.5],[0,0],[4.])
    with pytest.raises(ValueError):a.policy_counts([0],[float('nan')],[0],[4.])
