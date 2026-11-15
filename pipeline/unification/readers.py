"""Decode native scientific planes without inferring absent calibration."""
from dataclasses import dataclass
import gzip
import io
import re
import warnings

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from PIL import Image

MAX_INPUT = 256 * 1024**2
MAX_SIDE = 4096
AUXILIARY = {'DQ', 'MASK', 'FLAGS', 'VARIANCE', 'VAR', 'ERR', 'ERROR', 'UNCERTAINTY',
             'IVAR', 'WEIGHT', 'ZODI', 'OUTLIER', 'BLOOM', 'FOOTPRINT', 'COVERAGE'}


@dataclass
class Frame:
    image: np.ndarray
    valid: np.ndarray
    variance: np.ndarray
    variance_valid: np.ndarray
    outlier: np.ndarray
    bloom: np.ndarray
    wcs: object
    metadata: dict


def _bounded_bytes(path):
    if path.stat().st_size > MAX_INPUT:
        raise ValueError('encoded input exceeds limit')
    with path.open('rb') as f:
        signature = f.read(2)
    opener = gzip.open if signature == b'\x1f\x8b' else open
    with opener(path, 'rb') as f:
        data = f.read(MAX_INPUT + 1)
    if len(data) > MAX_INPUT:
        raise ValueError('expanded input exceeds limit')
    return data


def _check_shape(shape, itemsize=8):
    if len(shape) < 2 or any(n <= 0 for n in shape):
        raise ValueError('not an image plane')
    if max(shape[-2:]) > MAX_SIDE or int(np.prod(shape, dtype=object))*max(8, itemsize) > MAX_INPUT:
        raise ValueError('decoded image exceeds limit')


def _plane(hdu, indexes):
    shape = hdu.shape
    _check_shape(shape)
    if len(indexes) != len(shape)-2:
        raise ValueError('explicit cube plane_indices required')
    if any(type(i) is not int or not 0 <= i < n for i, n in zip(indexes, shape[:-2])):
        raise ValueError('cube plane index out of bounds')
    result = np.asarray(hdu.data[tuple(indexes)] if indexes else hdu.data)
    if result.dtype.kind not in 'iuf':
        raise ValueError('image must be numeric')
    return result.astype(np.float64)


def _midpoint(header):
    scale = str(header.get('TIMESYS', 'UTC')).lower()
    def utc(t):
        t = t.utc
        t.precision = 9
        return t.isot if np.isfinite(t.jd) else None
    try:
        if scale not in Time.SCALES:
            return None
        explicit = [Time(header[key], format=fmt, scale=scale)
                    for key, fmt in [('MJD-AVG', 'mjd'), ('DATE-AVG', None)] if key in header]
        if explicit:
            # DATE/MJD duplicate declarations must agree within header timestamp precision.
            if any(abs((t-explicit[0]).to_value('sec')) > 1 for t in explicit):
                return None
            return utc(explicit[0])
        if 'DATE-BEG' in header and 'DATE-END' in header:
            start = Time(header['DATE-BEG'], scale=scale)
            end = Time(header['DATE-END'], scale=scale)
            if end < start:
                return None
            return utc(start + (end-start)/2)
        exposure = float(header['EXPTIME'])
        if not np.isfinite(exposure) or exposure < 0:
            return None
        starts = []
        if 'MJD-OBS' in header:
            starts.append(Time(float(header['MJD-OBS']), format='mjd', scale=scale))
        if 'DATE-OBS' in header:
            stamp = str(header['DATE-OBS'])
            if 'T' not in stamp and 'TIME-OBS' in header:
                stamp += 'T' + str(header['TIME-OBS'])
            if 'T' in stamp or ' ' in stamp:
                starts.append(Time(stamp, scale=scale))
        if not starts or any(abs((t-starts[0]).to_value('sec')) > 1 for t in starts):
            return None
        from astropy.time import TimeDelta
        return utc(starts[0] + TimeDelta(exposure/2, format='sec'))
    except (ValueError, TypeError, KeyError, OverflowError):
        return None


