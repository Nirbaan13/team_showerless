"""Paired, parent-aware recovery accounting for frozen inference experiments."""
from __future__ import annotations

from collections import defaultdict

import numpy as np


def validate_cache_pair(baseline, candidate):
    """Require identical native inputs/options except the declared filter sigma.

    This validates metadata before trial-level pairing. Absolute input paths may
    change during relocation; their ordered byte digests remain authoritative.
    """
    for column in ['parent_id', 'partition', 'input_sources', 'times_hours',
                   'registered_shape', 'center_deg', 'detector_settings']:
        if column not in baseline or column not in candidate:
            raise ValueError('missing paired cache '+column)
        a, b = baseline[column], candidate[column]
        if column == 'input_sources':
            try:
                a, b = [v['sha256'] for v in a], [v['sha256'] for v in b]
            except (KeyError, TypeError) as error:
                raise ValueError('input_sources lacks ordered byte hashes') from error
            if not a or not b:
                raise ValueError('input_sources is empty')
        elif column == 'detector_settings':
            a = {k:v for k,v in a.items() if k != 'psf_sigma'}
            b = {k:v for k,v in b.items() if k != 'psf_sigma'}
        if a != b:
            raise ValueError('paired cache '+column+' differs')


def _identity(field):
    if 'parent_id' in field:
        return ('native', field['parent_id'], field['seed'],
                field['trajectory_id'], field['brightness'])
    return ('synthetic', field['seed'])


def _indexed(fields, scores):
    if len(fields) != len(scores):
        raise ValueError('field scores length mismatch')
    result = {}
    for field, values in zip(fields, scores):
        key = _identity(field)
        if key in result:
            raise ValueError('duplicate trial identities')
        values = np.asarray(values, dtype=float)
        labels = field['matches']
        if values.ndim != 1 or len(values) != len(labels) or not np.isfinite(values).all():
            raise ValueError('scores must be finite and aligned with candidates')
        count = field['truth_count']
        if not isinstance(count, int) or count < 0:
            raise ValueError('truth_count must be a nonnegative integer')
        if any(not isinstance(m, int) or m < -2 or m >= count for m in labels):
            raise ValueError('candidate match index outside truth_count')
        result[key] = (field, values)
    return result


def _counts(field, scores):
    labels = np.asarray(field['matches'], dtype=int)
    order = np.argsort(-scores, kind='stable')

    def unique(indices):
        return len(set(int(v) for v in labels[indices] if v >= 0))

    return dict(detected=unique(order), top1=unique(order[:1]), top3=unique(order[:3]),
                candidate_rows=len(labels))


def _summary(pairs, bootstrap_samples, bootstrap_seed):
    totals = {name:dict(detected=0, top1=0, top3=0, candidate_rows=0)
              for name in ['baseline', 'candidate']}
    groups = defaultdict(lambda:dict(truth_count=0, baseline=dict(top1=0, top3=0),
                                    candidate=dict(top1=0, top3=0)))
    truths = 0
    for left, right in pairs:
        field, scores = left
        group = ('native', field['parent_id']) if 'parent_id' in field else ('synthetic', field['seed'])
        truth_count = field['truth_count']
        truths += truth_count
        groups[group]['truth_count'] += truth_count
        for name, (trial, values) in [('baseline', left), ('candidate', right)]:
            counts = _counts(trial, values)
            for metric, value in counts.items():
                totals[name][metric] += value
            for metric in ['top1', 'top3']:
                groups[group][name][metric] += counts[metric]
    evaluable = [row for row in groups.values() if row['truth_count'] > 0]
    report = dict(trials=len(pairs), truth_count=truths, independent_groups=len(groups),
                  groups_with_truth=len(evaluable), **totals)
    if evaluable:
        rng = np.random.default_rng(bootstrap_seed)
        draws = rng.integers(0, len(evaluable), size=(bootstrap_samples, len(evaluable)))
    for k in [1, 3]:
        rates = {}
        for name in totals:
            rates[name] = np.asarray([row[name]['top'+str(k)] / row['truth_count'] for row in evaluable])
            report[name]['micro_recall'+str(k)] = totals[name]['top'+str(k)] / truths if truths else None
            report[name]['macro_recall'+str(k)] = float(rates[name].mean()) if evaluable else None
        delta = rates['candidate'] - rates['baseline']
        report['macro_delta_top'+str(k)] = float(delta.mean()) if evaluable else None
        report['paired_parent_ci95_top'+str(k)] = (
            np.quantile(delta[draws].mean(axis=1), [.025, .975]).tolist() if evaluable else None)
    report['uncertainty_unit'] = 'independent native parent or synthetic field; derivatives stay clustered'
    return report


def paired_report(baseline_fields, candidate_fields, baseline_scores, candidate_scores,
                  bootstrap_samples=10000, bootstrap_seed=20261114):
    """Compare one frozen pair; reject any silent trial intersection or relabeling."""
    if not isinstance(bootstrap_samples, int) or bootstrap_samples < 1:
        raise ValueError('bootstrap_samples must be a positive integer')
    left = _indexed(baseline_fields, baseline_scores)
    right = _indexed(candidate_fields, candidate_scores)
    if left.keys() != right.keys():
        raise ValueError('paired trial identities differ')
    pairs = []
    for key in sorted(left):
        a, b = left[key][0], right[key][0]
        for column in ['truth_count', 'expected_xy', 'injected_flux', 'speed_px_hour',
                       'origin_xy', 'velocity_xy_hour', 'usable_center_epochs']:
            if a.get(column) != b.get(column):
                raise ValueError('paired '+column+' differs')
        pairs.append((left[key], right[key]))
    common = [pair for pair in pairs if all(trial.get('attribution_eligible', True)
                                          for trial, _ in pair)]
    covered = [pair for pair in common if all(trial.get('usable_center_epochs', 3) >= 3
                                             for trial, _ in pair)]
    return dict(schema_version=1,
                all_planned=_summary(pairs, bootstrap_samples, bootstrap_seed),
                common_attributable=_summary(common, bootstrap_samples, bootstrap_seed),
                common_finite_center_ge3=_summary(covered, bootstrap_samples, bootstrap_seed),
                attribution_excluded_trials=len(pairs)-len(common),
                bootstrap_samples=bootstrap_samples, bootstrap_seed=bootstrap_seed)


def promotion_gate(synthetic_report, native_report):
    """Check the preregistered recovery gate; runtime/integration gates are separate."""
    reasons = []
    positive = False
    for name, report in [('synthetic', synthetic_report), ('native', native_report)]:
        for k in [1, 3]:
            metric = 'top'+str(k)
            value = report['common_attributable']['macro_delta_'+metric]
            if value is None or not np.isfinite(value):
                reasons.append(name+' '+metric+' has no defined denominator')
            elif value < 0:
                reasons.append(name+' '+metric+' regresses')
            elif value > 0:
                positive = True
    if not positive:
        reasons.append('no positive recovery improvement')
    return dict(passes_recovery_gate=not reasons, reasons=reasons,
                runtime_and_integration_gates_required_separately=True)
