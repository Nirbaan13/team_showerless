import importlib.util
from pathlib import Path
import numpy as np


def module():
    path = Path(__file__).with_name('probe.py')
    assert path.is_file(), 'density probe not implemented'
    spec = importlib.util.spec_from_file_location('density_probe', path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_all_fixed_paths_are_separated_and_inside_without_wrap():
    probe = module()
    for count in (8, 32, 100):
        paths = probe.source_paths(count)
        assert paths.shape == (count, 32, 2)
        assert np.min(paths) >= 5 and np.max(paths) <= 506
        assert np.allclose(np.diff(paths, axis=1), [1., .2])
        distances = np.linalg.norm(paths[:, None] - paths[None, :], axis=-1)
        distances[np.arange(count), np.arange(count)] = np.inf
        assert distances.min() >= 39.999999


def test_source_stamp_has_fixed_positive_discrete_flux_and_finite_shape():
    probe = module()
    image = np.zeros((512, 512), dtype=np.float32)
    probe.add_source(image, 50.3, 58.8)
    assert np.isfinite(image).all()
    assert np.isclose(image.sum(dtype=float), 50., rtol=1e-7)
    assert image.min() == 0 and image.max() > 0


def test_rejects_unplanned_density():
    import pytest
    with pytest.raises(ValueError, match='predeclared'):
        module().source_paths(9)


def test_dates_use_required_iso_seconds_and_hourly_cadence():
    from astropy.time import Time
    dates = module().epoch_dates()
    assert len(dates) == 32
    times = Time(dates.tolist(), format='isot', scale='utc').mjd
    assert dates[0] == '2025-01-01T00:00:00'
    assert np.allclose(np.diff(times) * 24, 1., atol=1e-8)
