"""Bitwise parity against the immutable NumPy-based leave-one-out implementation."""
from pathlib import Path
import warnings
import numpy as np
import pytest
from ml_inference.detector import difference_frames as legacy
from ml_inference.prepare import prepare
from ml.pvusatov.experiments.v4.detection.median_reference import leave_one_out_residuals


def same(images):
    before = images.copy()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning)
        expected = legacy(images,leave_one_out=True)
        actual,diagnostics = leave_one_out_residuals(images,return_diagnostics=True)
    np.testing.assert_array_equal(actual.view(np.uint64),expected.view(np.uint64))
    np.testing.assert_array_equal(images,before)
    return diagnostics


def test_all_finite_counts_zero_one_two_ties_and_infinities():
    values = np.asarray([[np.nan,1.,1.,1.,2.,3.,np.inf],
                         [np.nan,np.nan,2.,1.,2.,1.,-np.inf],
                         [np.nan,np.nan,np.nan,1.,2.,2.,3.],
                         [np.nan,np.nan,np.nan,1.,2.,2.,np.nan]],dtype=np.float64)
    diagnostic = same(values[:,:,None])
    assert diagnostic['fast_columns'] == 7


def test_signed_zeros_subnormal_extreme_and_float32_fallback():
    tiny = np.nextafter(np.float64(0),np.float64(1))
    data = np.asarray([[0.,-0.,tiny,1e308,-1e308],[-0.,0.,-tiny,1e308,1e308],[0.,-0.,tiny,-1e308,-1e308]],np.float64)[:,:,None]
    diagnostic = same(data)
    assert diagnostic['fallback_columns'] == 5
    diagnostic = same(np.asarray([1.,2.,3.,4.],np.float32).reshape(4,1,1))
    assert diagnostic['mode'] == 'legacy_non_float64'


@pytest.mark.parametrize('seed',range(3803000,3803100))
def test_prospective_random_masks_and_epoch_permutations(seed):
    rng = np.random.default_rng(seed)
    data = rng.normal(size=(1+seed%32,2+seed%7,3+seed%11))
    data[rng.random(data.shape)<.25] = np.nan
    data[rng.random(data.shape)<.015] = np.inf
    data[rng.random(data.shape)<.015] = -np.inf
    same(data)
    same(data[rng.permutation(len(data))])


@pytest.mark.parametrize('preset',['comet-d2','comet-d6','vesta-d3','vesta-d6'])
def test_all_four_real_development_prepared_images(preset):
    stack = prepare(dict(schema_version=1,analysis_id='median-development',source=dict(kind='preset',preset_id=preset)))
    same(stack.images)


def test_every_valid_count_in_one_stack_and_noncontiguous_layouts():
    data = np.resize(np.asarray([-5.,-3.,-1.,1.,2.,3.,4.]),(32,1,33))
    for count in range(33):
        data[count:,0,count] = np.nan
    same(data)
    same(np.asfortranarray(data))
    same(data[:,:,::-1])
    same(data[::-1])


def test_even_odd_extreme_and_signed_zero_permutations():
    import itertools
    for values in [(-0.,0.,1.),(-0.,0.,-1.,1.),(1e308,1e308,-1e308),(-1e308,-1e308,1e308,1e308)]:
        for order in set(itertools.permutations(range(len(values)))):
            same(np.asarray(values,np.float64)[list(order),None,None])


def test_random_ieee754_bitpatterns_and_wide_exponents():
    rng = np.random.default_rng(3803099)
    for count in [1,2,3,4,7,16,31,32]:
        data = rng.bit_generator.random_raw(count*7*9).reshape(count,7,9).view(np.float64)
        same(data)
        same(data[::-1])


def test_whole_empty_epoch_preserves_other_epoch_reference_values():
    data = np.random.default_rng(3803001).normal(size=(8,13,17))
    data[3] = np.nan
    data[1:,0,0] = np.nan
    data[2:,0,1] = np.nan
    same(data)


@pytest.mark.parametrize('all_exceptional',[False,True])
def test_legacy_fallback_runs_before_allocating_sorted_buffers(all_exceptional):
    from unittest.mock import patch
    from ml.pvusatov.experiments.v4.detection import median_reference as module
    data = np.ones((4,3,5),np.float64)
    if all_exceptional: data.fill(0.)
    else: data[:,:,0] = 0.
    events = []; sorting = np.sort; reference = module.legacy_difference_frames
    def observed_sort(*args,**kwargs):
        events.append('sort'); return sorting(*args,**kwargs)
    def observed_legacy(*args,**kwargs):
        events.append('legacy'); return reference(*args,**kwargs)
    with patch.object(module.np,'sort',side_effect=observed_sort), patch.object(module,'legacy_difference_frames',side_effect=observed_legacy):
        result = module.leave_one_out_residuals(data)
    assert events[0] == 'legacy'
    np.testing.assert_array_equal(result,reference(data,leave_one_out=True))
