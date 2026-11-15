"""Truth/coverage diagnostics only; no candidate scores or detection guarantees.

These necessary geometric conditions never change the all-planned denominator.
The three-pixel span is an explicit diagnostic threshold, not a calibrated test
of physical motion or source detectability in correlated image noise.
"""
from __future__ import annotations

import numpy as np


def geometry_capability(expected_xy, times_hours, usable_centers, *, min_epochs=3, minimum_span_px=3.):
    positions = np.asarray(expected_xy, dtype=float)
    times = np.asarray(times_hours, dtype=float)
    usable = np.asarray(usable_centers)
    if (positions.ndim != 2 or positions.shape[1] != 2 or len(positions) < 3
            or times.shape != (len(positions),) or usable.shape != times.shape
            or usable.dtype.kind != 'b' or not np.isfinite(positions).all()
            or not np.isfinite(times).all() or np.any(np.diff(times) <= 0)
            or type(min_epochs) is not int or min_epochs < 3
            or not np.isfinite(minimum_span_px) or minimum_span_px <= 0):
        raise ValueError('invalid truth, time, coverage or diagnostic thresholds')
    covered = positions[usable]
    count = int(usable.sum())
    span = float(np.max(np.linalg.norm(covered[:, None] - covered[None, :], axis=-1))) if count else 0.
    duration = float(np.ptp(times[usable])) if count >= 2 else 0.
    return dict(finite_center_epochs=count, covered_truth_span_px=span,
                covered_time_span_hours=duration, finite_centers_ge_min_epochs=count >= min_epochs,
                resolved_truth_span_ge3px=span >= minimum_span_px,
                geometrically_testable=count >= min_epochs and span >= minimum_span_px,
                minimum_speed_for_three_pixel_span_px_hour=minimum_span_px / duration if duration > 0 else None,
                diagnostic_only=True)
