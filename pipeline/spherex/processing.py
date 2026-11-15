#!/usr/bin/env python3
"""Bounded, offline FITS worker. One JSON request on stdin; one result on stdout.

IMAGE rendering, the team's ZODI subtraction and diagnostic aperture measurements
are enabled. Scientifically calibrated spectra remain explicitly unavailable.
No service, archive query, alignment, download, or synthetic image path is used.
"""
from contextlib import redirect_stdout
import hashlib
import json
import math
import os
import resource
from pathlib import Path
import sys

import astropy.units as u
from astropy.io import fits
from astropy.visualization import ZScaleInterval
import numpy as np
from PIL import Image

MAX_REQUEST_BYTES = 65_536
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_PIXELS = 4096 * 4096
SOURCE_BIT = 1 << 21


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
    resolved = p.resolve()
    root = Path(os.environ.get('PROCESSING_DATA_ROOT', '/app/data')).resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise WorkerError('invalid_path', f'{label} must be within PROCESSING_DATA_ROOT')
    return resolved


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
        if output == source or output.exists() or Path(request['output_path']).is_symlink() or not output.parent.is_dir():
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
    bad = (flags & ~SOURCE_BIT) != 0
    invalid = bad | ~np.isfinite(image)
    if 'VARIANCE' in hdul:
        variance=hdul['VARIANCE'].data
        if variance.shape != image.shape:
            raise WorkerError('invalid_shape','VARIANCE dimensions must match IMAGE')
        if operation == 'spectrum' and (np.any(~np.isfinite(variance[~invalid])) or np.any(variance[~invalid]<0)):
            raise WorkerError('invalid_variance','VARIANCE must be finite and nonnegative at valid IMAGE pixels')
        invalid |= ~np.isfinite(variance) | (variance <= 0)
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
    header.add_history('FLAGS allow-list: SOURCE only; original HDUs and spatial WCS retained')
    # IMAGE changes from float32 to float64. Ensure the serialized result fits the bound.
    estimated_bytes = sum(h.size for h in result) + 2880 * sum(len(h.header)//36 + 2 for h in result)
    if estimated_bytes > MAX_FILE_BYTES:
        raise WorkerError('invalid_output', 'processed FITS would exceed 256 MiB')
    result.writeto(output, overwrite=False, checksum=True)
    return clean_m


def _spectrum_preview(request):
    """Run the team's approximate WCS-WAVE photometry on trusted native inputs."""
    rows=request.get('observations')
    if not isinstance(rows,list) or not 1 <= len(rows) <= 120:
        raise WorkerError('invalid_request','Supply 1 to 120 native observations')
    output=_path(request.get('output_path'),'output_path')
    if output.exists() or Path(request['output_path']).is_symlink() or not output.parent.is_dir():
        raise WorkerError('invalid_output','output must be a new file in an existing directory')
    ra=_number(request,'ra_deg'); dec=_number(request,'dec_deg')
    radius=_number(request,'radius_pix',2.)
    subtraction=request.get('subtraction','zodi_subtracted')
    if not (0 <= ra < 360 and -90 <= dec <= 90 and .5 <= radius <= 10) or subtraction not in ('raw_calibrated','zodi_subtracted'):
        raise WorkerError('invalid_request','Unsupported coordinates, aperture or subtraction')
    from scripts.spectra import measure_cutout_point
    points=[]; failures=[]; skipped=0
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('frame_id'),str) or not 1<=len(row['frame_id'])<=512:
            raise WorkerError('invalid_request','Each observation requires a bounded frame_id')
        try:
            _,source,_=_request(dict(operation='spectrum',image_path=row.get('image_path'),ra_deg=ra,dec_deg=dec,radius_pix=radius))
            if source==output:
                raise WorkerError('invalid_output','Output must differ from every input')
            with fits.open(source,memmap=False,lazy_load_hdus=True) as hdus:
                _validate(hdus,'spectrum_preview')
            point=measure_cutout_point(source,ra,dec,radius_pix=radius,subtraction=subtraction)
            if point is None:
                skipped+=1; continue
            fields=('mjd','wavelength_um','bandwidth_um','flux_mjy','uncertainty_mjy','snr')
            if not all(math.isfinite(float(point[k])) for k in fields) or min(point['wavelength_um'],point['bandwidth_um'],point['uncertainty_mjy'])<=0:
                raise WorkerError('invalid_measurement','Non-finite or invalid measurement')
            detector=int(point['detector'])
            if not 1<=detector<=6:
                raise WorkerError('invalid_measurement','Missing detector identity')
            points.append(dict(frame_id=row['frame_id'],detector=f'D{detector}',detector_array=detector,
                               flagged=False,**{k:point[k] for k in fields}))
        except WorkerError as error:
            failures.append(dict(frame_id=row['frame_id'],code=error.code))
        except (OSError,ValueError,KeyError,TypeError,IndexError,RuntimeError):
            failures.append(dict(frame_id=row['frame_id'],code='invalid_spectral_wcs'))
    if not points:
        raise WorkerError('no_measurements','No complete usable aperture with valid spectral WCS was found')
    points.sort(key=lambda point:point['wavelength_um'])
    for i,point in enumerate(points,1): point['channel']=i
    summaries={}
    for detector in sorted({point['detector'] for point in points}):
        selected=[point for point in points if point['detector']==detector]
        summaries[detector]=dict(range=f"{min(p['wavelength_um'] for p in selected):.4f}-{max(p['wavelength_um'] for p in selected):.4f} um",
            mean_flux_mjy=float(np.mean([p['flux_mjy'] for p in selected])),mean_snr=float(np.mean([p['snr'] for p in selected])),channels=len(selected))
    result=dict(ra=ra,dec=dec,aperture_radius_pix=radius,subtraction_mode=subtraction,
        bad_pixel_mask='FLAGS allow-list: SOURCE only; finite pixels and positive variance',
        wcs_mode='WCS-WAVE visualization approximation',quality='experimental_visualization_photometry',
        scientifically_calibrated=False,molecular_detections=[],detectors_summary=summaries,
        total_channels=len(points),n_exposures_found=len(rows),n_masked_or_outside=skipped,n_failed=len(failures),
        failures=failures,spectrum=points,warnings=['wcs_wave_visualization_only','channel_is_measurement_index',
        'aperture_correction_not_applied','local_background_not_subtracted','zodi_model_uncertainty_not_propagated',
        'projected_pixel_area_approximation','incomplete_spectral_coverage'])
    encoded=json.dumps(result,allow_nan=False,separators=(',',':'))
    if len(encoded.encode())>1_048_576:
        raise WorkerError('invalid_output','Spectrum exceeds output size limit')
    with output.open('x') as stream: stream.write(encoded)
    return dict(status='ok',operation='spectrum_preview',output_path=str(output))


