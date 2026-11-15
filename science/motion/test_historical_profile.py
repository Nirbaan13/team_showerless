"""Unit regressions for historical review contracts; fixtures are not science acceptance evidence."""

from datetime import datetime, timezone

import numpy as np
import pytest

import review


def review_payload(*, outlier=True):
    """Small deterministic test-only images with a five-pixel/year track."""
    yy, xx = np.indices((56, 64))
    images = np.random.default_rng(42).normal(0, 1, (4, 56, 64))
    positions = np.array([[20, 28], [25, 28], [30, 28], [35, 28]])
    bloom = np.zeros_like(images, dtype=bool)
    for index, (x, y) in enumerate(positions):
        images[index] += 30 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.2 ** 2))
        bloom[index, y - 1:y + 2, x - 1:x + 2] = True
    return {
        'images': images,
        'times': np.array([0., 8766., 17532., 26298.]),
        'dates': np.array(['2010-01-01T00:00:00Z', '2011-01-01T03:00:00+03:00',
                           '2012-01-01T00:00:00+00:00', '2013-01-01T00:00:00']),
        'observation_ids': np.array(['test-0', 'test-1', 'test-2', 'test-3']),
        'outlier': np.zeros_like(images, dtype=bool) if outlier else None,
        'bloom': bloom,
        'expected_xy': positions,
        'center_deg': np.array([50., -20.]),
        'pixel_scale_arcsec': 2.75,
        'retain_outliers': outlier,
    }


def build(payload, **kwargs):
    return review.build_review(payload, 'test-historical', None, 'W1', None, **kwargs)


def test_slow_bounds_recover_all_review_branches_without_relabelling_hours():
    # Dropping min_speed from any branch excludes this multi-year track there.
    payload = review_payload()
    original_times = payload['times'].copy()
    result = build(payload, min_speed=0.00001, max_speed=0.001)
    for branch in ('shared_median', 'leave_one_out', 'outliers_masked', 'bloom'):
        assert result['comparison'][branch]['match']['rank'] == 1, branch
    assert all(check['match']['rank'] == 1 for check in result['omitted_frame_checks'])
    assert result['tracks'][0]['speed_px_per_time'] == pytest.approx(0.0005703855806525211)
    np.testing.assert_array_equal(payload['times'], original_times)
    assert result['detector_settings']['time_unit'] == 'hours'
    assert result['detector_settings']['min_speed'] == 0.00001
    assert result['detector_settings']['max_speed'] == 0.001


@pytest.mark.parametrize('bounds', [dict(min_speed=0.0008, max_speed=0.001),
                                    dict(min_speed=0.00001, max_speed=0.0003)])
def test_bounds_exclude_tracks_in_every_review_branch(bounds):
    result = build(review_payload(), **bounds)
    for branch in ('shared_median', 'leave_one_out', 'outliers_masked', 'bloom'):
        assert result['comparison'][branch]['match'] is None, branch
    assert all(check['match'] is None for check in result['omitted_frame_checks'])


def test_missing_outlier_evidence_stays_unavailable_for_qualified_historical_payload():
    result = build(review_payload(outlier=False), min_speed=0.00001, max_speed=0.001)
    assert result['comparison']['leave_one_out']['match']['rank'] == 1
    assert result['comparison']['outliers_masked'] is None
    assert result['tracks'][0]['outlier_at_position'] is None
    assert result['bloom_tracks'][0]['outlier_at_position'] is None


def test_aware_frame_dates_are_normalized_once_to_utc():
    result = build(review_payload())
    assert [frame['time'] for frame in result['frames']] == [
        '2010-01-01T00:00:00Z', '2011-01-01T00:00:00Z',
        '2012-01-01T00:00:00Z', '2013-01-01T00:00:00Z',
    ]
    assert all(datetime.fromisoformat(frame['time']).tzinfo == timezone.utc
               for frame in result['frames'])


def test_default_speed_bounds_preserve_spherex_behavior():
    result = build(review_payload())
    assert result['tracks'] == []
    assert result['bloom_tracks'] == []
    assert result['detector_settings']['min_speed'] == 0.5
    assert result['detector_settings']['max_speed'] == 60


def test_named_proper_motion_profile_converts_physical_units_and_records_provenance():
    from profiles import proper_motion_profile

    profile = proper_motion_profile(2.75)
    assert profile['name'] == 'historical-proper-motion'
    assert profile['min_speed'] == pytest.approx(0.000004148258840627721)
    assert profile['max_speed'] == pytest.approx(0.0012444776521883163)
    assert profile['proper_motion_arcsec_per_year'] == {'min': 0.1, 'max': 30.0}
    assert profile['pixel_scale_arcsec'] == 2.75
    assert profile['hours_per_year'] == 8766.0
    assert profile['speed_unit'] == 'pixels/hour'
    result = build(review_payload(), min_speed=profile['min_speed'],
                   max_speed=profile['max_speed'], search_profile=profile)
    assert result['search_profile'] == profile
    assert result['comparison']['leave_one_out']['match']['rank'] == 1


@pytest.mark.parametrize('pixel_scale', [0, -2.75, float('nan'), float('inf')])
def test_profile_rejects_pixel_scale_without_a_physical_conversion(pixel_scale):
    from profiles import proper_motion_profile

    with pytest.raises(ValueError, match='pixel scale'):
        proper_motion_profile(pixel_scale)


def test_actual_north_up_wcs_changes_only_post_detection_sky_conversion():
    from astropy.wcs import WCS

    payload = review_payload()
    legacy = build(payload, min_speed=0.00001, max_speed=0.001)
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    wcs.wcs.crpix = [32.5, 28.5]
    wcs.wcs.crval = [50., -20.]
    wcs.wcs.cdelt = [-2.75 / 3600, 2.75 / 3600]
    payload['sky_wcs_header'] = wcs.to_header().tostring(sep='\n')
    actual = build(payload, min_speed=0.00001, max_speed=0.001)
    for kind in ('tracks', 'bloom_tracks'):
        before, after = legacy[kind][0], actual[kind][0]
        assert all(position[1] < -20. for position in before['sky_deg'])
        assert all(position[1] > -20. for position in after['sky_deg'])
        for field in ('rank', 'positions_xy', 'speed_px_per_time', 'epochs'):
            assert after[field] == before[field]


def test_measured_track_speed_exposes_proper_motion_with_physical_unit():
    result = build(review_payload(), min_speed=0.00001, max_speed=0.001)
    for kind in ('tracks', 'bloom_tracks'):
        track = result[kind][0]
        assert track['speed_px_per_time'] == pytest.approx(0.0005703855806525211)
        assert track['proper_motion_arcsec_per_year'] == pytest.approx(13.75)
        assert track['proper_motion_unit'] == 'arcsec/year'