def _native_identity(header):
    """Read physical SPHEREx identity with the frozen consumer's detector syntax."""
    observations = []
    for key in ('OBSID', 'OBS_ID'):
        value = header.get(key)
        if isinstance(value, str):
            value = value.strip()
            if 1 <= len(value) <= 256:
                observations.append(value)
    if len(set(observations)) > 1:
        raise ValueError('conflicting native observation identity headers')
    detectors = []
    for key in ('DETECTOR', 'DET_ID', 'DETID'):
        value = header.get(key)
        if value is None or value == '':
            continue
        match = re.fullmatch(r'(?:SPHEREx-)?D?([1-6])', str(value).strip())
        if not match:
            raise ValueError('invalid native detector header')
        detectors.append(int(match.group(1)))
    if len(set(detectors)) > 1:
        raise ValueError('conflicting native detector headers')
    return (observations[0] if observations else None, detectors[0] if detectors else None)


def read_frame(path, spec, mask_policy='science'):
    data = _bounded_bytes(path)
    if spec['profile'] == 'raster':
        with Image.open(io.BytesIO(data)) as im:
            _check_shape((im.height, im.width))
            if getattr(im, 'n_frames', 1) != 1:
                raise ValueError('multi-frame raster requires a scientific plane')
            if im.mode not in ('1', 'L', 'I', 'I;16', 'F'):
                raise ValueError('raster must be a single-channel image; RGB calibration is unknown')
            image = np.asarray(im).astype(float)
        valid = np.isfinite(image)
        meta = dict(unit=None, midpoint_utc=None, band=None, instrument=None, mission=None,
                    calibration='unknown', mask_semantics='finite pixels only', selected_hdu=None,
                    plane_indices=[], source_wcs=None, raster_mode=im.mode, outlier_known=False, bloom_known=False)
        return Frame(image, valid, np.full(image.shape, np.nan), np.zeros(image.shape, bool),
                     np.zeros(image.shape, bool), np.zeros(image.shape, bool), None, meta)
    try:
        with fits.open(io.BytesIO(data), memmap=False, lazy_load_hdus=True) as hdus:
            for hdu_index, _ in enumerate(hdus):
                if hdu_index > 1024:
                    raise ValueError('FITS HDU count exceeds limit')
            decoded_bytes = sum(int(np.prod(h.shape, dtype=object))*8 for h in hdus
                                if isinstance(h, (fits.PrimaryHDU, fits.ImageHDU, fits.CompImageHDU)) and h.shape)
            if decoded_bytes > MAX_INPUT:
                raise ValueError('aggregate decoded FITS images exceed limit')
            selection = spec.get('image_hdu')
            candidates = [i for i, h in enumerate(hdus) if isinstance(h, (fits.PrimaryHDU, fits.ImageHDU, fits.CompImageHDU))
                          and len(h.shape or ()) >= 2 and h.name.upper() not in AUXILIARY]
            if selection is None:
                if len(candidates) != 1:
                    raise ValueError('ambiguous or absent scientific image HDU; select image_hdu')
                index = candidates[0]
            elif type(selection) is int:
                if selection < 0 or selection >= len(hdus):
                    raise ValueError('image_hdu out of bounds')
                index = selection
            else:
                matches = [i for i, h in enumerate(hdus) if h.name == selection.upper()]
                if len(matches) != 1:
                    raise ValueError('ambiguous or absent named image_hdu')
                index = matches[0]
            science = hdus[index]
            if not isinstance(science, (fits.PrimaryHDU, fits.ImageHDU, fits.CompImageHDU)):
                raise ValueError('selected HDU is not an image')
            image = _plane(science, spec.get('plane_indices', []))
            header = hdus[0].header.copy()
            header.extend(science.header, update=True)
            valid = np.isfinite(image)
            variance = np.full_like(image, np.nan)
            outlier = np.zeros(image.shape, bool)
            bloom = np.zeros(image.shape, bool)
            extver = science.header.get('EXTVER', 1)
            def auxiliary(names):
                matches = [h for h in hdus if h.name.upper() in names and h.header.get('EXTVER', 1) == extver]
                if len(matches) > 1:
                    raise ValueError('ambiguous auxiliary image HDUs')
                if not matches:
                    return None, None, None
                h = matches[0]
                values = _plane(h, spec.get('plane_indices', []) if len(h.shape) > 2 else [])
                if values.shape != image.shape:
                    raise ValueError('auxiliary image shape mismatch')
                return values, h.name.upper(), h.header.get('BUNIT')
            uncertainty, kind, uncertainty_unit = auxiliary({'VARIANCE', 'VAR', 'ERR', 'ERROR', 'UNCERTAINTY', 'IVAR'})
            uncertainty_semantics = 'unknown; no uncertainty plane'
            if uncertainty is not None:
                if uncertainty_unit is not None:
                    try:
                        from astropy import units as u
                        science_unit = u.Unit(header['BUNIT'])
                        exponent = -2 if kind == 'IVAR' else (1 if kind in ('ERR', 'ERROR', 'UNCERTAINTY') else 2)
                        factor = u.Unit(uncertainty_unit).to(science_unit**exponent)
                        uncertainty = uncertainty*factor
                    except (ValueError, TypeError, KeyError) as e:
                        raise ValueError('uncertainty unit is incompatible with science unit') from e
                    uncertainty_semantics = 'declared auxiliary unit converted to science unit power'
                else:
                    uncertainty_semantics = 'assumed native science unit power; auxiliary BUNIT absent'
                if kind in ('ERR', 'ERROR', 'UNCERTAINTY'):
                    variance = np.where(uncertainty >= 0, uncertainty**2, np.nan)
                elif kind == 'IVAR':
                    variance = np.divide(1, uncertainty, out=np.full_like(uncertainty, np.nan), where=uncertainty > 0)
                else:
                    variance = uncertainty
            if uncertainty is not None:
                valid &= np.isfinite(variance) & (variance > 0)
            dq, _, _ = auxiliary({'DQ', 'MASK', 'FLAGS'})
            if dq is not None:
                if not np.isfinite(dq).all() or np.any(dq < 0) or np.any(dq != np.floor(dq)):
                    raise ValueError('mask must contain nonnegative integer flags')
                if spec['profile'] == 'spherex':
                    if np.any(dq > 2**32-1):
                        raise ValueError('SPHEREx FLAGS exceed uint32 semantics')
                    flags = dq.astype(np.uint64)
                    outlier = (flags & (1 << 19)) != 0
                    bloom = (flags & (1 << 26)) != 0
                    allowed = (1 << 21) | ((1 << 19) if mask_policy == 'motion' else 0)
                    valid &= (flags & np.uint64(~allowed & ((1 << 64)-1))) == 0
                    mask_semantics = 'SPHEREx: SOURCE allowed' + ('; OUTLIER retained' if mask_policy == 'motion' else '') + '; remaining flags rejected'
                else:
                    valid &= dq == 0
                    mask_semantics = 'generic DQ/MASK/FLAGS: nonzero rejected; bits uninterpreted'
            else:
                mask_semantics = 'unknown; finite pixels only'
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    # WCSAXES may be 2 on a selected cube. Only celestial axes define registration.
                    w = WCS(header, relax=True).celestial
                if not w.has_celestial or w.pixel_n_dim != 2:
                    w = None
            except (ValueError, TypeError):
                w = None
            unit = str(header['BUNIT']).strip() if header.get('BUNIT') else None
            meta = dict(unit=unit, midpoint_utc=_midpoint(header),
                        band=str(header.get('FILTER', header.get('BAND'))).strip() if header.get('FILTER', header.get('BAND')) is not None else None,
                        instrument=str(header['INSTRUME']) if header.get('INSTRUME') else None,
                        mission=str(header['TELESCOP']) if header.get('TELESCOP') else None,
                        calibration='unit declared by FITS' if unit else 'unknown',
                        mask_semantics=mask_semantics, selected_hdu=index, plane_indices=spec.get('plane_indices', []),
                        source_wcs=w.to_header(relax=True).tostring(sep='\n') if w is not None else None,
                        uncertainty_unit_semantics=uncertainty_semantics, source_uncertainty_unit=uncertainty_unit,
                        source_time={k: header[k] for k in ('TIMESYS', 'MJD-AVG', 'DATE-AVG', 'MJD-OBS', 'DATE-OBS', 'TIME-OBS', 'EXPTIME', 'DATE-BEG', 'DATE-END') if k in header},
                        outlier_known=spec['profile'] == 'spherex' and dq is not None,
                        bloom_known=spec['profile'] == 'spherex' and dq is not None,
                        wavelength_min=header.get('WAVEMIN'), wavelength_max=header.get('WAVEMAX'),
                        wavelength_unit=header.get('WAVEUNIT'))
            native_observation, native_detector = _native_identity(header) if spec['profile'] == 'spherex' else (None, None)
            meta.update(native_observation_id=native_observation, native_detector=native_detector)
            return Frame(image, valid, variance, np.isfinite(variance) & (variance >= 0), outlier, bloom, w, meta)
    except (OSError, IndexError, KeyError, TypeError) as e:
        raise ValueError('cannot decode selected FITS image') from e
