"""Physical SPHEREx exposure identities come from native headers, never filenames."""
import hashlib
import sys
import uuid
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'pipeline'))
from unification.ml import load_bundle
from unification.readers import read_frame
from unification.worker import run_job


def native_request(tmp_path, *, observation='actual-exposure', detector='D1', duplicate=False):
    job = str(uuid.uuid4())
    directory = tmp_path / 'unifications' / job / 'inputs'
    directory.mkdir(parents=True)
    inputs = []
    for i in range(3):
        w = WCS(naxis=2)
        w.wcs.ctype = ['RA---TAN', 'DEC--TAN']
        w.wcs.crval = [20., 30.]
        w.wcs.crpix = [16.5, 16.5]
        w.wcs.cdelt = [-1/3600, 1/3600]
        h = w.to_header()
        h['BUNIT'] = 'MJy/sr'; h['FILTER'] = '1'; h['TELESCOP'] = 'SPHEREx'; h['INSTRUME'] = 'SPHEREx'
        h['DATE-OBS'] = f'2026-01-01T0{i}:00:00'; h['EXPTIME'] = 60.
        if observation is not None:
            h['OBSID'] = observation if duplicate else f'{observation}-{i}'
        if detector is not None:
            h['DETECTOR'] = detector
        path = directory / f'product-version-{i}.fits'
        fits.writeto(path, np.ones((32, 32)), h)
        inputs.append(dict(id=f'arbitrary-product-{i}', path=str(path.relative_to(tmp_path)),
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest(), profile='spherex',
                           image_hdu=None, plane_indices=[],
                           metadata=dict(provider='irsa-spherex', observation_id=None, detector_array=1)))
    return dict(schema_version=1, job_id=job, inputs=inputs,
                grid=dict(kind='sky', ra_degrees=20., dec_degrees=30., width=32, height=32, pixel_scale_arcsec=1.),
                options=dict(normalization='none', mask_policy='science', target_unit=None))


def bundle_for(tmp_path, request):
    result = run_job(request, tmp_path)
    return result, load_bundle(tmp_path / result['bundle']['path'])


@pytest.mark.parametrize('detector', [1, '1', 'D1', 'SPHEREx-D1', None])
def test_native_physical_identity_overrides_product_only_unknowns(tmp_path, detector):
    request = native_request(tmp_path, detector=detector)
    result, bundle = bundle_for(tmp_path, request)
    frame = bundle.metadata['frames'][0]
    assert frame['native_observation_id'] == 'actual-exposure-0'
    assert frame['native_detector'] == (None if detector is None else 1)
    assert frame['observation_identity'] == 'irsa-spherex:actual-exposure-0:D1'
    assert result['detection_ready'] is True
    bundle.motion_inputs()


def test_product_versions_of_same_physical_exposure_are_duplicates(tmp_path):
    request = native_request(tmp_path, duplicate=True)
    result, bundle = bundle_for(tmp_path, request)
    assert len(set(bundle.frame_ids)) == 3
    assert len(set(bundle.observation_ids)) == 1
    assert result['detection_ready'] is False
    with pytest.raises(ValueError, match='duplicate'):
        bundle.motion_inputs()


def test_product_ids_never_supply_unknown_physical_identity(tmp_path):
    result, bundle = bundle_for(tmp_path, native_request(tmp_path, observation=None))
    assert all(f.get('native_observation_id') is None for f in bundle.metadata['frames'])
    assert all(f['observation_identity'] is None for f in bundle.metadata['frames'])
    assert result['detection_ready'] is False
    with pytest.raises(ValueError, match='identit'):
        bundle.motion_inputs()


def test_header_and_trusted_detector_mismatch_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='detector'):
        run_job(native_request(tmp_path, detector='D2'), tmp_path)


def test_header_and_trusted_observation_mismatch_is_rejected(tmp_path):
    request = native_request(tmp_path)
    for i in request['inputs']:
        i['metadata']['observation_id'] = 'different-exposure:D1'
    with pytest.raises(ValueError, match='observation|identity'):
        run_job(request, tmp_path)


def test_conflicting_native_observation_aliases_are_rejected(tmp_path):
    request = native_request(tmp_path)
    path = tmp_path / request['inputs'][0]['path']
    with fits.open(path, mode='update') as hdus:
        hdus[0].header['OBS_ID'] = 'contradictory'
    with pytest.raises(ValueError, match='observation'):
        read_frame(path, request['inputs'][0])


@pytest.mark.parametrize('key,value', [('DET_ID', 'D1'), ('DETID', 'SPHEREx-D1'), ('DETECTOR', '1')])
def test_native_detector_aliases_follow_inference_contract(tmp_path, key, value):
    request = native_request(tmp_path, detector=None)
    path = tmp_path / request['inputs'][0]['path']
    with fits.open(path, mode='update') as hdus:
        hdus[0].header[key] = value
    frame = read_frame(path, request['inputs'][0])
    assert frame.metadata['native_detector'] == 1


def test_invalid_native_detector_is_not_silently_replaced(tmp_path):
    request = native_request(tmp_path, detector='D7')
    with pytest.raises(ValueError, match='detector'):
        read_frame(tmp_path / request['inputs'][0]['path'], request['inputs'][0])
