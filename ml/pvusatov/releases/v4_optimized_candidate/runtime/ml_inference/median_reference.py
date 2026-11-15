"""Exact order-statistic leave-one-out residuals for the versioned runtime.

Function copied without arithmetic edits from the separately verified development
prototype. Exceptional columns retain the unchanged detector implementation.
"""
import numpy as np
from .detector import difference_frames as legacy_difference_frames


def leave_one_out_residuals(images, *, return_diagnostics=False):
    original = np.asarray(images)
    if original.ndim != 3 or not 1 <= len(original) <= 32 or not 1 <= min(original.shape[1:]) <= max(original.shape[1:]) <= 512:
        raise ValueError('bounded1..32epoch2D images required')
    total = int(np.prod(original.shape[1:]))
    if original.dtype != np.dtype(np.float64):
        result = legacy_difference_frames(images, leave_one_out=True)
        diagnostics = dict(mode='legacy_non_float64',fast_columns=0,fallback_columns=total)
        return (result, diagnostics) if return_diagnostics else result
    valid = np.isfinite(original)
    counts = valid.sum(axis=0)
    finfo = np.finfo(np.float64)
    exceptional = np.any(valid & ((original == 0.) | (np.abs(original) < 2*finfo.tiny) |
                                  (np.abs(original) > finfo.max/4)),axis=0)
    fallback = int(exceptional.sum())
    diagnostics = dict(mode='sorted_float64_with_exceptional_column_fallback',fast_columns=total-fallback,
        fallback_columns=fallback,finite_count_min=int(counts.min()),finite_count_max=int(counts.max()),
        fallback_policy='any finite zero/subnormal/abs>Float64max/4; exact legacy arithmetic')
    if fallback == total:
        # Do not retain unused fast-path buffers around the full legacy call.
        del valid, counts, exceptional
        result = legacy_difference_frames(original,leave_one_out=True)
        diagnostics['mode'] = 'legacy_all_exceptional_float64'
        return (result,diagnostics) if return_diagnostics else result
    fallback_result = None
    if fallback:
        # Schedule legacy work before allocating sorted/mean/result cubes.
        columns = original[:,exceptional][:,:,None]
        fallback_result = legacy_difference_frames(columns,leave_one_out=True)[:,:,0]
        del columns
    finite = np.where(valid, original, np.inf)
    sorted_values = np.sort(finite, axis=0)
    del finite
    q = counts // 2
    take = lambda indices: np.take_along_axis(sorted_values,np.clip(indices,0,len(original)-1)[None],axis=0)[0]
    below, middle, above = take(q-1), take(q), take(q+1)
    result = np.full_like(original,np.nan)
    # NumPy masked median duplicates its odd central element then sums/divides.
    # Ordinary values round identically; exceptional arithmetic uses legacy.
    with np.errstate(over='ignore',under='ignore',invalid='ignore'):
        left_mean = (below + middle) / 2.
        skip_mean = (below + above) / 2.
        right_mean = (middle + above) / 2.
        even = counts % 2 == 0
        for epoch,image in enumerate(original):
            odd_reference = np.where(image < middle,right_mean,np.where(image > middle,left_mean,skip_mean))
            even_reference = np.where(image <= below,middle,below)
            reference = np.where(even,even_reference,odd_reference)
            covered = valid[epoch] & (counts >= 2) & ~exceptional
            result[epoch,covered] = image[covered] - reference[covered]
    if fallback:
        result[:,exceptional] = fallback_result
    return (result,diagnostics) if return_diagnostics else result


