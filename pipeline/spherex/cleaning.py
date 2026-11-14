import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

def load_clean_cutout(path):
  with fits.open(path) as hdul:
    img = hdul["IMAGE"].data.astype(float)
    flags = hdul["FLAGS"].data
    zodi = hdul["ZODI"].data.astype(float)
    head = hdul["IMAGE"].header

    BAD_BITS = 1 | 2 | 4 | 64 | 512 | 1024 | 2048
    bad = (flags & BAD_BITS) != 0
    flagged = float(np.mean(bad) * 100.0)
    clean = img - zodi
    clean_m = np.where(bad, np.nan, clean)

    meta = {
    'detector': head.get("DETECTOR"),
    'mjd': head.get("MJD-AVG", head.get("MJD-OBS")),
    'flag_pix_perc': round(flagged, 2),
    'zodi_med_mjy': round(float(np.nanmedian(zodi)), 3),
    'wcs': WCS(head),
    }

    return img, bad, clean_m, meta
