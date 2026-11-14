import numpy as np
from astropy.io import fits

def load_clean_cutout(path):
  with fits.open(path) as hdul:
    img = hdul["IMAGE"].data.astype(float)
    flags = hdul["FLAGS"].data
    zodi = hdul["ZODI"].data.astype(float)
    head = hdul["IMAGE"].header

    bad = flags != 0
    flagged = float(np.man(bad) * 100.0)
    clean = img - zodi
    clean_m = np.where(bad, np.nan, clean)

    meta = {
    'detector': head.get("DETECTOR"),
    'mjd': head.get("MJD-AVG", head.get("MJD-OBS")),
    'flag_pix_perc': round(flagged, 2),
    'zodi_med_mjy': round(float(np.nanmedian(zodi)), 3),
    }

    return img, bad, clean_m, meta
