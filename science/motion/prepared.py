"""Qualified unWISE preparation adapter for Ivan's existing heuristic review."""

import math
import re
from uuid import UUID

import numpy as np
from astropy.time import Time

from pipeline.unification.ml import load_bundle
from .profiles import proper_motion_profile
from .review import build_review, sky_wcs_from_header

PROFILE = 'stellar_proper_motion'
HASH = re.compile(r'[0-9a-fA-F]{64}')


def _close(value, expected):
    return isinstance(value, (int, float)) and math.isfinite(value) and math.isclose(value, expected, rel_tol=1e-8)


def _validate_qualification(frame):
    if (frame.get('profile') != 'unwise' or frame.get('unit') != 'uJy'
            or frame.get('mission') != 'WISE/NEOWISE' or frame.get('instrument') != 'WISE'
            or frame.get('band') != 'W2' or not isinstance(frame.get('provenance'), dict)
            or frame['provenance'].get('provider') != 'unwise-neo11'):
        raise ValueError('prepared historical motion requires qualified unwise-neo11 W2 physical frames')
    if frame.get('outlier_known') is not False or frame.get('bloom_known') is not False:
        raise ValueError('unWISE artifact evidence must remain explicitly unavailable')
    if not isinstance(frame.get('source_sha256'), str) or not HASH.fullmatch(frame['source_sha256']):
        raise ValueError('prepared source checksum is required')
    q = frame.get('historical_motion_qualification')
    if (not isinstance(q, dict) or q.get('status') != 'qualified_native_product'
            or q.get('release') != 'neo11' or q.get('band') != 'W2'
            or not isinstance(q.get('tile'), str) or not re.fullmatch(r'\d{4}[pm]\d{3}', q['tile'])
            or type(q.get('epoch')) is not int or not 0 <= q['epoch'] <= 999
            or not _close(q.get('native_pixel_scale_arcsec'), 2.75)):
        raise ValueError('missing or unsupported native unWISE qualification')
    conversion = q.get('flux_conversion', {})
    if (not isinstance(conversion, dict) or conversion.get('input_unit') != 'Vega nanomaggy'
            or not _close(conversion.get('magzp'), 22.5)
            or not _close(conversion.get('zero_flux_jy'), 171.787)
            or not _close(conversion.get('to_uJy'), 0.171787)):
        raise ValueError('unWISE W2 requires the documented Vega flux conversion')
    interval = q.get('time', {})
    if (not isinstance(interval, dict) or interval.get('scale') != 'utc'
            or interval.get('method') != 'midpoint of MJDMIN/MJDMAX visit interval'
            or not all(isinstance(interval.get(key), (int, float)) and math.isfinite(interval[key])
                       for key in ('start_mjd', 'end_mjd'))
            or interval['start_mjd'] > interval['end_mjd']):
        raise ValueError('actual UTC visit interval is required')
    midpoint = (interval['start_mjd'] + interval['end_mjd']) / 2
    if abs(float(Time(frame['midpoint_utc'], scale='utc').mjd) - midpoint) > 1e-7:
        raise ValueError('visit interval and observation midpoint disagree')
    auxiliaries = q.get('auxiliary_sources', {})
    if not isinstance(auxiliaries, dict):
        raise ValueError('checksummed auxiliary source metadata is required')
    for kind in ('inverse_variance', 'coverage', 'contributors'):
        asset = auxiliaries.get(kind, {})
        if (not isinstance(asset, dict) or not isinstance(asset.get('id'), str) or not asset['id']
                or not isinstance(asset.get('sha256'), str) or not HASH.fullmatch(asset['sha256'])
                or type(asset.get('bytes')) is not int or asset['bytes'] <= 0):
            raise ValueError('checksummed inverse variance, coverage and contributor provenance is required')
    psf = q.get('psf', {})
    if (not isinstance(psf, dict) or q.get('artifact_mask_available') is not False
            or psf.get('homogenized') is not False
            or not _close(psf.get('nominal_fwhm_arcsec'), 6.4)):
        raise ValueError('unWISE mask and nominal PSF limitations must be declared')
    return q


