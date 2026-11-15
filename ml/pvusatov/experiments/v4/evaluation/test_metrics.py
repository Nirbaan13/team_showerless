import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('v4_metrics', Path(__file__).with_name('metrics.py'))
metrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metrics)


def report(delta1=.01, delta3=.02):
    return {name: dict(macro_delta_top1=delta1, macro_delta_top3=delta3)
            for name in ('all_planned', 'common_attributable')}


def test_both_primary_populations_and_both_review_budgets_must_not_regress():
    native = report()
    native['all_planned']['macro_delta_top1'] = -.001
    result = metrics.recovery_gate(report(), native, baseline_controls=10, candidate_controls=10)
    assert not result['passes_recovery_gate']
    assert any('native all_planned top1' in reason for reason in result['reasons'])


def test_undefined_denominator_and_all_zero_gain_do_not_pass():
    undefined = report()
    undefined['common_attributable']['macro_delta_top3'] = None
    assert not metrics.recovery_gate(undefined, report(), baseline_controls=0, candidate_controls=0)['passes_recovery_gate']
    assert not metrics.recovery_gate(report(0., 0.), report(0., 0.), baseline_controls=0, candidate_controls=0)['passes_recovery_gate']


def test_more_unknown_candidates_are_workload_not_false_positive_labels():
    result = metrics.recovery_gate(report(), report(), baseline_controls=100, candidate_controls=126)
    assert not result['passes_recovery_gate']
    assert result['control_workload_ratio'] == 1.26
    assert result['control_truth_labels'] == 'UNKNOWN'


def test_exact_boundary_and_positive_gain_pass_only_scientific_gate():
    result = metrics.recovery_gate(report(), report(), baseline_controls=100, candidate_controls=125)
    assert result['passes_recovery_gate']
    assert result['promotion_authorized'] is False
    assert result['runtime_and_integration_gates_required_separately']


def test_nonzero_candidate_burden_against_zero_baseline_cannot_hide_in_ratio():
    assert not metrics.recovery_gate(report(), report(), baseline_controls=0, candidate_controls=1)['passes_recovery_gate']
