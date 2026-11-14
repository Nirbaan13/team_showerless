import numpy as np
from reproject import reproject_interp

from spherex.cleaning import load_clean_cutout


def align_ref(paths):
    """
    Align a sequence of SPHEREx cutout FITS files to the first frame's WCS.
    Returns:
        aligned: np.ndarray of shape (N, H, W)
        metas: list of metadata dicts
        ref_wcs: the reference WCS object
    """
    aligned = []
    metas = []
    ref_wcs = None
    ref_shape = None

    for i, p in enumerate(paths):
        _, _, clean_m, meta = load_clean_cutout(p)
        if i == 0:
            ref_wcs = meta['wcs']
            ref_shape = clean_m.shape
            aligned.append(clean_m)
        else:
            warped, _ = reproject_interp(
                (clean_m, meta['wcs']),
                ref_wcs,
                shape_out=ref_shape
            )
            aligned.append(warped)
        metas.append(meta)

    return np.array(aligned), metas, ref_wcs


def sub_med_ref(aligned):
    """
    Compute median-subtracted difference stack across multi-epoch frames.
    Returns:
        diff_stack: (N, H, W) difference frames
        med_sky: (H, W) static celestial background
    """
    med_sky = np.nanmedian(aligned, axis=0)
    diff_stack = aligned - med_sky
    return diff_stack, med_sky
