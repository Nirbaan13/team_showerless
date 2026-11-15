"""Scientific and serialization contracts exercised through real files."""
import gzip
import hashlib
import io
import json
import sys
import uuid
import zipfile
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'pipeline'))
sys.path.insert(0, str(ROOT / 'ml/pvusatov/backend/inference'))


def wcs_header(size=32, angle=0, offset=(0, 0)):
    w = WCS(naxis=2)
    w.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    w.wcs.crval = [20, 30]
    w.wcs.crpix = [(size + 1) / 2 + offset[0], (size + 1) / 2 + offset[1]]
    t = np.deg2rad(angle)
    w.wcs.cd = np.array([[-np.cos(t), np.sin(t)], [np.sin(t), np.cos(t)]]) / 3600
    h = w.to_header()
    h['BUNIT'] = 'Jy'
    h['INSTRUME'] = 'Test camera'
    h['TELESCOP'] = 'Test observatory'
    h['FILTER'] = 'r'
    h['DATE-OBS'] = '2026-01-01T00:00:00'
    h['EXPTIME'] = 60
    return h


def request_for(tmp_path, sources, grid=None, options=None):
    job_id = str(uuid.uuid4())
    base = tmp_path / 'unifications' / job_id / 'inputs'
    base.mkdir(parents=True)
    inputs = []
    for i, source in enumerate(sources):
        path = base / (str(i) + source.suffix)
        path.write_bytes(source.read_bytes())
        inputs.append(dict(id=f'frame-{i}', path=str(path.relative_to(tmp_path)),
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest(), profile='generic',
                           image_hdu=None, plane_indices=[], metadata={}))
    return dict(schema_version=1, job_id=job_id, inputs=inputs,
                grid=grid or dict(kind='sky', ra_degrees=20, dec_degrees=30,
                                  width=32, height=32, pixel_scale_arcsec=1),
                options=options or dict(normalization='none', mask_policy='science', target_unit=None))


def run_bundle(tmp_path, request):
    from unification.worker import run_job
    from unification.ml import load_bundle
    result = run_job(request, tmp_path)
    return result, load_bundle(tmp_path / result['bundle']['path'])


@pytest.mark.parametrize('kind', ['primary', 'extension', 'unsigned', 'gzip', 'tile'])
def test_fits_native_formats(tmp_path, kind):
    data = np.arange(1024, dtype=np.uint16 if kind == 'unsigned' else np.float32).reshape(32, 32)
    p = tmp_path / ('source.fits.gz' if kind == 'gzip' else 'source.fits')
    h = wcs_header()
    image = fits.CompImageHDU(data, h, name='SCI') if kind == 'tile' else fits.ImageHDU(data, h, name='SCI')
    hdus = fits.HDUList([fits.PrimaryHDU(), image]) if kind in ('extension', 'tile') else fits.HDUList([fits.PrimaryHDU(data, h)])
    hdus.writeto(p)
    result, b = run_bundle(tmp_path, request_for(tmp_path, [p]))
    np.testing.assert_allclose(b.images[0], data, atol=1e-6)
    assert b.valid_mask.all() and np.isfinite(b.tensor).all()
    assert result['detection_ready'] is False
    assert b.metadata['frames'][0]['unit'] == 'Jy'
    assert b.metadata['frames'][0]['midpoint_utc'].startswith('2026-01-01T00:00:30')


def test_ambiguous_hdus_and_cube_selection(tmp_path):
    p = tmp_path / 'cube.fits'
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.ones((2, 32, 32)), wcs_header(), name='SCI'),
                  fits.ImageHDU(np.zeros((32, 32)), name='OTHER')]).writeto(p)
    req = request_for(tmp_path, [p])
    from unification.worker import run_job
    with pytest.raises(ValueError, match='ambiguous'):
        run_job(req, tmp_path)
    req['inputs'][0]['image_hdu'] = 'SCI'
    with pytest.raises(ValueError, match='plane'):
        run_job(req, tmp_path)
    req['inputs'][0]['plane_indices'] = [1]
    _, b = run_bundle(tmp_path, req)
    np.testing.assert_allclose(b.images, 1)


