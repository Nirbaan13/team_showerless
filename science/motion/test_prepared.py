"""Prepared transport unit fixtures are analytic and are not discovery evidence."""

import json

import numpy as np
import pytest

from pipeline.unification.ml import Bundle
from pipeline.unification.resampling import target_wcs

JOB = 'c1c9e87b-964a-40aa-91cd-28e4d194b46a'


def qualified_bundle():
    images = np.random.default_rng(6).normal(20, 0.3, (3, 24, 24)).astype(np.float32)
    dates = np.array(['2010-01-01T00:00:00', '2011-01-01T00:00:00', '2012-01-01T00:00:00'])
    frames = []
    for index, (mjd, date) in enumerate(zip([55197., 55562., 55927.], dates)):
        identity = f'unwise-neo11:neo11:1342m076:W2:e{index:03d}'
        q = dict(status='qualified_native_product', release='neo11', band='W2', tile='1342m076', epoch=index,
                 native_pixel_scale_arcsec=2.75,
                 flux_conversion=dict(input_unit='Vega nanomaggy', magzp=22.5, zero_flux_jy=171.787, to_uJy=0.171787),
                 time=dict(method='midpoint of MJDMIN/MJDMAX visit interval', scale='utc',
                           start_mjd=mjd - 1, end_mjd=mjd + 1),
                 auxiliary_sources={name: dict(id=f'{name}-{index}', sha256=str(index + 1) * 64, bytes=123)
                                    for name in ('inverse_variance', 'coverage', 'contributors')},
                 artifact_mask_available=False, psf=dict(nominal_fwhm_arcsec=6.4, homogenized=False),
                 limitations=['Visit coadds; unknown artifact mask; no PSF homogenization.'])
        frames.append(dict(frame_id=f'frame-{index}', observation_identity=identity, midpoint_utc=str(date),
                           profile='unwise', unit='uJy', mission='WISE/NEOWISE', instrument='WISE', band='W2',
                           wavelength_min=None, wavelength_max=None, wavelength_unit=None,
                           outlier_known=False, bloom_known=False, analysis_eligible=False,
                           source_sha256='a' * 64, provenance=dict(provider='unwise-neo11'),
                           historical_motion_qualification=q))
    valid = np.ones_like(images, dtype=bool)
    grid = dict(kind='sky', width=24, height=24, ra_degrees=134., dec_degrees=-7.6,
                pixel_scale_arcsec=2.75)
    return Bundle(images=images, tensor=images.copy(), valid_mask=valid, footprint=np.ones_like(images),
                  variance=np.full_like(images, 0.09), variance_valid_mask=valid.copy(),
                  outlier=np.zeros_like(valid), bloom=np.zeros_like(valid),
                  times=np.array([0., 8760., 17520.]), time_known_mask=np.ones(3, dtype=bool),
                  frame_ids=np.array([f['frame_id'] for f in frames]),
                  observation_ids=np.array([f['observation_identity'] for f in frames]), dates_utc=dates,
                  metadata=dict(schema_version=1, job_id=JOB, frames=frames,
                                grid=grid, target_wcs=target_wcs(grid).to_header().tostring(sep='\n'),
                                time_unit='hours from first known real exposure midpoint',
                                resampling=dict(covariance='not represented', flux_conserving=False,
                                                variance='sum(squared normalized weights * independent input variance)'),
                                warnings=['Registration does not grant production analysis eligibility.']))


def write_bundle(path, bundle):
    arrays = {key: value for key, value in vars(bundle).items() if key != 'metadata'}
    arrays['manifest'] = np.frombuffer(json.dumps(bundle.metadata).encode(), dtype=np.uint8)
    arrays['schema_version'] = np.array(1, dtype=np.int16)
    np.savez_compressed(path, **arrays)
    return path


def test_prepared_adapter_subtracts_only_background_and_preserves_true_hours_and_unknown_masks():
    from science.motion.prepared import prepare_motion_payload

    bundle = qualified_bundle()
    original = bundle.images.copy()
    payload, provenance = prepare_motion_payload(bundle, JOB)
    offsets = np.median(original, axis=(1, 2))
    np.testing.assert_allclose(payload['images'], original.astype(float) - offsets[:, None, None], atol=2e-6)
    np.testing.assert_array_equal(bundle.images, original)
    np.testing.assert_array_equal(payload['times'], [0., 8760., 17520.])
    assert payload['outlier'] is None and payload['bloom'] is None
    assert 'expected_xy' not in payload
    assert payload['retain_outliers'] is False
    assert provenance['background_subtraction']['method'] == 'per-frame median of valid physical pixels'
    assert provenance['background_subtraction']['offsets_uJy'] == pytest.approx(offsets.tolist())
    assert provenance['frames'] == bundle.metadata['frames']


