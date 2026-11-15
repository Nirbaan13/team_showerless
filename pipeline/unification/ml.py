"""Validated pickle-free NPZ loader for general ML and the motion detector."""
from dataclasses import dataclass
import io
import json
import math
from pathlib import Path
import zipfile

import numpy as np

MAX_COMPRESSED = 192 * 1024**2
MAX_EXPANDED = 192 * 1024**2
MEMBERS = {'images', 'tensor', 'valid_mask', 'footprint', 'variance', 'variance_valid_mask',
           'outlier', 'bloom', 'times', 'time_known_mask', 'frame_ids', 'observation_ids', 'dates_utc',
           'manifest', 'schema_version'}


@dataclass
class Bundle:
    images: np.ndarray
    tensor: np.ndarray
    valid_mask: np.ndarray
    footprint: np.ndarray
    variance: np.ndarray
    variance_valid_mask: np.ndarray
    outlier: np.ndarray
    bloom: np.ndarray
    times: np.ndarray
    time_known_mask: np.ndarray
    frame_ids: np.ndarray
    observation_ids: np.ndarray
    dates_utc: np.ndarray
    metadata: dict

    def motion_inputs(self):
        """Supply physical images and hours from the first real exposure midpoint.

        Registration and comparable declared units/passbands qualify the numerical
        contract only. Users must assess PSF differences and scientific suitability.
        """
        from astropy import units as u
        if self.metadata.get('grid', {}).get('kind') != 'sky':
            raise ValueError('motion detection requires sky registration')
        if len(self.images) < 3 or not self.time_known_mask.all() or not np.isfinite(self.times).all() or np.any(np.diff(self.times) <= 0):
            raise ValueError('motion detection requires at least three distinct increasing known exposure midpoints')
        frames = self.metadata['frames']
        identities = [f.get('observation_identity') for f in frames]
        if any(not isinstance(i, str) or not i for i in identities):
            raise ValueError('motion detection requires known observation identities')
        if any(identities.count(i) > 1 for i in identities if i is not None):
            raise ValueError('duplicate observation identities cannot be motion epochs')
        bands = [(f.get('mission'), f.get('instrument'), f.get('band'), f.get('wavelength_min'),
                  f.get('wavelength_max'), f.get('wavelength_unit')) for f in frames]
        if any(not f.get('instrument') or not f.get('mission') or not f.get('band') for f in frames) or any(b != bands[0] for b in bands):
            raise ValueError('motion detection requires compatible known passbands and instruments')
        units = [f.get('unit') for f in frames]
        if not all(units) or len(set(units)) != 1:
            raise ValueError('motion detection requires compatible known physical units')
        try:
            unit = u.Unit(units[0])
            # Counts/ADU do not establish calibrated inter-exposure photometry.
            if not any(unit.is_equivalent(ref) for ref in (u.Jy, u.Jy/u.sr, u.W/u.m**2, u.W/u.m**2/u.sr)):
                raise ValueError('units do not establish a calibrated flux scale')
        except (ValueError, TypeError) as e:
            raise ValueError('motion detection requires calibrated physical units') from e
        if not np.all(self.valid_mask.any(axis=(1, 2))):
            raise ValueError('every motion frame requires valid sky coverage')
        return self.images, self.times


def _read_arrays(path):
    if Path(path).stat().st_size > MAX_COMPRESSED:
        raise ValueError('compressed bundle exceeds limit')
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if len(infos) > 32 or len(set(names)) != len(names) or set(names) != {m+'.npy' for m in MEMBERS}:
                raise ValueError('bundle has missing, duplicate or unexpected members')
            if sum(i.file_size for i in infos) > MAX_EXPANDED:
                raise ValueError('expanded bundle exceeds limit')
            arrays = {}
            for info in infos:
                if info.flag_bits & 1:
                    raise ValueError('encrypted bundle member is unsupported')
                with z.open(info) as f:
                    version = np.lib.format.read_magic(f)
                    if version == (1, 0):
                        shape, order, dtype = np.lib.format.read_array_header_1_0(f, max_header_size=16384)
                    elif version == (2, 0):
                        shape, order, dtype = np.lib.format.read_array_header_2_0(f, max_header_size=16384)
                    else:
                        raise ValueError('unsupported NPY version')
                    if dtype.hasobject or dtype.fields or dtype.kind not in 'biufU' or len(shape) > 3 or any(type(n) is not int or n < 0 for n in shape):
                        raise ValueError('unsafe bundle dtype or shape')
                    size = math.prod(shape)*dtype.itemsize
                    if size > MAX_EXPANDED or size != info.file_size-f.tell():
                        raise ValueError('declared array size exceeds available bounded data')
                payload = z.read(info)
                arrays[info.filename[:-4]] = np.load(io.BytesIO(payload), allow_pickle=False, max_header_size=16384)
            return arrays
    except (OSError, EOFError, zipfile.BadZipFile, KeyError, OverflowError) as e:
        raise ValueError('invalid bounded NPZ bundle') from e