def test_masks_squared_variance_and_unit_conversion(tmp_path):
    p = tmp_path / 'variance.fits'
    h = wcs_header(offset=(0.5, 0.5))
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.ones((32, 32))*2, h, name='SCI'),
                  fits.ImageHDU(np.ones((32, 32))*4, name='VARIANCE'),
                  fits.ImageHDU(np.pad(np.ones((1, 1), dtype=np.uint16), ((0, 31), (0, 31))), name='DQ')]).writeto(p)
    req = request_for(tmp_path, [p], options=dict(target_unit='mJy', normalization='robust', mask_policy='science'))
    _, b = run_bundle(tmp_path, req)
    np.testing.assert_allclose(b.images[0, 8:24, 8:24], 2000)
    np.testing.assert_allclose(b.variance[0, 8:24, 8:24], 1e6, rtol=1e-7)
    assert not b.valid_mask[0, 0, 0] or b.footprint[0, 0, 0] < 1
    assert np.isfinite(b.tensor).all()
    assert b.metadata['resampling']['covariance'] == 'not represented'


def test_raster_requires_pixel_mode_and_retains_unknowns(tmp_path):
    p = tmp_path / 'preview.png'
    Image.fromarray(np.arange(64, dtype=np.uint8).reshape(8, 8)).save(p)
    req = request_for(tmp_path, [p])
    req['inputs'][0]['profile'] = 'raster'
    from unification.worker import run_job
    with pytest.raises(ValueError, match='WCS|pixel'):
        run_job(req, tmp_path)
    req['grid'] = dict(kind='pixel', width=8, height=8)
    _, b = run_bundle(tmp_path, req)
    assert b.metadata['frames'][0]['unit'] is None
    assert b.metadata['frames'][0]['midpoint_utc'] is None
    with pytest.raises(ValueError, match='sky'):
        b.motion_inputs()


def test_unknown_units_times_and_duplicate_observations_block_motion(tmp_path):
    p = tmp_path / 'unknown.fits'
    h = wcs_header()
    del h['DATE-OBS']; del h['BUNIT']
    fits.writeto(p, np.ones((32, 32)), h)
    req = request_for(tmp_path, [p, p, p])
    for i in req['inputs']:
        i['metadata'] = dict(provider='eso', observation_id='same')
    _, b = run_bundle(tmp_path, req)
    assert not b.time_known_mask.any()
    with pytest.raises(ValueError):
        b.motion_inputs()
    req['options']['target_unit'] = 'Jy'
    from unification.worker import run_job
    with pytest.raises(ValueError, match='unit'):
        run_job(req, tmp_path)


def test_registered_moving_source_roundtrip_real_detector(tmp_path):
    from ml_inference.detector import find_candidates
    size = 64
    target = WCS(wcs_header(size))
    yy, xx = np.mgrid[:size, :size]
    rng = np.random.default_rng(53)
    sources = []
    positions = [(18 + 4*i, 22 + 2*i) for i in range(4)]
    for i, ((px, py), angle) in enumerate(zip(positions, [0, 13, -9, 25])):
        h = wcs_header(size, angle, (i * .3, -i * .2))
        h['DATE-OBS'] = f'2026-01-01T0{i}:00:00'
        source_wcs = WCS(h)
        ra, dec = source_wcs.all_pix2world(xx, yy, 0)
        tx, ty = target.all_world2pix(ra, dec, 0)
        data = rng.normal(0, 0.6, (size, size)) + 80*np.exp(-((tx-px)**2+(ty-py)**2)/(2*1.4**2))
        data[:2] = np.nan
        p = tmp_path / f'epoch-{i}.fits'
        fits.writeto(p, data, h)
        sources.append(p)
    req = request_for(tmp_path, sources)
    req['grid'].update(width=size, height=size)
    for i, spec in enumerate(req['inputs']):
        spec['metadata'] = dict(provider='test', observation_id=f'injected-epoch-{i}')
    result, b = run_bundle(tmp_path, req)
    images, times = b.motion_inputs()
    np.testing.assert_allclose(times, [0, 1, 2, 3], atol=1e-8)
    candidates = find_candidates(images, times, min_snr=6, min_speed=2, max_speed=7)
    assert result['detection_ready'] is True
    assert any(len(c.epochs) == 4 and np.max(np.linalg.norm(np.array(c.positions_xy)-positions, axis=1)) < 1.5 for c in candidates)