def validate_http_request(request):
    """Validate and freeze every shared path before accepting HTTP work."""
    if not isinstance(request, dict):
        raise WorkerError('invalid_request', 'request must be a JSON object')
    operation = request.get('operation')
    if operation == 'capabilities':
        return {'operation': operation}
    if operation not in ('preview', 'zodi', 'spectrum_preview'):
        raise WorkerError('invalid_request', 'unsupported operation')
    canonical = dict(request)
    if operation != 'spectrum_preview':
        _, source, output = _request(request)
        canonical.update(image_path=str(source), output_path=str(output))
        return canonical
    rows = request.get('observations')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 120:
        raise WorkerError('invalid_request', 'Supply 1 to 120 native observations')
    output = _path(request.get('output_path'), 'output_path')
    if output.exists() or Path(request['output_path']).is_symlink() or not output.parent.is_dir():
        raise WorkerError('invalid_output', 'output must be a new file in an existing directory')
    ra, dec = _number(request, 'ra_deg'), _number(request, 'dec_deg')
    radius = _number(request, 'radius_pix', 2.)
    subtraction = request.get('subtraction', 'zodi_subtracted')
    if not (0 <= ra < 360 and -90 <= dec <= 90 and .5 <= radius <= 10) or subtraction not in ('raw_calibrated', 'zodi_subtracted'):
        raise WorkerError('invalid_request', 'Unsupported coordinates, aperture or subtraction')
    canonical_rows = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('frame_id'), str) or not 1 <= len(row['frame_id']) <= 512:
            raise WorkerError('invalid_request', 'Each observation requires a bounded frame_id')
        _, source, _ = _request(dict(operation='spectrum', image_path=row.get('image_path'), ra_deg=ra, dec_deg=dec, radius_pix=radius))
        if source == output:
            raise WorkerError('invalid_output', 'Output must differ from every input')
        canonical_rows.append(dict(frame_id=row['frame_id'], image_path=str(source)))
    canonical.update(observations=canonical_rows, output_path=str(output),
        ra_deg=ra, dec_deg=dec, radius_pix=radius, subtraction=subtraction)
    return canonical


def execute(request):
    if isinstance(request, dict) and request.get('operation') == 'capabilities':
        return {'status': 'ok', 'operations': ['preview', 'zodi', 'spectrum_preview'],
            'spectrum': {'status': 'not_ready', 'code': 'missing_pixel_spectral_calibration'}}
    if isinstance(request,dict) and request.get('operation')=='spectrum_preview':
        return _spectrum_preview(request)
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
    # Also bound files produced by Astropy/Pillow while the parent supervises wall time.
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES, MAX_FILE_BYTES))
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise WorkerError('invalid_request', 'request exceeds 65536 bytes')
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