def prepare_motion_payload(bundle, unification_id):
    """Qualify physical metadata and remove each frame's measured background only."""
    if UUID(str(bundle.metadata.get('job_id'))) != UUID(str(unification_id)):
        raise ValueError('prepared bundle does not belong to the requested unification')
    images, times = bundle.motion_inputs()
    grid = bundle.metadata['grid']
    if grid.get('kind') != 'sky' or not _close(grid.get('pixel_scale_arcsec'), 2.75):
        raise ValueError('unWISE historical motion requires a sky grid at 2.75 arcsec/pixel')
    sky_header = bundle.metadata.get('target_wcs')
    sky_wcs_from_header(sky_header)
    if (not _close(times[0], 0.) or bundle.metadata.get('time_unit') != 'hours from first known real exposure midpoint'):
        raise ValueError('prepared motion times must be real elapsed hours from the first midpoint')
    frames = bundle.metadata['frames']
    qualifications = [_validate_qualification(frame) for frame in frames]
    physical = {(q['release'], q['tile'], q['band']) for q in qualifications}
    if len(physical) != 1 or len({q['epoch'] for q in qualifications}) != len(qualifications):
        raise ValueError('motion requires distinct epochs of the same unWISE release/tile/band')
    if (not np.array_equal(bundle.variance_valid_mask, bundle.valid_mask)
            or not np.all(np.isfinite(bundle.variance[bundle.valid_mask]))
            or np.any(bundle.variance[bundle.valid_mask] <= 0)):
        raise ValueError('every valid historical pixel requires finite positive propagated variance')
    resampling = bundle.metadata.get('resampling', {})
    if (resampling.get('covariance') != 'not represented' or resampling.get('flux_conserving') is not False
            or resampling.get('variance') != 'sum(squared normalized weights * independent input variance)'):
        raise ValueError('prepared variance and resampling covariance semantics are required')
    center = np.array([grid.get('ra_degrees'), grid.get('dec_degrees')], dtype=float)
    if not np.isfinite(center).all() or not 0 <= center[0] < 360 or not -90 < center[1] < 90:
        raise ValueError('a finite physical sky grid center is required')
    offsets = np.array([np.median(image[valid].astype(float))
                        for image, valid in zip(images, bundle.valid_mask)])
    payload = dict(images=images.astype(float) - offsets[:, None, None], times=times,
                   dates=bundle.dates_utc, observation_ids=bundle.observation_ids,
                   outlier=None, bloom=None, retain_outliers=False,
                   center_deg=center, pixel_scale_arcsec=grid['pixel_scale_arcsec'],
                   sky_wcs_header=sky_header)
    provenance = dict(provider='unwise-neo11', release='neo11', band='W2', unit='uJy',
                      flux_scale='nominal Vega-equivalent; no source SED color correction',
                      qualification='native product headers, calibration and preparation contract; not motion confirmation',
                      frames=frames, grid=grid, target_wcs=sky_header, time_unit='hours', psf_homogenized=False,
                      artifact_mask_available=False, resampling=resampling,
                      warnings=bundle.metadata.get('warnings', []),
                      background_subtraction=dict(method='per-frame median of valid physical pixels',
                                                  offsets_uJy=offsets.tolist()),
                      limitations=['Visit coadds are not individual exposures; real mission gaps remain.',
                                   'Fluxes are nominal Vega-equivalent uJy; no source SED color correction is applied.',
                                   'Nominal W2 PSF is 6.4 arcsec; no per-epoch PSF homogenization or astrometric refinement.',
                                   'Artifact/outlier/bloom evidence is unavailable; unknown masks are not SPHEREx flags.',
                                   'Bilinear sampling does not conserve integrated flux; pixel covariance is not represented.',
                                   'Ivan uses residual-derived noise; supplied variance qualifies preparation but is not detector weighting.'])
    return payload, provenance


def analyze_prepared(path, unification_id, *, track_limit=20):
    """Decode a managed artifact and call the existing detector without truth or training."""
    if type(track_limit) is not int or not 1 <= track_limit <= 100:
        raise ValueError('track_limit must be between 1 and 100')
    bundle = load_bundle(path)
    payload, provenance = prepare_motion_payload(bundle, unification_id)
    profile = proper_motion_profile(payload['pixel_scale_arcsec'])
    result = build_review(payload, str(unification_id), target=None, detector=None,
                          source='unWISE neo11 W2 time-resolved visit coadds',
                          min_speed=profile['min_speed'], max_speed=profile['max_speed'],
                          search_profile=profile, forest=None, track_limit=track_limit)
    result.update(unification_id=str(unification_id), profile=PROFILE, historical_preparation=provenance)
    return result