def test_paths_hashes_and_limits(tmp_path):
    from unification.worker import run_job
    p = tmp_path / 'one.fits'; fits.writeto(p, np.ones((32, 32)), wcs_header())
    req = request_for(tmp_path, [p])
    req['inputs'][0]['sha256'] = '0'*64
    with pytest.raises(ValueError, match='checksum'):
        run_job(req, tmp_path)
    req['inputs'][0]['path'] = '../one.fits'
    with pytest.raises(ValueError, match='path'):
        run_job(req, tmp_path)
    req = request_for(tmp_path, [p]); req['grid']['width'] = 513
    with pytest.raises(ValueError):
        run_job(req, tmp_path)


def test_bundle_rejects_pickle_and_unbounded_arrays(tmp_path):
    from unification.ml import load_bundle
    p = tmp_path / 'source.fits'
    fits.writeto(p, np.ones((32, 32)), wcs_header())
    result, _ = run_bundle(tmp_path, request_for(tmp_path, [p]))
    original = tmp_path / result['bundle']['path']
    with zipfile.ZipFile(original) as z:
        members = {name: z.read(name) for name in z.namelist()}
    bad = tmp_path / 'bad.npz'
    out = io.BytesIO(); np.save(out, np.array([object()], dtype=object))
    members['images.npy'] = out.getvalue()
    with zipfile.ZipFile(bad, 'w') as z:
        for name, value in members.items():
            z.writestr(name, value)
    with pytest.raises(ValueError, match='unsafe'):
        load_bundle(bad)
    # Preserve all expected members so this exercises NPY-size validation.
    out = io.BytesIO()
    np.lib.format.write_array_header_1_0(out, dict(descr='<f8', fortran_order=False, shape=(2**35,)))
    members['images.npy'] = out.getvalue()
    with zipfile.ZipFile(bad, 'w') as z:
        for name, value in members.items():
            z.writestr(name, value)
    with pytest.raises(ValueError, match='declared array size'):
        load_bundle(bad)


def temporal_sources(tmp_path, *, band='r', instrument='Camera-A', unit='Jy'):
    sources = []
    for i in range(3):
        p = tmp_path / f'temporal-{i}.fits'
        h = wcs_header(); h['DATE-OBS'] = f'2026-01-01T0{i}:00:00'
        h['FILTER'] = band; h['BUNIT'] = unit; h['INSTRUME'] = instrument; h['TELESCOP'] = 'Test observatory'
        fits.writeto(p, np.ones((32, 32)), h)
        sources.append(p)
    return sources


def test_motion_rejects_unknown_observation_identity(tmp_path):
    req = request_for(tmp_path, temporal_sources(tmp_path))
    _, bundle = run_bundle(tmp_path, req)
    with pytest.raises(ValueError, match='identit'):
        bundle.motion_inputs()


def test_motion_policy_retains_only_spherex_outliers(tmp_path):
    p = tmp_path / 'flags.fits'
    flags = np.zeros((32, 32), dtype=np.int32)
    flags[10, 10] = 1 << 19
    flags[12, 12] = 1 << 26
    flags[14, 14] = 1 << 21
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.ones((32, 32)), wcs_header(), name='IMAGE'),
                  fits.ImageHDU(flags, name='FLAGS')]).writeto(p)
    req = request_for(tmp_path, [p]); req['inputs'][0]['profile'] = 'spherex'
    _, science = run_bundle(tmp_path, req)
    assert not science.valid_mask[0, 10, 10]
    req = request_for(tmp_path, [p]); req['inputs'][0]['profile'] = 'spherex'; req['options']['mask_policy'] = 'motion'
    _, motion = run_bundle(tmp_path, req)
    assert motion.valid_mask[0, 10, 10] and motion.outlier[0, 10, 10]
    assert not motion.valid_mask[0, 12, 12] and motion.bloom[0, 12, 12]
    assert motion.valid_mask[0, 14, 14]


def test_mjd_average_and_start_without_duration(tmp_path):
    p = tmp_path / 'midpoint.fits'
    h = wcs_header(); del h['DATE-OBS']; del h['EXPTIME']; h['MJD-AVG'] = 61041.0
    fits.writeto(p, np.ones((32, 32)), h)
    _, b = run_bundle(tmp_path, request_for(tmp_path, [p]))
    assert b.time_known_mask.all()
    h = wcs_header(); del h['EXPTIME']
    fits.writeto(p, np.ones((32, 32)), h, overwrite=True)
    _, b = run_bundle(tmp_path, request_for(tmp_path, [p]))
    assert not b.time_known_mask.any()


