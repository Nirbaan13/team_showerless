"""Validate recorded matched geometry without loading science or changing rows.

The frozen producer stores maximum pairwise spans over actual matched epochs
(truth can include registration jitter). Stored Float64 distances allow 1e-9
pixel absolute / 1e-12 relative roundoff; the 1.5 pixel matching boundary allows
only 1e-12 pixel arithmetic roundoff. Neither tolerance changes any match label.
"""
import math


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _points(value, length):
    return (isinstance(value, list) and len(value) == length
            and all(isinstance(row, list) and len(row) == 2
                    and all(_number(v) for v in row) for row in value))


def _span(points):
    return max((math.dist(a, b) for a in points for b in points), default=0.)


def validate_matched_geometry(field, times_hours, *, native: bool) -> None:
    """Reject missing, duplicate, misaligned or numerically false geometry."""
    if (not isinstance(times_hours, list) or not all(_number(t) for t in times_hours)
            or any(a >= b for a, b in zip(times_hours, times_hours[1:]))):
        raise ValueError('matched geometry times are invalid')
    count = field.get('truth_count'); matches = field.get('matches')
    if (type(count) is not int or count < 0 or (native and count != 1)
            or not isinstance(matches, list)
            or any(type(m) is not int or m < -2 or m >= count for m in matches)):
        raise ValueError('matched geometry truth/match indices are invalid')
    paths = [field.get('expected_xy')] if native else field.get('expected_xy')
    if (not isinstance(paths, list) or len(paths) != count
            or any(not _points(path, len(times_hours)) for path in paths)):
        raise ValueError('matched geometry truth positions are invalid')
    epochs = field.get('candidate_epochs'); positions = field.get('candidate_positions_xy')
    geometry = field.get('matched_geometry')
    if (not isinstance(epochs, list) or not isinstance(positions, list)
            or len(epochs) != len(matches) or len(positions) != len(matches)
            or not isinstance(geometry, list)):
        raise ValueError('matched geometry candidate alignment is invalid')
    for observed, xy in zip(epochs, positions):
        if (not isinstance(observed, list) or not observed
                or any(type(e) is not int or not 0 <= e < len(times_hours) for e in observed)
                or observed != sorted(set(observed)) or not _points(xy, len(observed))):
            raise ValueError('matched geometry epochs/positions are invalid')
    required = {i for i, match in enumerate(matches) if match >= 0}; seen = set()
    for record in geometry:
        if not isinstance(record, dict):
            raise ValueError('matched geometry record is invalid')
        i = record.get('candidate_index'); truth = record.get('truth_index')
        if (type(i) is not int or i not in required or i in seen
                or type(truth) is not int or truth != matches[i]
                or record.get('epochs') != epochs[i]):
            raise ValueError('matched geometry identity/epochs differ')
        seen.add(i)
        expected = [paths[truth][e] for e in epochs[i]]; measured = positions[i]
        offset = max(math.dist(a, b) for a, b in zip(expected, measured))
        if offset > 1.5 + 1e-12:
            raise ValueError('matched geometry exceeds 1.5 pixel matching radius')
        recomputed = dict(true_displacement_px=_span(expected),
                          measured_displacement_px=_span(measured), max_offset_px=offset)
        for key, actual in recomputed.items():
            value = record.get(key)
            if (not _number(value) or value < 0
                    or not math.isclose(value, actual, rel_tol=1e-12, abs_tol=1e-9)):
                raise ValueError('matched geometry distance differs: ' + key)
    if seen != required:
        raise ValueError('matched geometry missing positive candidate rows')
