#!/usr/bin/env python3
"""Bounded, offline FITS worker. One JSON request on stdin; one result on stdout.

Only IMAGE rendering and the team's ZODI subtraction are enabled. Spectrum stays
unavailable until per-pixel calibration and aperture photometry are validated.
No service, archive query, alignment, download, or synthetic image path is used.
"""
from contextlib import redirect_stdout
import hashlib
import json
import math
from pathlib import Path
import sys

import astropy.units as u
from astropy.io import fits
from astropy.visualization import ZScaleInterval
import numpy as np
from PIL import Image

MAX_REQUEST_BYTES = 16_384
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_PIXELS = 4096 * 4096
BAD_BITS = 1 | 2 | 4 | 64 | 512 | 1024 | 2048


class WorkerError(Exception):
    def __init__(self, code, message, reason=None):
        super().__init__(message)
        self.code = code
        self.reason = reason


def _path(value, label):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise WorkerError('invalid_request', f'{label} must be an absolute path')
    p = Path(value)
    if not p.is_absolute():
        raise WorkerError('invalid_request', f'{label} must be an absolute path')
    return p.resolve()


def _number(request, key, default=None):
    value = request.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise WorkerError('invalid_request', f'{key} must be a finite number')
    return float(value)


def _request(request):
    if not isinstance(request, dict):
        raise WorkerError('invalid_request', 'request must be a JSON object')
    operation = request.get('operation')
    if operation not in ('preview', 'zodi', 'spectrum'):
        raise WorkerError('invalid_request', 'operation must be preview, zodi, or spectrum')
    source = _path(request.get('image_path'), 'image_path')
    output = None
    if operation in ('preview', 'zodi'):
        output = _path(request.get('output_path'), 'output_path')
        if output == source or output.exists() or not output.parent.is_dir():
            raise WorkerError('invalid_output', 'output must be a new file in an existing directory')
    if operation == 'spectrum':
        ra = _number(request, 'ra_deg')
        dec = _number(request, 'dec_deg')
        radius = _number(request, 'radius_pix', 2.0)
        if not (0 <= ra < 360 and -90 <= dec <= 90 and 0 < radius <= 64):
            raise WorkerError('invalid_request', 'coordinates or radius are out of range')
    if not source.is_file() or source.stat().st_size > MAX_FILE_BYTES:
        raise WorkerError('invalid_input', 'input must be an existing FITS file no larger than 256 MiB')
    return operation, source, output


def _unit(header, expected):
    try:
        scale = u.Unit(header.get('BUNIT', '')).to(expected)
    except (ValueError, TypeError, u.UnitConversionError) as exc:
        raise WorkerError('unsupported_unit', f'expected BUNIT {expected}') from exc
    # Team cleaning subtracts numbers without unit conversion. Reject different scales.
    if not math.isclose(scale, 1., rel_tol=1e-12):
        raise WorkerError('unsupported_unit', f'expected BUNIT {expected} at its original scale')


def _processed(hdul):
    for hdu in (hdul[0], hdul['IMAGE']):
        header = hdu.header
        if header.get('ZODISUB', False) or header.get('SPXPROC') == 'zodi-v1':
            return True
        for line in str(header.get('HISTORY', '')).lower().splitlines():
            if 'zodi subtracted' in line or 'subtract zodi' in line:
                return True
    return False


def _validate(hdul, operation):
    names = [h.name for h in hdul]
    required = ['IMAGE', 'FLAGS']
    if operation != 'preview':
        required += ['ZODI', 'VARIANCE']
    for name in required:
        if names.count(name) != 1:
            raise WorkerError('missing_hdu', f'exactly one {name} HDU is required')
    # Read dimensions before accessing arrays to bound allocation.
    header = hdul['IMAGE'].header
    shape = (header.get('NAXIS2', 0), header.get('NAXIS1', 0))
    if header.get('NAXIS') != 2 or not all(0 < n <= 4096 for n in shape) or math.prod(shape) > MAX_PIXELS:
        raise WorkerError('invalid_shape', 'IMAGE must be a nonempty 2D array of at most 4096 by 4096')
    for name in required:
        h = hdul[name].header
        if h.get('NAXIS') != 2 or (h.get('NAXIS2'), h.get('NAXIS1')) != shape:
            raise WorkerError('invalid_shape', f'{name} dimensions must match IMAGE')
    _unit(header, u.MJy / u.sr)
    flags = hdul['FLAGS'].data
    if not np.issubdtype(flags.dtype, np.integer) or np.any(flags < 0):
        raise WorkerError('invalid_flags', 'FLAGS must contain nonnegative integers')
    image = np.asarray(hdul['IMAGE'].data, dtype=float)
    bad = (flags & BAD_BITS) != 0
    invalid = bad | ~np.isfinite(image)
    if np.all(invalid):
        raise WorkerError('no_valid_pixels', 'IMAGE has no finite unflagged pixels')
    if operation != 'preview':
        if _processed(hdul):
            raise WorkerError('already_processed', 'input IMAGE has already had ZODI subtracted')
        _unit(hdul['ZODI'].header, u.MJy / u.sr)
        _unit(hdul['VARIANCE'].header, (u.MJy / u.sr)**2)
        zodi = hdul['ZODI'].data
        if np.any(~np.isfinite(zodi)[~invalid]):
            raise WorkerError('nonfinite_data', 'ZODI is nonfinite at valid IMAGE pixels')
        if operation == 'spectrum':
            variance = hdul['VARIANCE'].data
            if np.any(~np.isfinite(variance[~invalid])) or np.any(variance[~invalid] < 0):
                raise WorkerError('invalid_variance', 'VARIANCE must be finite and nonnegative at valid IMAGE pixels')
    return image, invalid