def test_different_passbands_and_adu_do_not_qualify_motion(tmp_path):
    req = request_for(tmp_path, temporal_sources(tmp_path))
    for i, spec in enumerate(req['inputs']):
        spec['metadata'] = dict(provider='test', observation_id=f'observation-{i}')
    _, bundle = run_bundle(tmp_path, req)
    bundle.metadata['frames'][1]['band'] = 'g'
    with pytest.raises(ValueError, match='passband'):
        bundle.motion_inputs()
    for frame in bundle.metadata['frames']:
        frame['band'] = 'r'; frame['unit'] = 'ADU'
    with pytest.raises(ValueError, match='physical units'):
        bundle.motion_inputs()


def test_symlink_input_and_output_rejected(tmp_path):
    from unification.worker import run_job
    p = tmp_path / 'outside.fits'; fits.writeto(p, np.ones((32, 32)), wcs_header())
    req = request_for(tmp_path, [p]); snapshot = tmp_path / req['inputs'][0]['path']
    snapshot.unlink(); snapshot.symlink_to(p)
    with pytest.raises(ValueError, match='symlink'):
        run_job(req, tmp_path)
    req = request_for(tmp_path, [p]); out = tmp_path / 'unifications' / req['job_id'] / 'output'
    out.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        run_job(req, tmp_path)


def test_bundle_manifest_and_frame_vectors_must_agree(tmp_path):
    from unification.ml import load_bundle
    p = tmp_path / 'valid.fits'; fits.writeto(p, np.ones((32, 32)), wcs_header())
    result, _ = run_bundle(tmp_path, request_for(tmp_path, [p]))
    artifact = tmp_path / result['bundle']['path']
    with np.load(artifact, allow_pickle=False) as z:
        arrays = {name: z[name] for name in z.files}
    arrays['frame_ids'] = np.array(['forged'])
    np.savez(artifact, **arrays)
    with pytest.raises(ValueError, match='identit'):
        load_bundle(artifact)


def test_motion_rejects_unknown_instrument_context(tmp_path):
    req = request_for(tmp_path, temporal_sources(tmp_path))
    for i, spec in enumerate(req['inputs']):
        spec['metadata'] = dict(provider='test', observation_id=f'observation-{i}')
    _, b = run_bundle(tmp_path, req)
    for frame in b.metadata['frames']:
        frame['instrument'] = None
    with pytest.raises(ValueError, match='instrument'):
        b.motion_inputs()


def test_sip_distortion_sky_registration(tmp_path):
    from astropy.wcs import Sip
    size = 32
    w = WCS(wcs_header(size))
    a = np.zeros((3, 3)); b = a.copy(); a[2, 0] = 0.002; b[0, 2] = -0.001
    w.sip = Sip(a, b, None, None, w.wcs.crpix)
    w.wcs.ctype = ['RA---TAN-SIP', 'DEC--TAN-SIP']
    h = wcs_header(size); h.update(w.to_header(relax=True))
    yy, xx = np.mgrid[:size, :size]
    sky = w.pixel_to_world(xx, yy)
    tx, ty = WCS(wcs_header(size)).world_to_pixel(sky)
    p = tmp_path / 'sip.fits'; fits.writeto(p, 2*tx+3*ty, h)
    _, bundle = run_bundle(tmp_path, request_for(tmp_path, [p]))
    np.testing.assert_allclose(bundle.images[0, 4:-4, 4:-4], (2*xx+3*yy)[4:-4, 4:-4], atol=0.008)


def test_all_auxiliary_decoding_has_aggregate_byte_limit(tmp_path, monkeypatch):
    import unification.readers as readers
    from unification.worker import run_job
    p = tmp_path / 'sum.fits'
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.ones((64, 64), dtype=np.int16), wcs_header(64), name='SCI'),
                  fits.ImageHDU(np.ones((64, 64), dtype=np.int16), name='VARIANCE')]).writeto(p)
    monkeypatch.setattr(readers, 'MAX_INPUT', 50000)
    with pytest.raises(ValueError, match='decoded'):
        run_job(request_for(tmp_path, [p]), tmp_path)


