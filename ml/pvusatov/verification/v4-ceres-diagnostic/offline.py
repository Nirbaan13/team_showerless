"""Offline positional compatibility only; never imported by prediction code."""
import numpy as np
from astropy.wcs import WCS
TOLERANCE_PX=1.5
MINIMUM_EPOCHS=3

def grid_wcs(grid):
    if grid['projection']!='TAN'or grid['coordinate_origin']!='zero_based_xy':raise ValueError('Unexpected registered coordinate convention')
    w=WCS(naxis=2);w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crval=grid['center_deg'];w.wcs.crpix=grid['crpix_fits'];w.wcs.cdelt=grid['cdelt_deg'];return w

def offsets(candidate,expected):
    points=candidate['detections'];epochs=[p['frame_index']for p in points]
    if any(type(i)is not int or not 0<=i<len(expected)for i in epochs)or epochs!=sorted(set(epochs)):raise ValueError('Invalid observed epoch identity')
    xy=np.array([[p['x'],p['y']]for p in points],dtype=float).reshape(-1,2)
    if not np.isfinite(xy).all():raise ValueError('Nonfinite observed position')
    distances=np.linalg.norm(xy-np.asarray(expected)[epochs],axis=1)
    return dict(epochs=epochs,offsets_px=distances.tolist(),max_offset_px=float(distances.max())if len(distances)else None,median_offset_px=float(np.median(distances))if len(distances)else None,compatible=bool(len(epochs)>=MINIMUM_EPOCHS and np.all(distances<=TOLERANCE_PX)))
