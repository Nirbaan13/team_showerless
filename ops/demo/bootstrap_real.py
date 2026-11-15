#!/usr/bin/env python3
"""Materialize pinned, genuine archive FITS into the two offline demo volumes.

The lock records original archive identities. This command never manufactures
observations, fills missing epochs, or labels an archive outage as absent sky.
Run with the scientific environment documented in PROVENANCE.AI.md.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import shutil
import sys
import urllib.parse
import urllib.request

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.visualization import ZScaleInterval
from PIL import Image

MAX_FITS_BYTES = 24 * 1024 * 1024
ARCHIVE_HOSTS = {'irsa.ipac.caltech.edu', 'nasa-irsa-spherex.s3.us-east-1.amazonaws.com'}


def archive_url(value, allow_test_http=False):
    p = urllib.parse.urlsplit(value)
    fixture = allow_test_http and p.scheme == 'http' and p.hostname in {'127.0.0.1', '::1'}
    if p.username or p.password or p.fragment or not (fixture or p.scheme == 'https' and p.hostname in ARCHIVE_HOSTS):
        raise ValueError('Use an official HTTPS archive URL')
    return value


def asset_path(value):
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] != 'fits' or p.suffix != '.fits':
        raise ValueError('Unsafe FITS asset path')
    return Path(*p.parts)


def validate_fits(path, observation, target):
    body = path.read_bytes()
    if len(body) != observation['bytes']:
        raise ValueError(f'{path}: size differs from pinned archive artifact')
    if hashlib.sha256(body).hexdigest() != observation['sha256']:
        raise ValueError(f'{path}: checksum differs from pinned archive artifact')
    with fits.open(path, memmap=False) as hdus:
        hdus.verify('exception')
        image = hdus['IMAGE']
        combined = hdus[0].header.copy()
        combined.extend(image.header, update=True)
        if int(combined['DETECTOR']) != observation['detector']:
            raise ValueError('Native FITS detector differs from manifest detector')
        if str(combined['DATE-OBS']).rstrip('Z') != observation['observation_date'].rstrip('Z'):
            raise ValueError('Native FITS observation date differs from manifest')
        wcs = WCS(image.header).celestial
        try:
            x, y = wcs.all_world2pix([[target['ra_deg'], target['dec_deg']]], 0, quiet=False)[0]
        except Exception as exc:
            raise ValueError('Target has no converged native FITS coverage') from exc
        actual_ra, actual_dec = wcs.all_pix2world([[x, y]], 0)[0]
        requested = np.radians([target['ra_deg'], target['dec_deg']])
        actual = np.radians([actual_ra, actual_dec])
        separation = np.arccos(np.clip(np.sin(requested[1])*np.sin(actual[1]) + np.cos(requested[1])*np.cos(actual[1])*np.cos(requested[0]-actual[0]), -1, 1))
        if not np.isfinite(separation) or separation > np.radians(0.01 / 3600):
            raise ValueError('Target has no reliable native FITS coverage roundtrip')
        ny, nx = image.data.shape
        if not np.isfinite([x, y]).all() or not (-.5 <= x < nx-.5 and -.5 <= y < ny-.5):
            raise ValueError('Target has no coverage in the native FITS footprint')
        return {'shape': [ny, nx], 'target_pixel_xy': [float(x), float(y)],
                'finite_pixel_fraction': float(np.isfinite(image.data).mean()),
                'hdus': [h.name for h in hdus]}


def seed_native_index(manifest, output, verify_only):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend/python'))
    from irsa_mirror import MirrorIndex
    path = output / 'api-data/irsa-mirror.sqlite'
    if verify_only and not path.is_file():
        raise ValueError('Missing offline native metadata index')
    index = MirrorIndex(path)
    try:
        for target in manifest['targets']:
            for obs in target['observations']:
                row = obs.get('native_index_row')
                if not row:
                    continue
                source_path = urllib.parse.urlsplit(obs['source_url']).path
                expected_key = source_path.removeprefix('/ibe/data/spherex/').lstrip('/')
                if row['key'] != expected_key:
                    raise ValueError('Native metadata key differs from pinned source URL')
                native = row['body']['observation']
                if row['detector'] != obs['detector'] or native['detector_array'] != obs['detector']:
                    raise ValueError('Native metadata detector differs from pinned observation')
                if native['observation_date'].rstrip('Z') != obs['observation_date'].rstrip('Z'):
                    raise ValueError('Native metadata date differs from pinned observation')
                existing = index.db.execute('SELECT * FROM mirror_objects WHERE key=?', (row['key'],)).fetchone()
                if existing and (existing['identity'] != row['identity'] or existing['release'] != row['release']
                        or json.loads(existing['body']) != row['body']
                        or json.loads(existing['footprint']) != row['footprint']
                        or existing['observed'] != row['observed'] or existing['detector'] != row['detector']):
                    raise ValueError('Existing native metadata or geometry differs from the pinned source')
                if not existing and verify_only:
                    raise ValueError('Missing pinned native metadata row')
                if not verify_only:
                    with index.db:
                        index.db.execute('INSERT OR IGNORE INTO mirror_objects VALUES (?,?,?,?,?,?,?)',
                            (row['key'], row['release'], row['identity'], json.dumps(row['body']),
                             json.dumps(row['footprint']), row['observed'], row['detector']))
        if not verify_only:
            index.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    finally:
        index.db.close()



def preview_pixels(path):
    """Display conversion of IMAGE values on the unchanged native pixel grid."""
    with fits.open(path, memmap=False) as hdus:
        values = np.asarray(hdus['IMAGE'].data, dtype=float)
        finite = np.isfinite(values)
        gray = np.zeros(values.shape, dtype=np.uint8)
        lo = hi = None
        if finite.any():
            lo, hi = map(float, ZScaleInterval().get_limits(values[finite]))
            if hi > lo:
                gray[finite] = np.rint(np.clip((values[finite] - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
        rgba = np.stack([gray, gray, gray, finite.astype(np.uint8) * 255], axis=-1)
        method = {'name': 'raw_calibrated_IMAGE_zscale', 'source_hdu': 'IMAGE',
                  'normalization': 'astropy.visualization.ZScaleInterval',
                  'zscale_limits': [lo, hi], 'mode': 'RGBA',
                  'row_order': 'native_array', 'interpolation': 'none', 'reprojection': False}
        flagged = None
        if 'FLAGS' in hdus:
            flags = hdus['FLAGS'].data
            if flags.shape != values.shape:
                raise ValueError('Native FLAGS and IMAGE dimensions differ')
            flagged = float(np.count_nonzero(flags != 0) * 100 / flags.size)
        return rgba, method, flagged


def seed_previews(manifest, output, verify_only):
    public_root = output / 'api-data'
    manifest_path = public_root / 'demo/preview-manifest.json'
    existing = json.loads(manifest_path.read_text()) if verify_only and manifest_path.is_file() else None
    if verify_only and existing is None:
        raise ValueError('Missing real archive preview manifest')
    expected = {'schema_version': 1, 'dataset_kind': 'real_archive',
                'discovery_complete': False, 'field_only': True, 'targets': []}
    seen = set()
    for target in manifest['targets']:
        note = target.get('coordinate_note', 'Reference query coordinates; native field previews do not establish a target detection or epoch astrometry.')
        item = {key: target[key] for key in ['id', 'name', 'ra_deg', 'dec_deg', 'recommended_detector']}
        item.update(coordinate_note=note, proper_motion_note=note, field_only=True,
                    discovery_complete=False, availability=target['availability'], observations=[])
        for obs in target['observations']:
            native = obs.get('native_index_row', {}).get('body', {}).get('observation')
            frame_id = native['frame_id'] if native else obs['id']
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', frame_id) or frame_id in seen:
                raise ValueError('Invalid or repeated native preview frame identity')
            seen.add(frame_id)
            pixels, method, flagged = preview_pixels(public_root / 'demo' / asset_path(obs['path']))
            preview_url = f'/demo/previews/{frame_id}.png'
            image_path = public_root / preview_url.lstrip('/')
            if not verify_only:
                image_path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(pixels).save(image_path, format='PNG')
            if not image_path.is_file():
                raise ValueError('Missing real archive preview PNG')
            with Image.open(image_path) as png:
                if png.format != 'PNG' or png.mode != 'RGBA' or png.size != (pixels.shape[1], pixels.shape[0]):
                    raise ValueError('Real archive preview dimensions or format differ from native IMAGE')
                if not np.array_equal(np.array(png), pixels):
                    raise ValueError('Real archive preview pixels differ from native IMAGE display conversion')
            record = {'frame_id': frame_id, 'observation_date': obs['observation_date'],
                      'detector': obs['detector'], 'release': obs['release'],
                      'preview_url': preview_url, 'fits_url': '/demo/' + obs['path'],
                      'source_url': obs['download_url'], 'source_sha256': obs['sha256'],
                      'preview_sha256': hashlib.sha256(image_path.read_bytes()).hexdigest(),
                      'image_width': pixels.shape[1], 'image_height': pixels.shape[0],
                      'rendering_method': method, 'field_only': True,
                      'proper_motion_note': note, 'discovery_complete': False}
            if flagged is not None:
                record['flagged_pixel_percentage'] = flagged
            item['observations'].append(record)
        expected['targets'].append(item)
    if verify_only:
        if existing != expected:
            raise ValueError('Real archive preview manifest metadata or source cross-references differ from pinned FITS')
    else:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(expected, indent=2) + '\n')


def bootstrap(manifest_path, output, *, verify_only=False, allow_test_http=False):
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get('schema_version') != 1 or manifest.get('dataset_kind') != 'real_archive':
        raise ValueError('Expected a version 1 real_archive source lock')
    output = Path(output)
    count = 0
    for target in manifest['targets']:
        observations = target['observations']
        if target['availability'] not in {'available', 'discovery_unavailable', 'no_coverage'}:
            raise ValueError('Unknown target availability')
        if target['availability'] != 'available' and (observations or not target.get('reason')):
            raise ValueError('Unavailable target requires an explicit reason and no observations')
        if target['availability'] == 'available' and not observations:
            raise ValueError('Available target needs at least one pinned observation')
        for obs in observations:
            if not allow_test_http and not obs.get('native_index_row'):
                raise ValueError('Pinned native source metadata is required for real archive seeds')
            relative = asset_path(obs['path'])
            archive_url(obs['source_url'], allow_test_http)
            url = archive_url(obs['download_url'], allow_test_http)
            if not 0 < obs['bytes'] <= MAX_FITS_BYTES:
                raise ValueError('FITS artifact exceeds size budget')
            path = output / 'api-data/demo' / relative
            if not path.exists():
                if verify_only:
                    raise ValueError(f'Missing offline asset: {path}')
                path.parent.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(url, timeout=60) as response:
                    if response.geturl() != url:
                        raise ValueError('Archive redirected to an unpinned URL')
                    body = response.read(MAX_FITS_BYTES + 1)
                if len(body) > MAX_FITS_BYTES:
                    raise ValueError('Archive response exceeds size budget')
                tmp = path.with_suffix('.fits.part')
                tmp.write_bytes(body)
                try:
                    validate_fits(tmp, obs, target)
                    tmp.replace(path)
                finally:
                    tmp.unlink(missing_ok=True)
            validate_fits(path, obs, target)
            mlpath = output / 'ml-data/demo' / relative
            if verify_only:
                validate_fits(mlpath, obs, target)
            elif not mlpath.exists():
                mlpath.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, mlpath)
            else:
                validate_fits(mlpath, obs, target)
            count += 1
    seed_native_index(manifest, output, verify_only)
    seed_previews(manifest, output, verify_only)
    if not verify_only:
        for prefix in ['api-data', 'ml-data']:
            destination = output / prefix / 'demo/manifest.json'
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(manifest, indent=2) + '\n')
        (output / 'provenance.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return {'targets': len(manifest['targets']), 'observations': count, 'verified_offline': verify_only}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('real_sources.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true', help='Verify pinned files without network access')
    args = parser.parse_args()
    print(json.dumps(bootstrap(args.manifest, args.output, verify_only=args.verify_only)))


if __name__ == '__main__':
    main()