def test_gzip_expanded_limit_and_source_side_limit(tmp_path, monkeypatch):
    import unification.readers as readers
    from unification.worker import run_job
    p = tmp_path / 'gzip.fits.gz'
    fits.writeto(p, np.zeros((128, 128)), wcs_header(128))
    req = request_for(tmp_path, [p]); monkeypatch.setattr(readers, 'MAX_INPUT', 10000)
    with pytest.raises(ValueError, match='expanded'):
        run_job(req, tmp_path)
    monkeypatch.setattr(readers, 'MAX_INPUT', 256*1024**2)
    p = tmp_path / 'wide.fits'; fits.writeto(p, np.zeros((2, 4097), dtype=np.int16))
    with pytest.raises(ValueError, match='decoded'):
        run_job(request_for(tmp_path, [p]), tmp_path)


def test_identity_grid_pixels_have_no_mask_hole_variance_leak(tmp_path):
    p = tmp_path / 'masked.fits'
    values = np.ones((32, 32)); values[11, 13] = 1e9
    mask = np.zeros((32, 32), dtype=np.uint8); mask[11, 13] = 1
    fits.HDUList([fits.PrimaryHDU(values, wcs_header()), fits.ImageHDU(mask, name='MASK')]).writeto(p)
    _, bundle = run_bundle(tmp_path, request_for(tmp_path, [p]))
    assert np.isnan(bundle.images[0, 11, 13])
    assert bundle.tensor[0, 11, 13] == 0
    np.testing.assert_allclose(bundle.images[bundle.valid_mask], 1)


@pytest.mark.parametrize('invalid', [-1., 0., np.nan])
def test_present_invalid_variance_masks_science(tmp_path, invalid):
    p = tmp_path / 'invalid-variance.fits'
    variance = np.ones((32, 32)); variance[10, 12] = invalid
    fits.HDUList([fits.PrimaryHDU(np.ones((32, 32)), wcs_header()), fits.ImageHDU(variance, name='VARIANCE')]).writeto(p)
    _, b = run_bundle(tmp_path, request_for(tmp_path, [p]))
    assert not b.valid_mask[0, 10, 12]
    assert np.isnan(b.images[0, 10, 12])


def test_uncertainty_unit_conversion_and_incompatible_units(tmp_path):
    from unification.worker import run_job
    p = tmp_path / 'variance-unit.fits'
    v = fits.ImageHDU(np.full((32, 32), 4e6), name='VARIANCE'); v.header['BUNIT'] = 'mJy2'
    fits.HDUList([fits.PrimaryHDU(np.full((32, 32), 2.), wcs_header()), v]).writeto(p)
    _, b = run_bundle(tmp_path, request_for(tmp_path, [p]))
    np.testing.assert_allclose(b.variance, 4.)
    v.header['BUNIT'] = 's2'
    fits.HDUList([fits.PrimaryHDU(np.full((32, 32), 2.), wcs_header()), v]).writeto(p, overwrite=True)
    with pytest.raises(ValueError, match='uncertainty unit'):
        run_job(request_for(tmp_path, [p]), tmp_path)


def test_missing_variance_unit_assumption_recorded(tmp_path):
    p = tmp_path / 'assumed.fits'
    fits.HDUList([fits.PrimaryHDU(np.ones((32, 32)), wcs_header()),
                  fits.ImageHDU(np.ones((32, 32)), name='VARIANCE')]).writeto(p)
    _, b = run_bundle(tmp_path, request_for(tmp_path, [p]))
    assert 'assumed' in b.metadata['frames'][0]['uncertainty_unit_semantics']


def test_partial_bilinear_support_does_not_fill_bad_pixels(tmp_path):
    p = tmp_path / 'support.fits'
    mask = np.zeros((32, 32), dtype=np.uint8); mask[10, 10] = 1
    fits.HDUList([fits.PrimaryHDU(np.ones((32, 32)), wcs_header(offset=(.5, .5))),
                  fits.ImageHDU(mask, name='MASK')]).writeto(p)
    _, b = run_bundle(tmp_path, request_for(tmp_path, [p]))
    assert .7 < b.footprint[0, 10, 10] < .8
    assert not b.valid_mask[0, 10, 10]
    assert np.isnan(b.images[0, 10, 10])


def test_contradictory_explicit_midpoints_stay_unknown(tmp_path):
    p = tmp_path / 'contradictory.fits'; h = wcs_header()
    h['MJD-AVG'] = 61041.; h['DATE-AVG'] = '2026-01-01T04:00:00'
    fits.writeto(p, np.ones((32, 32)), h)
    _, b = run_bundle(tmp_path, request_for(tmp_path, [p]))
    assert not b.time_known_mask.any()
    assert b.metadata['frames'][0]['source_time']['MJD-AVG'] == 61041.