def _metadata(data, invalid, processed):
    finite = data[~invalid]
    return {
        'width': int(data.shape[1]), 'height': int(data.shape[0]),
        'masked_pixels': int(np.count_nonzero(invalid)),
        'data_min': float(np.min(finite)), 'data_max': float(np.max(finite)),
        'data_unit': 'MJy/sr',
        'subtraction': 'zodi_subtracted' if processed else 'raw_calibrated',
    }


def _preview(image, invalid, output):
    lo, hi = ZScaleInterval().get_limits(image[~invalid])
    norm = np.zeros(image.shape, dtype=np.uint8)
    if hi > lo:
        norm[~invalid] = (np.clip((image[~invalid] - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
    alpha = np.where(invalid, 0, 255).astype(np.uint8)
    png = Image.fromarray(np.stack((norm, alpha), axis=-1))
    with output.open('xb') as stream:
        png.save(stream, format='PNG')
    return {'stretch': 'zscale', 'stretch_min': float(lo), 'stretch_max': float(hi)}


def _zodi(source, hdul, output, invalid):
    # Import only the reviewed pure function; do not import pipeline/service.py.
    worker_path = Path(__file__).resolve()
    for parent in (worker_path.parents[1], worker_path.parents[2]):
        pipeline = parent / 'pipeline'
        if (pipeline / 'spherex' / 'cleaning.py').is_file():
            sys.path.insert(0, str(pipeline))
            break
    from spherex.cleaning import load_clean_cutout
    with redirect_stdout(sys.stderr):
        _, _, clean_m, _ = load_clean_cutout(source)
    clean_m[invalid] = np.nan
    if not np.any(np.isfinite(clean_m)):
        raise WorkerError('no_valid_pixels', 'subtracted IMAGE has no valid pixels')
    if np.any(~np.isfinite(clean_m[~invalid])):
        raise WorkerError('nonfinite_data', 'subtraction produced nonfinite values')
    result = fits.HDUList([h.copy() for h in hdul])
    result['IMAGE'].data = clean_m
    header = result['IMAGE'].header
    header['ZODISUB'] = (True, 'IMAGE minus ZODI; bad pixels masked')
    header['SPXPROC'] = ('zodi-v1', 'Offline SPHEREx worker processing version')
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    header['HIERARCH SPX SOURCE SHA256'] = digest
    header.add_history('SPHEREx worker: zodi subtracted once using spherex.cleaning.load_clean_cutout')
    header.add_history(f'Bad FLAGS bits masked: {BAD_BITS}; original HDUs and spatial WCS retained')
    # IMAGE changes from float32 to float64. Ensure the serialized result fits the bound.
    estimated_bytes = sum(h.size for h in result) + 2880 * sum(len(h.header)//36 + 2 for h in result)
    if estimated_bytes > MAX_FILE_BYTES:
        raise WorkerError('invalid_output', 'processed FITS would exceed 256 MiB')
    result.writeto(output, overwrite=False, checksum=True)
    return clean_m


def execute(request):
    if isinstance(request, dict) and request.get('operation') == 'capabilities':
        return {'status': 'ok', 'operations': ['preview', 'zodi'],
            'spectrum': {'status': 'not_ready', 'code': 'missing_pixel_spectral_calibration'}}
    operation, source, output = _request(request)
    try:
        # memmap=False also supports standard FITS unsigned integer scaling in FLAGS.
        with fits.open(source, memmap=False, lazy_load_hdus=True) as hdul:
            image, invalid = _validate(hdul, operation)
            if operation == 'spectrum':
                if 'CWAVE' not in hdul or 'CBAND' not in hdul:
                    raise WorkerError('not_ready',
                        'Science spectrum requires matched per-pixel CWAVE and CBAND calibration; WCS-WAVE is visualization-only',
                        'missing_pixel_spectral_calibration')
                raise WorkerError('not_ready',
                    'Per-pixel calibration association and aperture photometry are not yet scientifically validated',
                    'unverified_spectral_photometry')
            processed = _processed(hdul)
            extra = {}
            if operation == 'zodi':
                image = _zodi(source, hdul, output, invalid)
                processed = True
            else:
                extra = _preview(image, invalid, output)
            return {'status': 'ok', 'operation': operation, 'output_path': str(output),
                **_metadata(image, invalid, processed), **extra}
    except WorkerError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise WorkerError('invalid_fits', f'FITS processing failed: {exc}') from exc


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise WorkerError('invalid_request', 'request exceeds 16384 bytes')
        try:
            request = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise WorkerError('invalid_request', 'stdin must contain one JSON object') from exc
        # Astropy and team helpers can log to stdout; reserve it for the protocol.
        with redirect_stdout(sys.stderr):
            result = execute(request)
        exit_code = 0
    except WorkerError as exc:
        error = {'code': exc.code, 'message': str(exc)}
        if exc.reason:
            error['reason'] = exc.reason
        result = {'status': 'error', 'error': error}
        exit_code = 1
    except Exception as exc:
        result = {'status': 'error', 'error': {'code': 'processing_failed', 'message': str(exc)}}
        exit_code = 1
    sys.stdout.write(json.dumps(result, allow_nan=False, separators=(',', ':')) + '\n')
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
