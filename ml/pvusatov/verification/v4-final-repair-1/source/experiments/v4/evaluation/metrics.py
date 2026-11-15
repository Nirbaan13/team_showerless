"""Prospective V4 recovery/workload gate; runtime approval remains separate."""
from __future__ import annotations

import math


def recovery_gate(synthetic, native, *, baseline_controls, candidate_controls):
    reasons = []
    positive = False
    for domain, report in [('synthetic', synthetic), ('native', native)]:
        for cohort in ('all_planned', 'common_attributable'):
            for budget in ('top1', 'top3'):
                value = report.get(cohort, {}).get('macro_delta_' + budget)
                label = domain + ' ' + cohort + ' ' + budget
                if type(value) not in (int, float) or not math.isfinite(value):
                    reasons.append(label + ' has no defined denominator')
                elif value < 0:
                    reasons.append(label + ' regresses')
                elif value > 0:
                    positive = True
    if not positive:
        reasons.append('no positive recovery improvement')
    if any(type(value) is not int or value < 0 for value in (baseline_controls, candidate_controls)):
        reasons.append('invalid UNKNOWN-control workload counts')
        ratio = None
    elif baseline_controls:
        ratio = candidate_controls / baseline_controls
        if ratio > 1.25:
            reasons.append('UNKNOWN-control candidate workload exceeds preregistered 1.25 ratio')
    else:
        ratio = 1. if candidate_controls == 0 else None
        if candidate_controls:
            reasons.append('new UNKNOWN-control workload against an empty baseline')
    return dict(passes_recovery_gate=not reasons, reasons=reasons,
                control_workload_ratio=ratio, control_truth_labels='UNKNOWN',
                runtime_and_integration_gates_required_separately=True,
                promotion_authorized=False)
