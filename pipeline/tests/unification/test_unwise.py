"""Instrument-adapter contracts using small analytic FITS fixtures, not acceptance data."""
import hashlib
import json
import shutil
import uuid
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS


def source_files(tmp_path, epoch=0, start=55319.):
    tmp_path.mkdir(parents=True, exist_ok=True)
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    wcs.wcs.crval = [134.2, -7.6]
    wcs.wcs.crpix = [8.5, 8.5]
    wcs.wcs.cdelt = [-2.75 / 3600, 2.75 / 3600]
    header = wcs.to_header()
    for key, value in dict(EPOCH=epoch, BAND=2, MAGZP=22.5, UNW_DVER='3.3',
                           MJDMIN=start, MJDMAX=start+3).items():
        header[key] = value
    science = tmp_path / 'science.fits'
    fits.writeto(science, np.full((16, 16), 10, np.float32), header)
    auxiliaries = {}
    for name, value in [('inverse_variance', 4.), ('coverage', 2.)]:
        path = tmp_path / (name + '.fits.gz')
        fits.writeto(path, np.full((16, 16), value, np.float32), header)
        auxiliaries[name] = path
    path = tmp_path / 'contributors.fits'
    fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns([
        fits.Column(name='mjd', format='D', array=[start, start+3]),
        fits.Column(name='band', format='I', array=[2, 2]),
        fits.Column(name='included', format='L', array=[True, True]),
    ])]).writeto(path)
    auxiliaries['contributors'] = path
    descriptors = {name: dict(id=name, path=str(path), bytes=path.stat().st_size,
                              sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                   for name, path in auxiliaries.items()}
    spec = dict(id='science', profile='unwise', image_hdu=0, plane_indices=[],
                auxiliaries=descriptors, metadata=dict(provider='unwise-neo11',
                    native=dict(coadd_id='1342m076', epoch=str(epoch), band='2', release='neo11')))
    return science, spec, auxiliaries


def test_native_unwise_calibration_variance_and_real_times(tmp_path):
    from pipeline.unification.unwise import read_unwise_frame
    science, spec, auxiliaries = source_files(tmp_path)
    frame = read_unwise_frame(science, spec, auxiliaries)
    np.testing.assert_allclose(frame.image, 10 * .171787)
    np.testing.assert_allclose(frame.variance, .171787**2 / 4)
    assert frame.metadata['unit'] == 'uJy'
    assert frame.metadata['source_time']['MJDMIN'] == 55319.
    assert frame.metadata['source_time']['MJDMAX'] == 55322.
    assert frame.metadata['midpoint_utc'].startswith('2010-05-04T12:00:00')
    assert frame.metadata['outlier_known'] is frame.metadata['bloom_known'] is False
    q = frame.metadata['historical_motion_qualification']
    assert q['status'] == 'qualified_native_product' and q['band'] == 'W2'
    assert q['auxiliary_sources']['inverse_variance']['sha256'] == spec['auxiliaries']['inverse_variance']['sha256']
    assert q['psf']['homogenized'] is False


def test_coverage_and_inverse_variance_define_invalid_pixels(tmp_path):
    from pipeline.unification.unwise import read_unwise_frame
    science, spec, auxiliaries = source_files(tmp_path)
    for name, pixel in [('inverse_variance', (2, 3)), ('coverage', (4, 5))]:
        path = auxiliaries[name]
        with fits.open(path) as f:
            data, header = f[0].data.copy(), f[0].header.copy()
        data[pixel] = 0
        fits.writeto(path, data, header, overwrite=True)
    frame = read_unwise_frame(science, spec, auxiliaries)
    for pixel in [(2, 3), (4, 5)]:
        assert not frame.valid[pixel] and np.isnan(frame.image[pixel]) and np.isnan(frame.variance[pixel])
    assert np.array_equal(frame.valid, frame.variance_valid)


@pytest.mark.parametrize('key,value', [('BAND', 1), ('EPOCH', 2), ('MAGZP', 21.),
                                      ('MJDMAX', 55300.), ('UNW_DVER', 'unknown')])
def test_incompatible_native_headers_are_rejected(tmp_path, key, value):
    from pipeline.unification.unwise import read_unwise_frame
    science, spec, auxiliaries = source_files(tmp_path)
    with fits.open(science, mode='update') as f:
        f[0].header[key] = value
    with pytest.raises(ValueError):
        read_unwise_frame(science, spec, auxiliaries)


def test_auxiliary_epoch_and_grid_must_match_science(tmp_path):
    from pipeline.unification.unwise import read_unwise_frame
    science, spec, auxiliaries = source_files(tmp_path)
    path = auxiliaries['inverse_variance']
    with fits.open(path) as f:
        data, header = f[0].data.copy(), f[0].header.copy()
    header['CRVAL1'] += .01
    fits.writeto(path, data, header, overwrite=True)
    with pytest.raises(ValueError):
        read_unwise_frame(science, spec, auxiliaries)


def test_all_related_products_are_required(tmp_path):
    from pipeline.unification.unwise import read_unwise_frame
    science, spec, auxiliaries = source_files(tmp_path)
    auxiliaries.pop('coverage')
    with pytest.raises(ValueError):
        read_unwise_frame(science, spec, auxiliaries)


def test_early_product_band_is_qualified_without_inserting_header(tmp_path):
    from pipeline.unification.unwise import read_unwise_frame
    science, spec, auxiliaries = source_files(tmp_path)
    for path in [science, auxiliaries['inverse_variance'], auxiliaries['coverage']]:
        with fits.open(path) as f:
            data, header = f[0].data.copy(), f[0].header.copy()
        del header['BAND']
        header['REFEREN1'] = '/author/neo2_ref_w2'
        fits.writeto(path, data, header, overwrite=True)
    frame = read_unwise_frame(science, spec, auxiliaries)
    assert frame.metadata['band'] == 'W2'
    assert 'REFEREN1' in frame.metadata['historical_motion_qualification']['band_identity_source']
    with fits.open(science) as f:
        assert 'BAND' not in f[0].header


def test_conflicting_native_band_and_filter_are_rejected(tmp_path):
    from pipeline.unification.unwise import read_unwise_frame
    science, spec, auxiliaries = source_files(tmp_path)
    with fits.open(science, mode='update') as f:
        f[0].header['FILTER'] = 'W1'
    with pytest.raises(ValueError):
        read_unwise_frame(science, spec, auxiliaries)


def prepared_request(tmp_path):
    job = str(uuid.uuid4())
    directory = tmp_path / 'unifications' / job / 'inputs'
    directory.mkdir(parents=True)
    inputs = []
    for epoch, start in [(0, 55319.), (1, 55510.), (22, 60414.)]:
        source, spec, auxiliary = source_files(tmp_path / f'raw-{epoch}', epoch, start)
        def snapshot(path, role):
            destination = directory / f'{epoch}-{role}.fits'
            shutil.copyfile(path, destination)
            return dict(id=f'{epoch}-{role}', path=str(destination.relative_to(tmp_path)),
                        bytes=destination.stat().st_size,
                        sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
        primary = snapshot(source, 'science')
        spec.update(id=primary['id'], path=primary['path'], sha256=primary['sha256'])
        spec['metadata']['observation_id'] = f'neo11:1342m076:W2:e{epoch:03d}'
        spec['auxiliaries'] = {role: snapshot(path, role) for role, path in auxiliary.items()}
        inputs.append(spec)
    return dict(schema_version=1, job_id=job, inputs=inputs,
                grid=dict(kind='sky', width=16, height=16, ra_degrees=134.2,
                          dec_degrees=-7.6, pixel_scale_arcsec=2.75),
                options=dict(normalization='none', mask_policy='science'))


def test_managed_snapshot_roundtrip_qualifies_existing_ivan_adapter(tmp_path):
    from pipeline.unification.worker import run_job
    from pipeline.unification.ml import load_bundle
    from science.motion.prepared import prepare_motion_payload
    request = prepared_request(tmp_path)
    result = run_job(request, tmp_path)
    bundle = load_bundle(tmp_path / result['bundle']['path'])
    payload, provenance = prepare_motion_payload(bundle, request['job_id'])
    assert len(payload['images']) == 3
    assert payload['outlier'] is None
    assert payload['times'][-1] > 120000  # True hours across the historical interval.
    assert bundle.metadata['frames'][0]['analysis_eligible'] is False
    assert bundle.metadata['frames'][0]['auxiliary_assets'] == {
        name: {k: ref[k] for k in ('id', 'sha256', 'bytes')}
        for name, ref in request['inputs'][0]['auxiliaries'].items()}


def test_corrupt_related_snapshot_is_rejected_before_output(tmp_path):
    from pipeline.unification.worker import run_job
    request = prepared_request(tmp_path)
    request['inputs'][0]['auxiliaries']['coverage']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='checksum'):
        run_job(request, tmp_path)
    assert not (tmp_path / 'unifications' / request['job_id'] / 'output' / 'dataset.npz').exists()


def test_related_paths_cannot_escape_the_managed_job(tmp_path):
    from pipeline.unification.worker import validate_request
    request = prepared_request(tmp_path)
    request['inputs'][0]['auxiliaries']['coverage']['path'] = '/etc/passwd'
    with pytest.raises(ValueError, match='snapshot path'):
        validate_request(request)


def test_contributors_selects_exposure_table_with_extra_astrometric_hdus(tmp_path):
    from pipeline.unification.unwise import read_unwise_frame
    science, spec, auxiliaries = source_files(tmp_path)
    path = auxiliaries['contributors']
    with fits.open(path) as f:
        exposure = f[1].copy()
    calibration = fits.BinTableHDU.from_columns([fits.Column(name='coeff', format='D', array=[0.])])
    summary = fits.BinTableHDU.from_columns([fits.Column(name='n_attempted', format='K', array=[])])
    fits.HDUList([fits.PrimaryHDU(), exposure, calibration, summary]).writeto(path, overwrite=True)
    frame = read_unwise_frame(science, spec, auxiliaries)
    assert frame.metadata['historical_motion_qualification']['contributor_summary']['included'] == 2


def test_native_contributor_included_bytes_are_not_boolean_pixel_masks(tmp_path):
    from pipeline.unification.unwise import read_unwise_frame
    science, spec, auxiliaries = source_files(tmp_path)
    path = auxiliaries['contributors']
    table = fits.BinTableHDU.from_columns([
        fits.Column(name='mjd', format='D', array=[55319., 55322., 56000.]),
        fits.Column(name='band', format='I', array=[2, 2, 2]),
        fits.Column(name='included', format='B', array=[2, 30, 0]),
    ])
    fits.HDUList([fits.PrimaryHDU(), table]).writeto(path, overwrite=True)
    frame = read_unwise_frame(science, spec, auxiliaries)
    summary = frame.metadata['historical_motion_qualification']['contributor_summary']
    assert summary['included'] == 2 and summary['rows'] == 3


@pytest.mark.parametrize('cards', [{'RADESYS': 'FK4', 'EQUINOX': 1950.}, {'LONPOLE': 0.}])
def test_auxiliary_complete_celestial_mapping_must_match(tmp_path, cards):
    from pipeline.unification.unwise import read_unwise_frame
    science, spec, auxiliaries = source_files(tmp_path)
    path = auxiliaries['inverse_variance']
    with fits.open(path) as f:
        data, header = f[0].data.copy(), f[0].header.copy()
    for key, value in cards.items():
        header[key] = value
    fits.writeto(path, data, header, overwrite=True)
    with pytest.raises(ValueError, match='WCS'):
        read_unwise_frame(science, spec, auxiliaries)
