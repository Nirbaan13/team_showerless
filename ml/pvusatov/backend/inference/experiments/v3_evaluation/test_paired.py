"""Independent accounting tests using deliberately small paired examples."""
from copy import deepcopy

import pytest

from experiments.v3_evaluation.paired import paired_report, promotion_gate, validate_cache_pair


def native(parent, trial=0, matches=(), eligible=True):
    return dict(parent_id=parent, seed=1, trajectory_id=trial, brightness=3.,
                truth_count=1, matches=list(matches), attribution_eligible=eligible,
                expected_xy=[[0., 0.], [1., 0.], [2., 0.]],
                usable_center_epochs=3)


def test_duplicate_candidates_do_not_recover_one_truth_twice_and_ties_are_stable():
    fields = [dict(seed=12, truth_count=2, matches=[-1, 0, 0, 1])]
    report = paired_report(fields, fields, [[1, 1, 1, 1]], [[0, 2, 1, 3]])
    raw = report['all_planned']
    assert raw['truth_count'] == 2
    assert raw['baseline']['top1'] == 0
    assert raw['baseline']['top3'] == 1
    assert raw['candidate']['top1'] == 1
    assert raw['candidate']['top3'] == 2


def test_control_ambiguity_is_excluded_from_both_systems_only_in_common_cohort():
    baseline = [native('a', matches=[0])]
    candidate = [native('a', matches=[0], eligible=False)]
    report = paired_report(baseline, candidate, [[1]], [[1]])
    assert report['all_planned']['trials'] == 1
    assert report['all_planned']['baseline']['top1'] == 1
    assert report['common_attributable']['trials'] == 0
    assert report['common_attributable']['macro_delta_top1'] is None


def test_missing_or_duplicate_trial_fails_instead_of_intersecting_results():
    row = native('a')
    with pytest.raises(ValueError, match='identities'):
        paired_report([row], [], [[]], [])
    with pytest.raises(ValueError, match='duplicate'):
        paired_report([row, row], [row, row], [[], []], [[], []])


def test_pair_requires_identical_injected_positions():
    row = native('a')
    changed = deepcopy(row)
    changed['expected_xy'][1][0] += .01
    with pytest.raises(ValueError, match='expected_xy'):
        paired_report([row], [changed], [[]], [[]])


@pytest.mark.parametrize('scores', [[float('nan')], [], [1, 2]])
def test_nonfinite_or_misaligned_scores_fail(scores):
    row = native('a', matches=[0])
    with pytest.raises(ValueError, match='scores'):
        paired_report([row], [row], [scores], [[1]])


def test_no_detections_and_zero_truth_controls_are_retained():
    fields = [native('a'), dict(seed=6, truth_count=0, matches=[-1])]
    report = paired_report(fields, fields, [[], [1]], [[], [1]])
    raw = report['all_planned']
    assert raw['trials'] == 2
    assert raw['truth_count'] == 1
    assert raw['baseline']['detected'] == 0
    assert raw['baseline']['top3'] == 0
    assert raw['baseline']['candidate_rows'] == 1
    assert raw['macro_delta_top3'] == 0


def test_parent_macro_and_bootstrap_do_not_treat_derivatives_as_independent():
    base = [native('many', trial=i, matches=[0]) for i in range(100)]
    base += [native('one', matches=[])]
    new = [native('many', trial=i, matches=[]) for i in range(100)]
    new += [native('one', matches=[0])]
    bs = [[1] if f['matches'] else [] for f in base]
    ns = [[1] if f['matches'] else [] for f in new]
    report = paired_report(base, new, bs, ns, bootstrap_samples=1000)
    raw = report['all_planned']
    assert raw['baseline']['top1'] == 100
    assert raw['candidate']['top1'] == 1
    assert raw['independent_groups'] == 2
    assert raw['baseline']['macro_recall1'] == .5
    assert raw['candidate']['macro_recall1'] == .5
    assert raw['macro_delta_top1'] == 0
    assert raw['paired_parent_ci95_top1'] == [-1., 1.]
    assert paired_report(base, new, bs, ns, bootstrap_samples=1000) == report


def test_promotion_rejects_either_budget_regression_even_if_other_budget_improves():
    good = {'common_attributable': dict(macro_delta_top1=.1, macro_delta_top3=.1)}
    bad = {'common_attributable': dict(macro_delta_top1=-.01, macro_delta_top3=.3)}
    assert promotion_gate(good, good)['passes_recovery_gate'] is True
    result = promotion_gate(good, bad)
    assert result['passes_recovery_gate'] is False
    assert any('native' in reason and 'top1' in reason for reason in result['reasons'])


def test_promotion_requires_positive_improvement_and_defined_denominators():
    tied = {'common_attributable': dict(macro_delta_top1=0., macro_delta_top3=0.)}
    absent = {'common_attributable': dict(macro_delta_top1=None, macro_delta_top3=None)}
    assert promotion_gate(tied, tied)['passes_recovery_gate'] is False
    assert promotion_gate(tied, absent)['passes_recovery_gate'] is False


def cache(sigma=1.2):
    return dict(parent_id='a', partition='validation', input_sources=[dict(sha256='abc')],
                times_hours=[0., 1., 2.], registered_shape=[3, 20, 20], center_deg=[4., 5.],
                detector_settings=dict(psf_sigma=sigma, min_speed=.5, snr_threshold=4.))


def test_native_cache_comparison_permits_only_declared_detector_difference():
    validate_cache_pair(cache(), cache(.8))
    changed = cache(.8)
    changed['detector_settings']['min_speed'] = .005
    with pytest.raises(ValueError, match='detector_settings'):
        validate_cache_pair(cache(), changed)


def test_native_cache_comparison_rejects_changed_observations_or_times():
    for column, value in [('input_sources', [dict(sha256='other')]), ('times_hours', [0., 1., 3.])]:
        changed = cache(.8)
        changed[column] = value
        with pytest.raises(ValueError, match=column):
            validate_cache_pair(cache(), changed)


def test_native_cache_comparison_requires_provenance_instead_of_two_missing_values():
    left = cache()
    right = cache(.8)
    del left['input_sources'], right['input_sources']
    with pytest.raises(ValueError, match='input_sources'):
        validate_cache_pair(left, right)


@pytest.mark.parametrize('column,a,b', [
    ('freeze_sha256', 'a'*64, 'b'*64),
    ('preparation_options', {'mask_policy':'motion'}, {'mask_policy':'science'}),
])
def test_final_caches_cannot_mix_freezes_or_preparation(column, a, b):
    left,right = cache(),cache(.8)
    left[column],right[column] = a,b
    with pytest.raises(ValueError, match=column):
        validate_cache_pair(left,right)
    del right[column]
    with pytest.raises(ValueError, match=column):
        validate_cache_pair(left,right)
    right[column] = a
    validate_cache_pair(left,right)
