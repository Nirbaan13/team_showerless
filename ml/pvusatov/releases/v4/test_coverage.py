"""A missing footprint must not erase covered epochs or their identities."""
import importlib
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from ml.pvusatov.releases.v4.test_runtime import package, RUNTIME, ORIGINAL, RELEASE


def observation(path, index, *, empty=None):
    grid = WCS(naxis=2); grid.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    grid.wcs.crval = [20. if empty != 'footprint' else 30., 5.]
    grid.wcs.crpix = [16.5, 16.5]; grid.wcs.cdelt = [-6.15/3600, 6.15/3600]
    header = grid.to_header(); header['MJD-AVG'] = 61000 + index/24
    header['DATE-AVG'] = Time(header['MJD-AVG'], format='mjd').isot
    header['DETECTOR'] = 1; header['BUNIT'] = 'MJy/sr'; header['OBSID'] = 'coverage-' + str(index)
    image = np.random.default_rng(3800700 + index).normal(size=(32, 32)).astype(np.float32)
    flags = np.full((32, 32), 1 if empty == 'flags' else 0, dtype=np.int32)
    hdus = [fits.PrimaryHDU()] + [fits.ImageHDU(value, header=header, name=name) for name, value in
        [('IMAGE', image), ('FLAGS', flags), ('VARIANCE', np.ones_like(image)), ('ZODI', np.zeros_like(image))]]
    fits.HDUList(hdus).writeto(path)
    return dict(frame_id=path.stem, observation_id='manifest-' + str(index), path=str(path))


def request(rows, **options):
    return dict(schema_version=1, analysis_id='coverage-preserved',
                source=dict(kind='fits', observations=rows, region=dict(right_ascension_deg=20., declination_deg=5.,
                            width_arcmin=2., height_arcmin=2.)), options=options)


@pytest.mark.parametrize('empty', ['flags', 'footprint'])
def test_empty_epoch_is_retained_with_original_date_id_and_mask(tmp_path, empty):
    pipeline = package(); rows = [observation(tmp_path/f'{i}.fits', i, empty=empty if i == 1 else None) for i in range(4)]
    stack = pipeline.prepare(request(rows))
    assert len(stack.frames) == 4 and np.isnan(stack.images[1]).all()
    assert [frame['frame_id'] for frame in stack.frames] == ['0', '1', '2', '3']
    assert [frame['physical_observation_id'] for frame in stack.frames] == ['coverage-' + str(i) for i in range(4)]
    assert np.allclose(stack.times, [0., 1., 2., 3.], atol=1e-8)
    assert all(np.isfinite(stack.images[i]).any() for i in (0, 2, 3))
    assert 'observations_without_usable_requested_coverage' in stack.warnings


@pytest.mark.parametrize('usable', [0, 1, 2])
def test_fewer_than_requested_usable_epochs_remains_a_failure(tmp_path, usable):
    pipeline = package(); rows = [observation(tmp_path/f'{i}.fits', i, empty='flags' if i >= usable else None) for i in range(4)]
    with pytest.raises(pipeline.InferenceError, match='usable') as error:
        pipeline.prepare(request(rows))
    assert error.value.code == 'insufficient_observations'


def test_missing_science_hdu_is_not_reinterpreted_as_empty_coverage(tmp_path):
    pipeline = package(); rows = [observation(tmp_path/f'{i}.fits', i) for i in range(4)]
    with fits.open(rows[1]['path']) as hdus:
        retained = fits.HDUList([hdu.copy() for hdu in hdus if hdu.name != 'VARIANCE'])
    retained.writeto(rows[1]['path'], overwrite=True)
    with pytest.raises(pipeline.InferenceError) as error:
        pipeline.prepare(request(rows))
    assert error.value.code == 'invalid_fits'


def test_covered_data_are_bitwise_identical_to_original_preparation(tmp_path):
    name = 'coverage_legacy_reference'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ORIGINAL/'ml_inference/__init__.py',
                     submodule_search_locations=[str(ORIGINAL/'ml_inference')])
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    legacy = importlib.import_module(name + '.prepare')
    rows = [observation(tmp_path/f'{i}.fits', i) for i in range(4)]
    original = legacy.prepare(request(rows)); amended = package().prepare(request(rows))
    for key in ('images', 'times', 'outlier', 'bloom'):
        assert getattr(original, key).tobytes() == getattr(amended, key).tobytes()
    assert original.frames == amended.frames and original.warnings == amended.warnings
    assert original.provenance == amended.provenance


def test_actual_selected_pipeline_publishes_explicit_zero_coverage_frame(tmp_path):
    from PIL import Image
    pipeline = package(); rows = [observation(tmp_path/f'{i}.fits', i, empty='flags' if i == 1 else None) for i in range(4)]
    req = request(rows); req['model_dir'] = str(RELEASE/'model'); output = tmp_path/'output'
    result = pipeline.run(req, output)
    assert result['frames'][1]['coverage_fraction'] == 0.
    assert len(result['frames']) == 4 and result['model']['sha256'].startswith('c596f66f')
    with Image.open(output/result['frames'][1]['image_url']) as image:
        assert not np.asarray(image).any()
