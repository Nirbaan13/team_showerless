"""Project calibrated SPHEREx FITS cutouts onto one north-up ICRS grid."""

import argparse
import csv
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates

SOURCE_BIT = 1 << 21
OUTLIER_BIT = 1 << 19
BLOOM_BIT = 1 << 26


def make_grid(ra, dec, width, height, pixel_scale):
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.crpix = [(width + 1) / 2, (height + 1) / 2]
    wcs.wcs.cdelt = [-pixel_scale / 3600] * 2
    return wcs


def align_exposure(path, sky_ra, sky_dec, retain_outliers, include_bloom):
    # Only the four science HDUs are needed. The PSF and wavelength arrays can be large.
    with fits.open(path, lazy_load_hdus=True) as hdus:
        image = hdus['IMAGE']
        header = image.header.copy()
        signal = image.data.astype(float) - hdus['ZODI'].data
        flags = hdus['FLAGS'].data.astype(np.int64)
        variance = hdus['VARIANCE'].data
        allowed = SOURCE_BIT | (OUTLIER_BIT if retain_outliers else 0)
        good = ((flags & ~allowed) == 0) & np.isfinite(signal) & np.isfinite(variance) & (variance > 0)
        x, y = WCS(header).celestial.world_to_pixel_values(sky_ra, sky_dec)
        projected = map_coordinates(np.where(good, signal, 0), [y, x], order=1, cval=0)
        support = map_coordinates(good.astype(float), [y, x], order=1, cval=0)
        usable = support >= 0.995
        if not usable.any():
            raise ValueError(f'{path.name} has no usable coverage of the requested grid')
        projected[usable] /= support[usable]
        projected[~usable] = np.nan
        projected -= np.nanmedian(projected)
        flagged = map_coordinates(((flags & OUTLIER_BIT) != 0).astype(float), [y, x], order=1, cval=0)
        bloom = (map_coordinates(((flags & BLOOM_BIT) != 0).astype(np.uint8), [y, x],
                                 order=0, cval=0).astype(bool) if include_bloom else None)
        return header['MJD-AVG'], header['DATE-AVG'], path.stem, projected, flagged > 0, bloom


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fits', type=Path, nargs='+', metavar='FITS', help='Cutouts named by observation ID')
    parser.add_argument('--center', nargs=2, type=float, required=True, metavar=('RA', 'DEC'))
    parser.add_argument('--shape', nargs=2, type=int, default=[256, 144], metavar=('WIDTH', 'HEIGHT'))
    parser.add_argument('--pixel-scale', type=float, default=6.15, help='Arcseconds per pixel')
    parser.add_argument('--retain-outliers', action='store_true', help='Keep OUTLIER pixels and expose their flags separately')
    parser.add_argument('--include-bloom', action='store_true', help='Store BLOOM masks separately for bright-source tracking')
    parser.add_argument('--ephemeris', type=Path, help='Optional CSV with observation_id, ra_deg, dec_deg for evaluation')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    width, height = args.shape
    ra, dec = args.center
    if (len(args.fits) < 3 or not 8 <= min(width, height) <= max(width, height) <= 512
            or not 0 <= ra < 360 or not -90 < dec < 90 or not 0 < args.pixel_scale <= 60):
        parser.error('Use at least three exposures, a sky center in degrees, and a grid from 8 to 512 pixels')

    grid = make_grid(*args.center, width, height, args.pixel_scale)
    yy, xx = np.indices((height, width))
    sky_ra, sky_dec = grid.pixel_to_world_values(xx, yy)
    try:
        rows = [align_exposure(path, sky_ra, sky_dec, args.retain_outliers, args.include_bloom) for path in args.fits]
        mjd, dates, ids, images, flags, bloom = zip(*sorted(rows, key=lambda row: row[0]))
        times = (np.array(mjd) - mjd[0]) * 24
        if np.any(np.diff(times) <= 0) or len(set(ids)) != len(ids):
            raise ValueError('Observation IDs and exposure midpoints must be unique')
        payload = dict(images=np.array(images, dtype='float32'), times=times, dates=dates,
                       observation_ids=ids, outlier=np.array(flags),
                       center_deg=args.center, pixel_scale_arcsec=args.pixel_scale,
                       retain_outliers=args.retain_outliers)
        if args.include_bloom:
            payload['bloom'] = np.stack(bloom)
        if args.ephemeris:
            with args.ephemeris.open(newline='') as source:
                values = {row['observation_id']: (float(row['ra_deg']), float(row['dec_deg']))
                          for row in csv.DictReader(source)}
            target_ra, target_dec = np.array([values[identifier] for identifier in ids]).T
            x, y = grid.world_to_pixel_values(target_ra, target_dec)
            payload['expected_xy'] = np.column_stack((x, y))
    except (KeyError, OSError, ValueError) as error:
        parser.error(str(error))
    np.savez_compressed(args.output, **payload)


if __name__ == '__main__':
    main()