def test_large_nonzero_generic_dq_never_wraps_to_valid(tmp_path):
    p = tmp_path / 'large-dq.fits'
    dq = np.zeros((32, 32), dtype=np.uint64); dq[12, 10] = 2**64-1
    fits.HDUList([fits.PrimaryHDU(np.ones((32, 32)), wcs_header()), fits.ImageHDU(dq, name='DQ')]).writeto(p)
    _, b = run_bundle(tmp_path, request_for(tmp_path, [p]))
    assert not b.valid_mask[0, 12, 10]


def test_too_many_fits_extensions_rejected_before_data(tmp_path):
    from unification.worker import run_job
    p = tmp_path / 'too-many-hdus.fits'
    fits.HDUList([fits.PrimaryHDU(np.ones((32, 32)), wcs_header())] + [fits.ImageHDU() for _ in range(1025)]).writeto(p)
    with pytest.raises(ValueError, match='HDU'):
        run_job(request_for(tmp_path, [p]), tmp_path)


def test_manifest_staging_file_cannot_truncate_an_existing_hardlink(tmp_path):
    import os
    from unification.worker import run_job
    p = tmp_path / 'source.fits'; fits.writeto(p, np.ones((32, 32)), wcs_header())
    req = request_for(tmp_path, [p])
    output = tmp_path / 'unifications' / req['job_id'] / 'output'; output.mkdir()
    sentinel = tmp_path / 'sentinel'; sentinel.write_bytes(b'keep original')
    os.link(sentinel, output / 'manifest.json.partial')
    with pytest.raises(ValueError):
        run_job(req, tmp_path)
    assert sentinel.read_bytes() == b'keep original'


def test_full_advertised_geometry_fits_versioned_bundle_limits(tmp_path):
    source = tmp_path / 'maximum.fits'
    fits.writeto(source, np.ones((512, 512), dtype=np.float32), wcs_header(size=512))
    request = request_for(tmp_path, [source] * 32,
        grid=dict(kind='sky', ra_degrees=20, dec_degrees=30, width=512, height=512, pixel_scale_arcsec=1))
    result, bundle = run_bundle(tmp_path, request)
    assert bundle.images.shape == (32, 512, 512)
    assert bundle.valid_mask.all()
    assert result['frame_count'] == 32


def test_output_writer_bounds_peak_bytes_before_writing(tmp_path):
    from unification.worker import BoundedWriter
    path = tmp_path / 'bounded.npz'
    with path.open('wb') as raw:
        writer = BoundedWriter(raw, 8)
        assert writer.write(b'1234567') == 7
        with pytest.raises(ValueError, match='limit'):
            writer.write(b'89')
        writer.flush()
        assert path.stat().st_size == 7
        writer.seek(0)
        writer.write(b'header')
        with pytest.raises(ValueError, match='limit'):
            writer.seek(9)
    assert path.stat().st_size <= 8


def test_selected_cube_plane_requires_celestial_axes_to_match_its_pixels(tmp_path):
    # The selected leading axis is RA, so the remaining plane is frequency x DEC.
    # It cannot be registered as a two-dimensional sky image.
    w = WCS(naxis=3)
    w.wcs.ctype = ['FREQ', 'DEC--TAN', 'RA---TAN']
    w.wcs.crval = [1e9, 30, 20]
    w.wcs.crpix = [16.5, 16.5, 1]
    w.wcs.cdelt = [1e6, 1/3600, -1/3600]
    source = tmp_path / 'non-spatial-plane.fits'
    fits.writeto(source, np.ones((2, 32, 32)), w.to_header())
    request = request_for(tmp_path, [source])
    request['inputs'][0]['plane_indices'] = [0]
    with pytest.raises(ValueError, match='WCS|celestial|sky'):
        run_bundle(tmp_path, request)
    # Explicit pixel mode remains usable, without inventing a sky registration.
    request = request_for(tmp_path, [source], grid=dict(kind='pixel', width=32, height=32))
    request['inputs'][0]['plane_indices'] = [0]
    _, bundle = run_bundle(tmp_path, request)
    assert bundle.metadata['frames'][0]['source_wcs'] is None
