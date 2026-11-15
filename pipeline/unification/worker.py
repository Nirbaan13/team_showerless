"""Bounded standalone unification worker; accepts only shared-root snapshots."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import uuid

import numpy as np
from astropy import units as u
from astropy.time import Time

from .ml import MAX_COMPRESSED, MAX_EXPANDED, load_bundle
from .readers import read_frame
from .resampling import resample, target_wcs


class UnificationError(ValueError):
    """A public, path-free validation or numerical error."""


class BoundedWriter:
    """Seekable ZIP destination that enforces the disk budget before every write."""
    def __init__(self, stream, limit):
        self.stream, self.limit = stream, limit

    def write(self, data):
        if self.stream.tell() + len(data) > self.limit:
            raise ValueError('compressed output exceeds limit')
        return self.stream.write(data)

    def seek(self, offset, whence=0):
        position = self.stream.tell()
        destination = offset if whence == 0 else position + offset if whence == 1 else None
        if destination is None or not 0 <= destination <= self.limit:
            raise ValueError('output seek exceeds limit')
        return self.stream.seek(offset, whence)

    def __getattr__(self, name):
        return getattr(self.stream, name)


def _object(value, required, optional=()):
    if not isinstance(value, dict) or set(value)-set(required)-set(optional) or not set(required) <= set(value):
        raise ValueError('invalid request fields')


def _integer(value, lo, hi):
    return type(value) is int and lo <= value <= hi


def validate_request(request):
    _object(request, ('schema_version', 'job_id', 'inputs', 'grid', 'options'))
    if type(request['schema_version']) is not int or request['schema_version'] != 1:
        raise ValueError('unsupported request schema')
    try:
        if str(uuid.UUID(request['job_id'])) != request['job_id']:
            raise ValueError('invalid job identity')
    except (TypeError, AttributeError, ValueError) as e:
        raise ValueError('invalid job identity') from e
    inputs = request['inputs']
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= 32:
        raise ValueError('input count must be between 1 and 32')
    for spec in inputs:
        _object(spec, ('id', 'path', 'sha256', 'profile'), ('image_hdu', 'plane_indices', 'metadata'))
        if not isinstance(spec['id'], str) or not 1 <= len(spec['id']) <= 256:
            raise ValueError('invalid input identity')
        if spec['profile'] not in ('generic', 'spherex', 'raster'):
            raise ValueError('invalid source profile')
        if not isinstance(spec['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', spec['sha256']):
            raise ValueError('invalid source checksum')
        p = spec['path']
        prefix = f"unifications/{request['job_id']}/inputs/"
        if not isinstance(p, str) or not p.startswith(prefix) or '\\' in p or '\x00' in p or any(c in ('.', '..') for c in p.split('/')) or PurePosixPath(p).is_absolute() or len(PurePosixPath(p).parts) != 4:
            raise ValueError('invalid input path')
        hdu = spec.get('image_hdu')
        if hdu is not None and not (_integer(hdu, 0, 1024) or isinstance(hdu, str) and 1 <= len(hdu) <= 68):
            raise ValueError('invalid image_hdu')
        planes = spec.get('plane_indices', [])
        if not isinstance(planes, list) or len(planes) > 8 or any(not _integer(i, 0, 2**31-1) for i in planes):
            raise ValueError('invalid plane_indices')
        if not isinstance(spec.get('metadata', {}), dict) or len(json.dumps(spec.get('metadata', {}), allow_nan=False)) > 16384:
            raise ValueError('invalid input metadata')
    if len({s['id'] for s in inputs}) != len(inputs):
        raise ValueError('duplicate frame identities')
    grid = request['grid']
    if not isinstance(grid, dict):
        raise ValueError('invalid target grid')
    kind = grid.get('kind')
    _object(grid, ('kind', 'width', 'height') + (('ra_degrees', 'dec_degrees', 'pixel_scale_arcsec') if kind == 'sky' else ()))
    if kind not in ('sky', 'pixel') or not _integer(grid['width'], 1, 512) or not _integer(grid['height'], 1, 512):
        raise ValueError('invalid target dimensions or grid kind')
    if kind == 'sky':
        values = [grid[k] for k in ('ra_degrees', 'dec_degrees', 'pixel_scale_arcsec')]
        if any(type(v) not in (int, float) or not np.isfinite(v) for v in values) or not (0 <= values[0] < 360 and -90 <= values[1] <= 90 and 0 < values[2] <= 3600):
            raise ValueError('invalid sky grid coordinates or scale')
    options = request['options']
    _object(options, (), ('normalization', 'mask_policy', 'target_unit'))
    if options.get('normalization', 'none') not in ('none', 'robust') or options.get('mask_policy', 'science') not in ('science', 'motion'):
        raise ValueError('unsupported normalization or mask policy')
    unit = options.get('target_unit')
    if unit is not None and (not isinstance(unit, str) or not 1 <= len(unit) <= 128):
        raise ValueError('invalid target unit')
    return request


def safe_path(root, relative):
    root = Path(root).resolve(strict=True)
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('symlink paths are forbidden')
    if not path.resolve().is_relative_to(root):
        raise ValueError('path escapes data root')
    return path


def _sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _artifact(root, path):
    return dict(path=str(path.relative_to(root)), bytes=path.stat().st_size, sha256=_sha(path))


def _run_job(request, root):
    validate_request(request)
    root = Path(root).resolve(strict=True)
    grid, options = request['grid'], request['options']
    records = []
    for spec in request['inputs']:
        source = safe_path(root, spec['path'])
        if not source.is_file() or source.stat().st_size > 256*1024**2:
            raise ValueError('input file absent or exceeds size limit')
        # Verify immediately before and after decoding to catch source replacement.
        if _sha(source) != spec['sha256']:
            raise ValueError('source checksum mismatch')
        frame = read_frame(source, spec, options.get('mask_policy', 'science'))
        if _sha(source) != spec['sha256']:
            raise ValueError('source checksum changed during decode')
        target_unit = options.get('target_unit')
        if target_unit is not None:
            try:
                if not frame.metadata['unit']:
                    raise ValueError('unknown source unit')
                factor = u.Unit(frame.metadata['unit']).to(u.Unit(target_unit))
                if not np.isfinite(factor):
                    raise ValueError('nonfinite unit factor')
            except (ValueError, TypeError) as e:
                raise ValueError('target unit conversion requires compatible declared physical units') from e
            frame.image *= factor
            frame.variance *= factor**2
            frame.metadata['source_unit'] = frame.metadata['unit']
            frame.metadata['unit'] = target_unit
            frame.metadata['unit_factor'] = factor
        registered = resample(frame, grid)
        meta = frame.metadata
        provenance = spec.get('metadata', {})
        observation = provenance.get('observation_id')
        if observation is not None and (not isinstance(observation, str) or len(observation) > 512):
            raise ValueError('invalid observation identity')
        if spec['profile'] == 'spherex':
            native_observation = meta.get('native_observation_id')
            native_detector = meta.get('native_detector')
            trusted_detector = provenance.get('detector_array')
            if trusted_detector is not None and not _integer(trusted_detector, 1, 6):
                raise ValueError('invalid trusted detector identity')
            if native_detector is not None and trusted_detector is not None and native_detector != trusted_detector:
                raise ValueError('native and trusted detector identities disagree')
            detector = native_detector if native_detector is not None else trusted_detector
            physical = f'{native_observation}:D{detector}' if native_observation and detector else None
            if physical is not None:
                if observation is not None and observation != physical:
                    raise ValueError('native and trusted observation identities disagree')
                observation = physical
        provider = provenance.get('provider')
        if provider is not None and (not isinstance(provider, str) or len(provider) > 128):
            raise ValueError('invalid observation provider')
        meta.update(frame_id=spec['id'], source_sha256=spec['sha256'], profile=spec['profile'],
                    provenance=provenance, observation_identity=f'{provider}:{observation}' if observation and provider else None,
                    analysis_eligible=False)
        records.append((registered, meta))
    # Exposure chronology is authoritative; unknown times retain request ordering.
    if all(meta['midpoint_utc'] is not None for _, meta in records):
        records.sort(key=lambda r: Time(r[1]['midpoint_utc'], scale='utc').tai.jd)
    arrays = {name: np.stack([a[name] for a, _ in records]).astype(np.float32 if name in ('images', 'variance', 'footprint') else bool)
              for name in records[0][0]}
    if np.isinf(arrays['images']).any() or np.isinf(arrays['variance']).any():
        raise ValueError('physical values exceed float32 bundle range')
    frames = [m for _, m in records]
    tensor = np.where(arrays['valid_mask'], arrays['images'], 0).astype(np.float32)
    for index, frame in enumerate(frames):
        good = arrays['valid_mask'][index]
        offset, scale = 0., 1.
        if options.get('normalization', 'none') == 'robust' and good.any():
            pixels = arrays['images'][index][good].astype(float)
            offset = float(np.median(pixels))
            scale = float(1.4826*np.median(np.abs(pixels-offset))) or 1.
            tensor[index] = np.where(good, (arrays['images'][index].astype(float)-offset)/scale, 0)
        frame['tensor_normalization'] = dict(kind=options.get('normalization', 'none'), offset=offset, scale=scale)
    if not np.isfinite(tensor).all():
        raise ValueError('normalized tensor exceeds float32 range')
    arrays['tensor'] = tensor
    known = np.array([f['midpoint_utc'] is not None for f in frames])
    times = np.full(len(frames), np.nan)
    if known.any():
        dates = Time([f['midpoint_utc'] for f in frames if f['midpoint_utc']], scale='utc')
        times[known] = (dates-dates[0]).to_value('hour')
    arrays.update(times=times, time_known_mask=known, frame_ids=np.array([f['frame_id'] for f in frames], dtype='U256'),
                  observation_ids=np.array([f['observation_identity'] or '' for f in frames], dtype='U650'),
                  dates_utc=np.array([f['midpoint_utc'] or '' for f in frames], dtype='U64'), schema_version=np.array(1, dtype=np.int16))
    warnings_list = ['Bilinear point sampling does not conserve integrated flux or match PSFs.',
                     'Resampling induces covariance; only independent input-pixel variance is propagated.',
                     'Registration does not grant production analysis eligibility.']
    metadata = dict(schema_version=1, job_id=request['job_id'], grid=grid,
                    target_wcs=target_wcs(grid).to_header().tostring(sep='\n') if grid['kind'] == 'sky' else None,
                    frames=frames, time_unit='hours from first known real exposure midpoint',
                    resampling=dict(method='bilinear normalized valid weights', flux_conserving=False, covariance='not represented',
                                    minimum_valid_support=0.995, variance='sum(squared normalized weights * independent input variance)'),
                    options=options, warnings=warnings_list)
    manifest = json.dumps(metadata, allow_nan=False, ensure_ascii=True, separators=(',', ':')).encode()
    if len(manifest) > 1024**2:
        raise ValueError('manifest exceeds limit')
    arrays['manifest'] = np.frombuffer(manifest, dtype=np.uint8)
    if sum(a.nbytes for a in arrays.values()) + len(arrays)*16384 > MAX_EXPANDED:
        raise ValueError('expanded output exceeds limit')
    output = safe_path(root, f"unifications/{request['job_id']}/output")
    output.mkdir(exist_ok=True)
    # Never truncate a symlink or publish partially written arrays.
    bundle_path, manifest_path = output/'dataset.npz', output/'manifest.json'
    for p in (bundle_path, manifest_path, output/'dataset.npz.partial', output/'manifest.json.partial'):
        if p.is_symlink():
            raise ValueError('symlink output is forbidden')
    partial = output/'dataset.npz.partial'
    mp = output/'manifest.json.partial'
    try:
        with partial.open('xb') as f:
            np.savez_compressed(BoundedWriter(f, MAX_COMPRESSED), **arrays)
        if partial.stat().st_size > MAX_COMPRESSED:
            raise ValueError('compressed output exceeds limit')
        loaded = load_bundle(partial)
        try:
            loaded.motion_inputs()
            ready = True
        except ValueError as e:
            ready = False
            warnings_list.append(str(e))
        # Same exact manifest lives in the bundle and standalone artifact.
        # Eligibility warning is response-only; metadata retains declared limitations.
        with mp.open('xb') as f:
            f.write(manifest)
        os.replace(partial, bundle_path)
        os.replace(mp, manifest_path)
    finally:
        partial.unlink(missing_ok=True)
        mp.unlink(missing_ok=True)
    return dict(schema_version=1, job_id=request['job_id'], status='completed', bundle=_artifact(root, bundle_path),
                manifest=_artifact(root, manifest_path), frame_count=len(frames), width=grid['width'], height=grid['height'],
                detection_ready=ready, warnings=warnings_list)


def run_job(request: dict, root: Path) -> dict:
    try:
        return _run_job(request, root)
    except ValueError:
        raise
    except (OSError, RuntimeError, OverflowError, TypeError, KeyError, AttributeError) as e:
        raise UnificationError('image unification could not process the selected input') from e


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError('one bounded request file is required')
        path = Path(sys.argv[1])
        if path.stat().st_size > 1024**2:
            raise ValueError('request exceeds limit')
        with path.open('r', encoding='utf-8') as f:
            request = json.load(f, parse_constant=lambda s: (_ for _ in ()).throw(ValueError('nonfinite request')))
        result = run_job(request, Path(os.environ['UNIFICATION_DATA_ROOT']))
        print(json.dumps(result, allow_nan=False), flush=True)
        return 0
    except Exception:
        # Astropy/file errors can contain paths; the process boundary never exposes them.
        print(json.dumps(dict(status='failed', code='invalid_request', message='Image unification failed validation or processing.')), flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
