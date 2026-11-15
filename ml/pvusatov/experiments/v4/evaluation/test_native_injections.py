"""Controlled generator parity; never opens native data, models or FINAL inputs."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import warnings

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent


def load(path, name):
    assert path.is_file(), 'native injection repair has not been implemented'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


@pytest.fixture
def controlled():
    legacy_path = HERE.parents[2] / 'backend/inference/experiments/v3_evaluation/run_native.py'
    legacy = load(legacy_path, 'v4_test_immutable_native_helpers')
    images = np.random.default_rng(3800800).normal(size=(8, 24, 24))
    images[:, 0, 0] = np.nan
    stack = SimpleNamespace(images=images, times=np.array([0., .03, .17, .35, .5, .8, 1.2, 1.5]), grid=object())
    template = np.arange(576, dtype=float).reshape(24, 24) / 575.
    responses = np.asarray([(i + 1) * template for i in range(8)])

    def project(native, grid, xy):
        return responses[native].copy(), {'controlled_response_epoch': native}

    def add(images, response, flux):
        return np.where(np.isfinite(images), images + flux * response, np.nan)

    science = SimpleNamespace(project_response=project, add_injection=add)
    parent = {'parent_id': 'controlled-parent', '_scope': 'development', 'seed': 3800801}
    return parent, stack, list(range(8)), science, [24, 24], legacy


def test_every_nonempty_trial_is_byte_identical_to_immutable_legacy(controlled):
    helper = load(HERE / 'native_injections.py', 'v4_test_native_injections')
    parent, stack, natives, science, shape, legacy = controlled
    original = stack.images.copy()
    expected = list(legacy._native_latents(parent, stack, natives, science, shape, None))
    actual = list(helper.native_latents(*controlled))
    assert len(expected) == len(actual) == 270
    for (old_id, old_image, old_xy, old_error), (identity, images, xy, error) in zip(expected, actual):
        assert old_error is error is None
        assert {key: identity[key] for key in old_id} == old_id
        np.testing.assert_array_equal(xy, old_xy)
        assert images.dtype == np.float64 and images.tobytes() == old_image.tobytes()
    assert stack.images.tobytes() == original.tobytes()


def test_blank_epoch_retains_all_times_trials_and_uses_only_seven_noise_references(controlled):
    helper = load(HERE / 'native_injections.py', 'v4_test_native_injections_blank')
    parent, stack, natives, science, shape, legacy = controlled
    expected = list(legacy._native_latents(parent, stack, natives, science, shape, None))
    stack.images[2] = np.nan
    original = stack.images.copy()
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        actual = list(helper.native_latents(*controlled))
    assert len(actual) == 270
    mad = [1.4826 * np.median(abs(values - np.median(values)))
           for image in stack.images if np.isfinite(image).any()
           for values in [image[np.isfinite(image)]]]
    for (identity, images, xy, error), (old_id, _, old_xy, _) in zip(actual, expected):
        assert error is None
        assert images.shape == (8, 24, 24) and np.isnan(images[2]).all()
        assert len(identity['center_usable_flags']) == 8 and identity['center_usable_flags'][2] is False
        assert identity['noise_reference_usable_epoch_count'] == 7
        assert identity['usable_center_epochs'] == sum(identity['center_usable_flags'])
        np.testing.assert_array_equal(xy, old_xy)
        assert identity['origin_xy'] == old_id['origin_xy']
        assert identity['velocity_xy_hour'] == old_id['velocity_xy_hour']
        peaks = np.arange(1., 9.)
        supported = peaks[np.asarray(identity['center_usable_flags'])]
        normalization = np.median(supported if len(supported) else peaks)
        assert identity['injected_flux'] == identity['brightness'] * float(np.median(mad)) / normalization
    assert stack.images.tobytes() == original.tobytes()


@pytest.mark.parametrize('invalid', ['only_two_nonempty', 'nonempty_zero_mad', 'nonfinite_mad'])
def test_invalid_nonempty_noise_never_becomes_a_usable_subset(controlled, invalid):
    helper = load(HERE / 'native_injections.py', 'v4_test_native_injections_invalid')
    parent, stack, natives, science, shape, legacy = controlled
    if invalid == 'only_two_nonempty':
        stack.images[2:] = np.nan
    elif invalid == 'nonempty_zero_mad':
        stack.images[3] = 0.
    else:
        stack.images[3] = np.tile([-1e308, 1e308], (24, 12))
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        actual = list(helper.native_latents(*controlled))
    assert len(actual) == 270
    assert all(images is None and error['phase'] == 'background_normalization'
               and identity['injected_flux'] is None for identity, images, xy, error in actual)


def test_exactly_three_nonempty_epochs_are_kept_with_five_blank_epochs(controlled):
    helper = load(HERE / 'native_injections.py', 'v4_test_native_injections_three')
    parent, stack, natives, science, shape, legacy = controlled
    stack.images[3:] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        actual = list(helper.native_latents(*controlled))
    assert len(actual) == 270
    assert all(error is None and identity['noise_reference_usable_epoch_count'] == 3
               and images.shape == (8, 24, 24) and np.isnan(images[3:]).all()
               for identity, images, xy, error in actual)


def test_no_supported_response_fallback_remains_byte_identical(controlled):
    helper = load(HERE / 'native_injections.py', 'v4_test_native_injections_fallback')
    parent, stack, natives, science, shape, legacy = controlled

    def project(native, grid, xy):
        value = native + 1 if np.array_equal(xy, [12., 12.]) else 0.
        return np.full((24, 24), value), {'controlled_response_epoch': native}

    science.project_response = project
    expected = list(legacy._native_latents(parent, stack, natives, science, shape, None))
    actual = list(helper.native_latents(*controlled))
    assert len(expected) == len(actual) == 270
    for (old_id, old_images, old_xy, old_error), (identity, images, xy, error) in zip(expected, actual):
        assert old_error is error is None
        assert {key: identity[key] for key in old_id} == old_id
        assert images.tobytes() == old_images.tobytes()
        np.testing.assert_array_equal(xy, old_xy)
