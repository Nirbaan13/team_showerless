"""Qualified neo11 W2 visit products; no SPHEREx planes or bit semantics."""
import io
import re

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from .readers import Frame, _bounded_bytes, _plane

ROLES = {'inverse_variance', 'coverage', 'contributors'}
NATIVE_SCALE = 2.75
ZERO_FLUX_JY = 171.787
MAGZP = 22.5
TO_UJY = ZERO_FLUX_JY * 10**(-0.4 * MAGZP) * 1e6


def _number(header, key):
    value = float(header[key])
    if not np.isfinite(value):
        raise ValueError('nonfinite unWISE native metadata')
    return value


def _qualify_header(header, epoch):
    declared = [header[key] for key in ('BAND', 'FILTER') if key in header]
    if declared:
        if any(str(value).strip().upper() not in {'2', 'W2'} for value in declared):
            raise ValueError('unWISE band is not qualified W2')
        band_source = 'native BAND/FILTER and managed W2 product identity'
    else:
        # Early products have no BAND card; this is native reference provenance,
        # corroborated by the managed atlas/filename selection, not a new HDU.
        if not str(header.get('REFEREN1', '')).strip().endswith('_w2'):
            raise ValueError('unWISE native band reference is unavailable')
        band_source = 'atlas W2, managed W2 product identity and native REFEREN1'
    if _number(header, 'EPOCH') != epoch or str(header.get('UNW_DVER', '')).strip() != '3.3':
        raise ValueError('unWISE epoch or processing version does not match qualified product')
    if not np.isclose(_number(header, 'MAGZP'), MAGZP, rtol=0, atol=1e-7):
        raise ValueError('unWISE flux zero point is not qualified')
    if str(header.get('TIMESYS', 'UTC')).strip().upper() != 'UTC':
        raise ValueError('unWISE source time scale is not qualified UTC')
    start, end = (_number(header, key) for key in ('MJDMIN', 'MJDMAX'))
    if not 50000 < start < end < 70000 or end - start > 45:
        raise ValueError('unWISE visit interval is invalid or not a visit coadd')
    wcs = WCS(header).celestial
    if (not wcs.has_celestial or wcs.pixel_n_dim != 2 or wcs.has_distortion
            or list(wcs.wcs.ctype) != ['RA---TAN', 'DEC--TAN']):
        raise ValueError('qualified unWISE requires an undistorted two-dimensional TAN WCS')
    scales = np.sqrt(np.sum(wcs.pixel_scale_matrix**2, axis=0)) * 3600
    if not np.allclose(scales, NATIVE_SCALE, atol=1e-6, rtol=0):
        raise ValueError('unWISE native sampling is not qualified')
    return wcs, start, end, band_source


def _image(path):
    with fits.open(io.BytesIO(_bounded_bytes(path)), memmap=False) as hdus:
        if len(hdus) != 1 or not isinstance(hdus[0], fits.PrimaryHDU):
            raise ValueError('unWISE product must be a primary image')
        return _plane(hdus[0], []), hdus[0].header.copy()


def _contributors(path, start, end):
    with fits.open(io.BytesIO(_bounded_bytes(path)), memmap=False) as hdus:
        if len(hdus) > 32:
            raise ValueError('unWISE contributor HDU count exceeds limit')
        # neo11 also contains astrometric coefficients and a solution summary.
        # Select the exposure table by its schema, never by an assumed count.
        tables = [h for h in hdus if isinstance(h, fits.BinTableHDU)
                  and {'mjd', 'included'} <= {name.lower() for name in h.columns.names}]
        if len(tables) != 1 or len(tables[0].data) > 100000:
            raise ValueError('unWISE contributor table is not bounded or unique')
        table = tables[0].data
        names = {n.lower(): n for n in table.names}
        if not {'mjd', 'included'} <= names.keys():
            raise ValueError('unWISE contributor times or inclusion flags are absent')
        included = np.asarray(table[names['included']])
        if included.dtype.kind not in 'biu' or np.any(included < 0) or np.any(included > 255):
            raise ValueError('unWISE contributor flags are invalid')
        # The author's coadder uses included > 0 when deriving MJDMIN/MAX.
        # New releases encode quadrant participation in this byte; it is not a
        # boolean column and must never become a SPHEREx pixel-quality mask.
        selected = included > 0
        times = np.asarray(table[names['mjd']], dtype=float)[selected]
        if not len(times) or not np.isfinite(times).all():
            raise ValueError('unWISE has no valid included exposure times')
        # MJDMIN/MAX are author visit bounds; source rows are retained as an
        # additional consistency check rather than converted into extra epochs.
        if times.min() < start - 1e-5 or times.max() > end + 1e-5:
            raise ValueError('unWISE contributors disagree with visit interval')
        if 'band' in names and not np.all(np.asarray(table[names['band']])[selected] == 2):
            raise ValueError('unWISE contributors have incompatible bands')
        return dict(rows=len(table), included=int(selected.sum()),
                    first_included_mjd=float(times.min()), last_included_mjd=float(times.max()),
                    additional_hdus=len(hdus)-2, selection='author included > 0')


