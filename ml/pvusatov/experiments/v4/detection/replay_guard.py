"""Validate replay against the cache producer's exact observable representation.

cache_native._record_measurement explicitly stores legacy features as Float32.
Geometry remains exact; no truth positions enter this guard. This corrects only
an over-strict Float64-vs-Float32 comparison, never a matching tolerance.
"""
import numpy as np


def validate_replay(tracks,field):
    if [list(t.epochs)for t in tracks]!=field['candidate_epochs']:
        raise AssertionError('baseline epoch reconstruction differs')
    if len(tracks)!=len(field['candidate_positions_xy']):
        raise AssertionError('baseline position count differs')
    for t,xy in zip(tracks,field['candidate_positions_xy']):
        np.testing.assert_array_equal(t.positions_xy,xy)
    actual=np.asarray([t.features()for t in tracks],np.float32).reshape(-1,6)
    expected=np.asarray(field['features'],np.float32).reshape(-1,6)
    if not np.isfinite(actual).all()or not np.isfinite(expected).all():
        raise ValueError('nonfinite observable replay features')
    np.testing.assert_array_equal(actual,expected)
