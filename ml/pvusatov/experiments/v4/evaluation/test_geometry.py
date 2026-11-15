import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location('v4_geometry', Path(__file__).with_name('geometry.py'))
geometry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(geometry)


def test_coverage_and_motion_are_separate_necessary_conditions():
    result = geometry.geometry_capability([[0., 0.], [2., 0.], [4., 0.]], [0., 1., 2.], [True, True, True])
    assert result['finite_center_epochs'] == 3
    assert result['covered_truth_span_px'] == 4.
    assert result['geometrically_testable'] is True
    assert result['minimum_speed_for_three_pixel_span_px_hour'] == 1.5


def test_span_uses_all_covered_positions_not_only_first_and_last():
    result = geometry.geometry_capability([[0., 0.], [7., 0.], [0., 0.]], [0., 1., 2.], [True] * 3)
    assert result['covered_truth_span_px'] == 7.


def test_long_displacement_does_not_hide_missing_epochs():
    result = geometry.geometry_capability([[0., 0.], [2., 0.], [4., 0.]], [0., 1., 2.], [True, False, True])
    assert result['covered_truth_span_px'] == 4.
    assert result['geometrically_testable'] is False


def test_near_static_truth_and_no_coverage_are_reported_without_dropping_truth():
    result = geometry.geometry_capability([[0., 0.], [.1, 0.], [.2, 0.]], [0., 1., 2.], [True] * 3)
    assert result['finite_center_epochs'] == 3
    assert result['resolved_truth_span_ge3px'] is False
    empty = geometry.geometry_capability([[0., 0.]] * 3, [0., 1., 2.], [False] * 3)
    assert empty['finite_center_epochs'] == 0
    assert empty['minimum_speed_for_three_pixel_span_px_hour'] is None


@pytest.mark.parametrize('times,flags', [([0., 0., 1.], [True] * 3), ([0., 1., 2.], [1, 1, 1]), ([0., 1.], [True] * 3)])
def test_invalid_time_or_coverage_cannot_create_an_observability_claim(times, flags):
    with pytest.raises(ValueError):
        geometry.geometry_capability([[0., 0.]] * 3, times, flags)


def test_inputs_are_not_changed():
    positions = np.array([[0., 0.], [2., 0.], [4., 0.]])
    original = positions.copy()
    geometry.geometry_capability(positions, [0., 1., 2.], [True] * 3)
    np.testing.assert_array_equal(positions, original)
