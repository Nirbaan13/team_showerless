"""Point-sampled bilinear registration with independent-pixel uncertainties."""
import numpy as np
from astropy.wcs import WCS


def target_wcs(grid):
    w = WCS(naxis=2)
    w.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    w.wcs.radesys = 'ICRS'
    w.wcs.crval = [grid['ra_degrees'], grid['dec_degrees']]
    w.wcs.crpix = [(grid['width']+1)/2, (grid['height']+1)/2]
    w.wcs.cdelt = [-grid['pixel_scale_arcsec']/3600, grid['pixel_scale_arcsec']/3600]
    return w


def resample(frame, grid):
    h, w = grid['height'], grid['width']
    yy, xx = np.mgrid[:h, :w]
    sh, sw = frame.image.shape
    if grid['kind'] == 'sky':
        if frame.wcs is None:
            raise ValueError('sky registration requires celestial WCS; use explicit pixel grid for rasters')
        # SkyCoord transformations account for differing celestial frames/equinox.
        world = target_wcs(grid).pixel_to_world(xx, yy)
        x, y = frame.wcs.world_to_pixel(world)
    else:
        x, y = (xx+.5)*sw/w-.5, (yy+.5)*sh/h-.5
    # WCS roundoff must not discard exact edge pixels or inject tiny neighbor weights.
    x = np.where(np.abs(x-np.rint(x)) < 1e-7, np.rint(x), x)
    y = np.where(np.abs(y-np.rint(y)) < 1e-7, np.rint(y), y)
    finite = np.isfinite(x) & np.isfinite(y)
    safe_x = np.clip(np.where(finite, x, -2), -2, sw+1)
    safe_y = np.clip(np.where(finite, y, -2), -2, sh+1)
    ix, iy = np.floor(safe_x).astype(int), np.floor(safe_y).astype(int)
    dx, dy = safe_x-ix, safe_y-iy
    total = np.zeros((h, w)); signal = np.zeros((h, w)); varsum = np.zeros((h, w))
    missing_var = np.zeros((h, w), bool)
    outlier = np.zeros((h, w), bool); bloom = outlier.copy()
    for ox, oy, weight in [(0, 0, (1-dx)*(1-dy)), (1, 0, dx*(1-dy)),
                           (0, 1, (1-dx)*dy), (1, 1, dx*dy)]:
        sx, sy = ix+ox, iy+oy
        inside = finite & (sx >= 0) & (sx < sw) & (sy >= 0) & (sy < sh) & (weight > 0)
        sx, sy = np.clip(sx, 0, sw-1), np.clip(sy, 0, sh-1)
        good = inside & frame.valid[sy, sx]
        wt = np.where(good, weight, 0)
        total += wt
        signal += wt*np.where(good, frame.image[sy, sx], 0)
        known = frame.variance_valid[sy, sx]
        varsum += wt**2*np.where(known, frame.variance[sy, sx], 0)
        missing_var |= good & ~known
        outlier |= inside & frame.outlier[sy, sx]
        bloom |= inside & frame.bloom[sy, sx]
    valid = total >= 0.995
    image = np.divide(signal, total, out=np.full((h, w), np.nan), where=valid)
    variance_valid = valid & ~missing_var
    variance = np.divide(varsum, total**2, out=np.full((h, w), np.nan), where=variance_valid)
    return dict(images=image, valid_mask=valid, variance=variance, variance_valid_mask=variance_valid,
                footprint=np.clip(total, 0, 1), outlier=outlier, bloom=bloom)
