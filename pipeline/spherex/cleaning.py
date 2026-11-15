
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

OUTLIER_BIT = 1 << 19
SOURCE_BIT = 1 << 21
BLOOM_BIT = 1 << 26
def allowed_bits(retain_outliers=False):
    return SOURCE_BIT | (OUTLIER_BIT if retain_outliers else 0)
def build_mask(flags, signal, variance, retain_outliers=False):
    flags = np.asarray(flags).astype(np.int64)
    good = ((flags & ~allowed_bits(retain_outliers)) == 0) & np.isfinite(signal)
    if variance is not None:
        good &= np.isfinite(variance) & (variance > 0)
    return ~good

def load_clean_cutout(path, retain_outliers=False):
    """Return (img, bad, clean_m, meta). clean_m = IMAGE - ZODI with bad pixels set to NaN."""
    with fits.open(path, lazy_load_hdus=True) as hdul:
        img = hdul["IMAGE"].data.astype(float)
        flags = hdul["FLAGS"].data
        zodi = hdul["ZODI"].data.astype(float)
        variance = hdul["VARIANCE"].data.astype(float)
        head = hdul["IMAGE"].header.copy()
    clean = img - zodi
    bad = build_mask(flags, clean, variance, retain_outliers)
    clean_m = np.where(bad, np.nan, clean)
    valid_zodi = zodi[np.isfinite(zodi)]
    meta = {
        "detector": head.get("DETECTOR"),
        "mjd": head.get("MJD-AVG", head.get("MJD-OBS")),
        "flag_pix_perc": round(float(np.mean(bad) * 100.0), 2),
        "zodi_med_mjy": round(float(np.median(valid_zodi)), 3) if valid_zodi.size else None,
        "wcs": WCS(head).celestial,
    }
    return img, bad, clean_m, meta
