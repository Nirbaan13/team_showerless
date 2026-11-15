"""Engineering contract checks; no science labels or model fitting."""
import numpy as np
from ml_inference.detector import Candidate
from ml.pvusatov.experiments.v4.feature_performance_boundary import boundary


def test_measured_candidates_finite_paths_and_support_controls():
    data = boundary.make_inputs(8, 17, 'finite_support')
    images, times, tracks, options, evidence = data
    assert images.shape == (8,64,64)
    assert np.isnan(images[-1]).all()
    assert np.all(images[-2] == 0)
    assert np.diff(times).min() > 0
    assert all(isinstance(t, Candidate) for t in tracks)
    assert all(np.isfinite(t.features()).all() for t in tracks)
    assert all(np.isfinite(images[list(t.epochs), np.asarray(t.positions_xy)[:,1].astype(int), np.asarray(t.positions_xy)[:,0].astype(int)]).all() for t in tracks)
    assert evidence['boundary_group_rows'] == 17
    assert options['outlier'].dtype == np.bool_
    assert options['bloom'].dtype == np.bool_


def test_4096_boundary_remainder_preserves_all_columns_and_actual_score_order():
    result = boundary.run_case(16, 4097, 'signed_quality', boundary.load_fixed_ranker())
    assert result['boundary_group_verified']
    assert result['observed_valid_epoch_counts']['16'] == 4097
    assert result['rows'] == 4101
    assert result['all_contract_equal'], result
    assert result['producer_source_distinct']
    assert result['score_rows'] == 4101
    assert result['reference_unique_score_count'] < 4101  # actual ties exercise stable order
    assert result['stable_full_order_equal']


def test_empty_pool_has_full_contract_and_no_fabricated_score_rows():
    result = boundary.run_case(8, 0, 'finite_noise', boundary.load_fixed_ranker(), empty=True)
    assert result['rows'] == result['score_rows'] == 0
    assert result['all_contract_equal'], result
    assert result['prototype_batch']['valid_rows'] == 0