@pytest.mark.parametrize('change', [
    lambda b: b.metadata.update(job_id='f97f0b5d-c817-45ab-8a39-af26afad4035'),
    lambda b: b.metadata['grid'].update(kind='pixel'),
    lambda b: b.metadata['grid'].update(pixel_scale_arcsec=6.15),
    lambda b: b.metadata['frames'][0].update(profile='generic'),
    lambda b: b.metadata['frames'][0].update(unit='adu'),
    lambda b: b.metadata['frames'][0].update(band='W1'),
    lambda b: b.metadata['frames'][0]['provenance'].update(provider='cadc'),
    lambda b: b.metadata['frames'][0].pop('historical_motion_qualification'),
    lambda b: b.metadata['frames'][0]['historical_motion_qualification'].update(tile='other'),
    lambda b: b.metadata['frames'][0]['historical_motion_qualification'].update(release='other'),
    lambda b: b.metadata['frames'][0]['historical_motion_qualification']['flux_conversion'].update(to_uJy=3.631),
    lambda b: b.metadata['frames'][0]['historical_motion_qualification']['time'].update(scale='tai'),
    lambda b: b.metadata['frames'][0]['historical_motion_qualification']['auxiliary_sources'].pop('coverage'),
    lambda b: b.variance_valid_mask.__setitem__((0, 0, 0), False),
    lambda b: b.metadata['frames'][0].update(outlier_known=True),
])
def test_prepared_adapter_rejects_unqualified_physical_contract(change):
    from science.motion.prepared import prepare_motion_payload

    bundle = qualified_bundle()
    change(bundle)
    with pytest.raises(ValueError):
        prepare_motion_payload(bundle, JOB)


def test_prepared_npz_uses_real_loader_and_ivan_review_without_truth_or_training(tmp_path):
    from science.motion.prepared import analyze_prepared

    path = write_bundle(tmp_path / 'test-fixture.npz', qualified_bundle())
    result = analyze_prepared(path, JOB, track_limit=2)
    assert result['id'] == JOB
    assert result['detector'] is None and result['target'] is None
    assert result['has_ephemeris'] is False
    assert result['comparison']['random_forest'] is None
    assert result['comparison']['outliers_masked'] is None
    assert result['search_profile']['proper_motion_arcsec_per_year'] == {'min': 0.1, 'max': 30.0}
    assert result['historical_preparation']['band'] == 'W2'
    assert result['historical_preparation']['psf_homogenized'] is False
    assert [frame['id'] for frame in result['frames']] == qualified_bundle().observation_ids.tolist()
    assert result['frames'][0]['time'] == '2010-01-01T00:00:00Z'
    assert len(result['tracks']) <= 2


@pytest.mark.parametrize('key', ['flux_conversion', 'time', 'auxiliary_sources', 'psf'])
def test_malformed_nested_provenance_is_reported_as_validation_failure(tmp_path, key):
    from science.motion.prepared import analyze_prepared

    bundle = qualified_bundle()
    bundle.metadata['frames'][0]['historical_motion_qualification'][key] = []
    path = write_bundle(tmp_path / 'malformed-fixture.npz', bundle)
    with pytest.raises(ValueError):
        analyze_prepared(path, JOB)


@pytest.mark.parametrize('wcs_header', [None, '', 'COMMENT A FITS header without a celestial projection'])
def test_historical_adapter_requires_actual_celestial_target_wcs(wcs_header):
    from science.motion.prepared import prepare_motion_payload

    bundle = qualified_bundle()
    bundle.metadata['target_wcs'] = wcs_header
    with pytest.raises(ValueError, match='WCS'):
        prepare_motion_payload(bundle, JOB)


def test_prepared_adapter_propagates_exact_registered_wcs():
    from science.motion.prepared import prepare_motion_payload

    bundle = qualified_bundle()
    payload, provenance = prepare_motion_payload(bundle, JOB)
    assert payload['sky_wcs_header'] == bundle.metadata['target_wcs']
    assert provenance['target_wcs'] == bundle.metadata['target_wcs']
