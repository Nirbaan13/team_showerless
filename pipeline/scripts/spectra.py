import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_area

from spherex.cleaning import load_clean_cutout


def measure_cutout_point(path, ra_deg, dec_deg, radius_pix=2.0, subtraction="zodi_subtracted"):
    img, bad, clean_m, meta = load_clean_cutout(path)
    if subtraction == "raw_calibrated":
        clean_m = np.where(bad, np.nan, img)
    elif subtraction != "zodi_subtracted":
        raise ValueError("Unsupported subtraction mode")

    with fits.open(path) as hdul:
        head = hdul["IMAGE"].header
        var = hdul["VARIANCE"].data.astype(float)

        # RA, Dec -> pixel (x, y)
        spatial_wcs = WCS(head)
        coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg)
        x, y = spatial_wcs.world_to_pixel(coord)
        x, y = float(x), float(y)

        ny, nx = clean_m.shape
        if not (radius_pix <= x <= nx - 1 - radius_pix and
                radius_pix <= y <= ny - 1 - radius_pix):
            return None  # Target is outside this cutout

        # pixel (x, y) -> (wavelength, bandwidth) from WCS-WAVE
        wave_wcs = WCS(head, fobj=hdul, key="W")
        wave_wcs.sip = None
        lam, bw = wave_wcs.pixel_to_world(x, y)
        wavelength_um = float(lam.to(u.um).value)
        bandwidth_um = float(bw.to(u.um).value)

        #circular aperture around (x, y)
        yy, xx = np.ogrid[:ny, :nx]
        in_ap = (xx - x) ** 2 + (yy - y) ** 2 <= radius_pix**2

        if np.any(bad[in_ap]) or np.any(~np.isfinite(clean_m[in_ap])):
            return None  # Skip if aperture touches a flagged pixel

        # MJy/sr -> mJy using pixel solid angle
        pix_sr = (proj_plane_pixel_area(spatial_wcs) * u.deg**2).to(u.sr).value
        scale_mjy = 1e9 * pix_sr

        flux_mjy = float(np.sum(clean_m[in_ap]) * scale_mjy)
        err_mjy = float(np.sqrt(np.sum(var[in_ap])) * scale_mjy)
        snr = flux_mjy / err_mjy if err_mjy > 0 else 0.0

        return {
            "file": str(path),
            "mjd": meta["mjd"],
            "detector": meta["detector"],
            "wavelength_um": round(wavelength_um, 4),
            "bandwidth_um": round(bandwidth_um, 4),
            "flux_mjy": flux_mjy,
            "uncertainty_mjy": err_mjy,
            "snr": round(snr, 2),
            "x_pix": round(x, 2),
            "y_pix": round(y, 2),
        }


def extract_spectrum(cutout_paths, ra_deg, dec_deg, radius_pix=2.0):
    rows = []
    for p in cutout_paths:
        pt = measure_cutout_point(p, ra_deg, dec_deg, radius_pix=radius_pix)
        if pt is not None:
            rows.append(pt)

    tbl = Table(rows=rows)
    if len(tbl) > 0:
        tbl.sort("wavelength_um")
    return tbl