def load_bundle(path):
    arrays = _read_arrays(path)
    if arrays['schema_version'].shape != () or arrays['schema_version'].dtype.kind not in 'iu' or arrays['schema_version'].item() != 1:
        raise ValueError('unsupported bundle schema')
    raw = arrays.pop('manifest')
    arrays.pop('schema_version')
    if raw.dtype != np.uint8 or raw.ndim != 1 or len(raw) > 1024**2:
        raise ValueError('invalid manifest encoding')
    try:
        metadata = json.loads(raw.tobytes().decode('utf-8'), parse_constant=lambda s: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as e:
        raise ValueError('invalid bundle manifest') from e
    images = arrays['images']
    if images.ndim != 3 or not 1 <= images.shape[0] <= 32 or not all(1 <= n <= 512 for n in images.shape[1:]):
        raise ValueError('invalid bundle image dimensions')
    n, h, w = images.shape
    if not isinstance(metadata, dict) or metadata.get('schema_version') != 1 or not isinstance(metadata.get('frames'), list) or len(metadata['frames']) != n or not all(isinstance(f, dict) for f in metadata['frames']):
        raise ValueError('invalid bundle provenance')
    if any(str(arrays['frame_ids'][i]) != f.get('frame_id') or str(arrays['observation_ids'][i]) != (f.get('observation_identity') or '') or str(arrays['dates_utc'][i]) != (f.get('midpoint_utc') or '') for i, f in enumerate(metadata['frames'])):
        raise ValueError('manifest identities disagree with frame vectors')
    grid = metadata.get('grid', {})
    if not isinstance(grid, dict) or grid.get('kind') not in ('sky', 'pixel') or grid.get('width') != w or grid.get('height') != h:
        raise ValueError('manifest grid disagrees with arrays')
    for name in ('images', 'tensor', 'footprint', 'variance'):
        if arrays[name].shape != images.shape or arrays[name].dtype.kind != 'f':
            raise ValueError('invalid image array shape or type')
    for name in ('valid_mask', 'variance_valid_mask', 'outlier', 'bloom'):
        if arrays[name].shape != images.shape or arrays[name].dtype != np.bool_:
            raise ValueError('invalid mask shape or type')
    for name in ('times', 'time_known_mask', 'frame_ids', 'observation_ids', 'dates_utc'):
        if arrays[name].shape != (n,):
            raise ValueError('invalid frame vector shape')
    if arrays['times'].dtype.kind != 'f' or arrays['time_known_mask'].dtype != np.bool_:
        raise ValueError('invalid time vector type')
    for name in ('frame_ids', 'observation_ids', 'dates_utc'):
        if arrays[name].dtype.kind != 'U' or arrays[name].dtype.itemsize > 4096:
            raise ValueError('invalid identity vector type')
    valid, vv = arrays['valid_mask'], arrays['variance_valid_mask']
    if not np.array_equal(np.isfinite(images), valid) or np.isinf(images).any():
        raise ValueError('physical image and validity mask disagree')
    variance = arrays['variance']
    if not np.array_equal(np.isfinite(variance), vv) or np.any(vv & (~valid | (variance < 0))) or np.isinf(variance).any():
        raise ValueError('variance and validity mask disagree')
    if not np.isfinite(arrays['tensor']).all() or np.any(arrays['tensor'][~valid] != 0):
        raise ValueError('tensor must be finite and zero at invalid pixels')
    fp = arrays['footprint']
    if not np.isfinite(fp).all() or np.any((fp < 0) | (fp > 1)) or np.any(valid & (fp <= 0)):
        raise ValueError('invalid interpolation footprint')
    known = arrays['time_known_mask']
    if not np.array_equal(np.isfinite(arrays['times']), known) or np.isinf(arrays['times']).any():
        raise ValueError('time mask disagrees with known times')
    from astropy.time import Time
    dates = [f.get('midpoint_utc') for f in metadata['frames']]
    if any(bool(d) != bool(k) for d, k in zip(dates, known)):
        raise ValueError('manifest times disagree with arrays')
    if known.any():
        try:
            observed = Time([d for d in dates if d], scale='utc')
            expected = (observed-observed[0]).to_value('hour')
        except (ValueError, TypeError) as e:
            raise ValueError('invalid exposure midpoint') from e
        if not np.allclose(arrays['times'][known], expected, atol=1e-8, rtol=1e-10):
            raise ValueError('relative hours disagree with exposure midpoints')
    return Bundle(metadata=metadata, **arrays)