def read_unwise_frame(path, spec, auxiliary_paths):
    """Decode checksum-pinned related files supplied by the managed worker."""
    if set(auxiliary_paths) != ROLES or set(spec.get('auxiliaries', {})) != ROLES:
        raise ValueError('unWISE requires inverse variance, coverage and contributors')
    meta = spec.get('metadata', {})
    native = meta.get('native', {})
    if (meta.get('provider') != 'unwise-neo11' or native.get('release') != 'neo11'
            or not re.fullmatch(r'\d{4}[pm]\d{3}', str(native.get('coadd_id', '')))
            or str(native.get('band')) not in {'2', 'W2'}):
        raise ValueError('unWISE managed source identity is not qualified')
    epoch = int(native['epoch'])
    if not 0 <= epoch <= 426 or spec.get('image_hdu') not in (None, 0) or spec.get('plane_indices', []):
        raise ValueError('unWISE image selection is not qualified')
    image, header = _image(path)
    wcs, start, end, band_source = _qualify_header(header, epoch)
    auxiliary_arrays = {}
    for role in ('inverse_variance', 'coverage'):
        values, h = _image(auxiliary_paths[role])
        awcs, lo, hi, _ = _qualify_header(h, epoch)
        if (values.shape != image.shape or abs(lo-start) > 1e-8 or abs(hi-end) > 1e-8
                or not wcs.wcs.compare(awcs.wcs, cmp=0, tolerance=1e-12)):
            raise ValueError('unWISE auxiliary epoch, shape or WCS differs from science')
        auxiliary_arrays[role] = values
    ivar, coverage = (auxiliary_arrays[k] for k in ('inverse_variance', 'coverage'))
    valid = np.isfinite(image) & np.isfinite(ivar) & (ivar > 0) & np.isfinite(coverage) & (coverage >= 1)
    if np.any(np.isfinite(coverage) & ((coverage < 0) | (coverage != np.floor(coverage)))):
        raise ValueError('unWISE coverage is not a nonnegative frame count')
    if not valid.any():
        raise ValueError('unWISE has no usable science and uncertainty coverage')
    contributors = _contributors(auxiliary_paths['contributors'], start, end)
    image = np.where(valid, image * TO_UJY, np.nan)
    variance = np.divide(TO_UJY**2, ivar, out=np.full_like(image, np.nan), where=valid)
    valid &= np.isfinite(variance) & (variance > 0)
    image[~valid] = np.nan
    variance[~valid] = np.nan
    aux = {k: {field: spec['auxiliaries'][k][field] for field in ('id', 'sha256', 'bytes')} for k in ROLES}
    midpoint = Time(start + (end-start)/2, format='mjd', scale='utc')
    midpoint.precision = 9
    limitations = ['Native W2 visit coadds, not individual exposures; midpoint approximates the visit interval.',
                   'Nominal Vega-equivalent flux density; no source-spectrum color correction.',
                   'No supplied per-pixel artifact, outlier or bloom mask; -m denotes upstream outlier rejection.',
                   'Native scan-dependent W2 PSF is not homogenized; WCS registration does not prove common stellar centroids.']
    qualification = dict(status='qualified_native_product', release='neo11', band='W2',
        tile=native['coadd_id'], epoch=epoch, native_pixel_scale_arcsec=NATIVE_SCALE,
        band_identity_source=band_source,
        flux_conversion=dict(input_unit='Vega nanomaggy', magzp=MAGZP, zero_flux_jy=ZERO_FLUX_JY, to_uJy=TO_UJY),
        time=dict(method='midpoint of MJDMIN/MJDMAX visit interval', scale='utc', start_mjd=start, end_mjd=end),
        auxiliary_sources=aux, contributor_summary=contributors, artifact_mask_available=False,
        psf=dict(nominal_fwhm_arcsec=6.4, homogenized=False), limitations=limitations)
    metadata = dict(unit='uJy', midpoint_utc=midpoint.isot, band='W2', mission='WISE/NEOWISE', instrument='WISE',
        calibration='MAGZP=22.5 Vega; nominal W2 zero flux 171.787 Jy; no color correction',
        mask_semantics='finite science, positive inverse variance and positive frame coverage; artifact flags unavailable',
        selected_hdu=0, plane_indices=[], source_wcs=wcs.to_header().tostring(sep='\n'),
        source_time={k: header[k] for k in ('MJDMIN', 'MJDMAX', 'TIMESYS') if k in header},
        outlier_known=False, bloom_known=False, auxiliary_assets=aux,
        uncertainty_unit_semantics='1/native inverse variance, multiplied by squared flux conversion',
        source_uncertainty_unit='inverse squared native coadd flux', historical_motion_qualification=qualification)
    unknown = np.zeros(image.shape, dtype=bool)
    return Frame(image, valid, variance, valid.copy(), unknown, unknown.copy(), wcs, metadata)
