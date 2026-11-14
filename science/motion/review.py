"""Generate a candidate review from an aligned SPHEREx stack."""

import argparse
import base64
import json
import struct
import zlib
from dataclasses import asdict
from pathlib import Path

import numpy as np
from scipy.ndimage import center_of_mass, label, map_coordinates

if __package__:
    from .detector import difference_frames, filtered_evidence, find_candidates, link_detections
    from .ranker import TRAINING_FIELDS, random_forest_order, train_random_forest
else:
    from detector import difference_frames, filtered_evidence, find_candidates, link_detections
    from ranker import TRAINING_FIELDS, random_forest_order, train_random_forest

PIXEL_RADIUS = 14
MIN_SUPPORT = 0.8
PSF_SIGMA = 1.2
MATCH_TOLERANCE = 1.5
ARCHIVE_URL = 'https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html'
VESTA_ARCHIVE_URL = 'https://caltech-ipac.github.io/irsa-tutorials/most-queries/'
SERIES = {
    'december-d6': ('3I/ATLAS', 'D6', ARCHIVE_URL),
    'december-d2': ('3I/ATLAS', 'D2', ARCHIVE_URL),
    'vesta-d3': ('(4) Vesta', 'D3', VESTA_ARCHIVE_URL),
    'vesta-d6': ('(4) Vesta', 'D6', VESTA_ARCHIVE_URL),
}


def stretch(array, floor, ceiling):
    levels = np.clip((np.nan_to_num(array) - floor) / (ceiling - floor), 0, 1)
    return np.rint(10 + 241 * np.arcsinh(levels * 5) / np.arcsinh(5)).astype(np.uint8)


def png_url(array):
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))

    height, width = array.shape
    header = struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)
    pixels = b''.join(b'\0' + row.tobytes() for row in array)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
           + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))
    return 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')


def fitted_positions(track, times):
    measured = np.array(track.positions_xy)
    fitted_times = times[list(track.epochs)]
    delta_time = fitted_times - fitted_times.mean()
    velocity = delta_time @ measured / (delta_time @ delta_time)
    return measured.mean(axis=0) + (times - fitted_times.mean())[:, None] * velocity


def stack_evidence(significance, coordinates):
    """Coadd standardized residuals on a small grid around supplied positions."""
    axis = np.arange(-PIXEL_RADIUS, PIXEL_RADIUS + 1)
    dy, dx = np.meshgrid(axis, axis, indexing='ij')
    sum_z = np.zeros_like(dx, dtype=float)
    count = np.zeros_like(dx, dtype=int)
    for image, (x, y) in zip(significance, coordinates):
        finite = np.isfinite(image)
        points = [y + dy, x + dx]
        interpolated = map_coordinates(np.where(finite, image, 0), points, order=1)
        covered = map_coordinates(finite.astype(float), points, order=1) >= 0.995
        sum_z += np.where(covered, interpolated, 0)
        count += covered
    return np.divide(sum_z, np.sqrt(count), where=count > 0, out=np.full_like(sum_z, np.nan)), count


def projected_coordinates(xy, width, height, ra_center, dec_center, pixel_scale):
    """Inverse gnomonic projection for the grid produced by prepare_fits.py."""
    xi, eta = np.deg2rad((np.asarray(xy).T - np.array([[(width - 1) / 2], [(height - 1) / 2]]))
                         * -pixel_scale / 3600)
    ra0, dec0 = np.deg2rad([ra_center, dec_center])
    denominator = np.cos(dec0) - eta * np.sin(dec0)
    ra = ra0 + np.arctan2(xi, denominator)
    dec = np.arctan2(np.sin(dec0) + eta * np.cos(dec0), np.hypot(denominator, xi))
    return np.column_stack((np.rad2deg(ra) % 360, np.rad2deg(dec)))


def ephemeris_match(track, expected):
    if expected is None:
        return None
    offsets = np.linalg.norm(np.array(track.positions_xy) - expected[list(track.epochs)], axis=1)
    if np.max(offsets) <= MATCH_TOLERANCE:
        return offsets
    return None


def bloom_candidates(masks, times, max_speed):
    peaks = []
    for mask in masks:
        components, count = label(mask, structure=np.ones((3, 3)))
        areas = np.bincount(components.ravel(), minlength=count + 1)
        ids = np.flatnonzero(areas[1:] >= 6) + 1
        positions = center_of_mass(mask, components, ids)
        peaks.append(np.array([(x, y, areas[index], 0) for (y, x), index in zip(positions, ids)]).reshape(-1, 4))
    return link_detections(peaks, times, .5, max_speed, 1.4, 3, subpixel=True)


def candidate_record(track, rank, images, times, significance, supports, outlier, expected, grid, *, bloom=None):
    fitted = fitted_positions(track, times)
    epochs = list(track.epochs)
    is_bloom = bloom is not None
    evidence = bloom.astype(float) if is_bloom else significance
    # Use the same linked frames in both stacks. The stationary view uses the median track position.
    aligned, coverage = stack_evidence(evidence[epochs], fitted[epochs])
    stationary_position = np.broadcast_to(np.median(fitted[epochs], axis=0), (len(epochs), 2))
    stationary, _ = stack_evidence(evidence[epochs], stationary_position)
    display_values = np.concatenate((aligned[np.isfinite(aligned)], stationary[np.isfinite(stationary)]))
    floor, scale = ((0, np.sqrt(len(epochs))) if is_bloom else
                    (2, max(6.0, float(np.percentile(display_values, 99.8))) if display_values.size else 6.0))
    offsets = ephemeris_match(track, expected)
    height, width = images.shape[1:]
    sky = projected_coordinates(track.positions_xy, width, height, *grid)
    record = asdict(track)
    if is_bloom:
        record.update(snr=None, median_peak_ratio=None, bloom_area_px=list(map(int, track.snr)))
    pixels = np.rint(track.positions_xy).astype(int).tolist()
    record.update({
        'id': f'{"bloom" if is_bloom else "candidate"}-{rank:02d}',
        'method': 'bloom_centroids' if is_bloom else 'heuristic_leave_one_out',
        'rank': rank,
        'known_match': offsets is not None,
        'max_offset_px': None if offsets is None else round(float(max(offsets)), 3),
        'ephemeris_offsets_px': None if offsets is None else offsets.round(3).tolist(),
        'sky_deg': sky.round(7).tolist(),
        'filter_support': None if is_bloom else [round(float(supports[index, y, x]), 3)
                                               for index, (x, y) in zip(epochs, pixels)],
        'outlier_at_position': [bool(outlier[index, y, x])
                                for index, (x, y) in zip(epochs, pixels)],
        'fixed_stack': png_url(stretch(stationary, floor, scale)),
        'motion_stack': png_url(stretch(aligned, floor, scale)),
        'stack_contributing_exposures': int(coverage[PIXEL_RADIUS, PIXEL_RADIUS]),
    })
    return record


def best_match(tracks, expected):
    for rank, track in enumerate(tracks, 1):
        offsets = ephemeris_match(track, expected)
        if offsets is not None:
            return {'rank': rank, 'exposures': len(track.epochs), 'max_offset_px': round(float(max(offsets)), 3)}
    return None


def make_review(path, max_speed=60, forest=None):
    with np.load(path) as data:
        target, detector, source = SERIES.get(path.stem, (None, None, None))
        return build_review(data, path.stem, target, detector, source, max_speed=max_speed, forest=forest)


def build_review(data, series_id, target, detector, source, *, max_speed=60, forest=None, track_limit=None):
    images = data['images'].astype(float)
    times, dates, ids = data['times'], data['dates'], data['observation_ids']
    outlier = data['outlier']
    expected = data.get('expected_xy')
    bloom = data.get('bloom')
    grid = (*map(float, data['center_deg']), float(data['pixel_scale_arcsec']))
    retains_outliers = bool(data['retain_outliers'])
    if expected is not None and (expected.shape != (len(images), 2) or not np.isfinite(expected).all()):
        raise ValueError(f'{series_id} needs one finite ephemeris position per exposure')
    settings = {'max_speed': max_speed, 'min_support': MIN_SUPPORT, 'psf_sigma': PSF_SIGMA}
    tracks = find_candidates(images, times, leave_one_out=True, **settings)
    forest_order = random_forest_order(forest, tracks) if forest is not None else []
    forest_ranks = {index: rank for rank, index in enumerate(forest_order, 1)}
    baseline = find_candidates(images, times, **settings)
    strict = find_candidates(np.where(outlier, np.nan, images), times, leave_one_out=True, **settings)
    bloom_tracks = bloom_candidates(bloom, times, max_speed) if bloom is not None else []
    residuals = difference_frames(images, leave_one_out=True)
    evidence = [filtered_evidence(diff, np.isfinite(diff), PSF_SIGMA, MIN_SUPPORT) for diff in residuals]
    _, significance, supports, _ = (np.stack(column) for column in zip(*evidence))
    valid = np.isfinite(images)
    raw_ceiling = max(.1, float(np.nanpercentile(images, 99.9)))
    finite_significance = significance[np.isfinite(significance)]
    detection_ceiling = max(6., float(np.percentile(finite_significance, 99.9))) if finite_significance.size else 6.0
    omitted_frame_checks = []
    if expected is not None and len(images) == 4:
        for index in range(len(images)):
            keep = np.arange(len(images)) != index
            reduced = find_candidates(images[keep], times[keep], leave_one_out=True, **settings)
            omitted_frame_checks.append({'omitted_observation_id': str(ids[index]),
                                         'match': best_match(reduced, expected[keep])})
    frames = [
        {'id': str(identifier), 'time': str(date) + 'Z',
         'coverage': round(float(mask.mean()), 4),
         'aligned': png_url(stretch(image, raw_ceiling * .025, raw_ceiling)),
         'residual': png_url(stretch(signal, 2, detection_ceiling))}
        for identifier, date, mask, image, signal in zip(ids, dates, valid, images, significance)
    ]
    if bloom is not None:
        for frame, mask in zip(frames, bloom):
            frame['bloom'] = png_url(stretch(mask, 0, 1))
    return {
        'id': series_id,
        'target': target,
        'detector': detector,
        'source': source,
        'width': images.shape[2],
        'height': images.shape[1],
        'pixel_scale_arcsec': grid[2],
        'retains_outliers': retains_outliers,
        'has_ephemeris': expected is not None,
        'ephemeris_match_tolerance_px': MATCH_TOLERANCE if expected is not None else None,
        'simulated_training_fields': TRAINING_FIELDS if forest is not None else None,
        'omitted_frame_checks': omitted_frame_checks,
        'frames': frames,
        'tracks': [{**candidate_record(track, index + 1, images, times, significance, supports,
                                       outlier, expected, grid),
                    'random_forest_rank': forest_ranks.get(index)}
                   for index, track in enumerate(tracks[:track_limit])],
        'bloom_tracks': [candidate_record(track, index + 1, images, times, significance, supports,
                                          outlier, expected, grid, bloom=bloom)
                         for index, track in enumerate(bloom_tracks[:track_limit])],
        'comparison': {
            'shared_median': {'candidates': len(baseline), 'match': best_match(baseline, expected)},
            'leave_one_out': {'candidates': len(tracks), 'match': best_match(tracks, expected)},
            'random_forest': (None if forest is None else
                              {'candidates': len(tracks),
                               'match': best_match([tracks[i] for i in forest_order], expected)}),
            'outliers_masked': {'candidates': len(strict), 'match': best_match(strict, expected)},
            'bloom': None if bloom is None else {'candidates': len(bloom_tracks),
                                                  'match': best_match(bloom_tracks, expected)},
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stacks', type=Path, nargs='+')
    parser.add_argument('--max-speed', type=float, default=60, help='Maximum track speed in pixels per hour')
    parser.add_argument('--compare-random-forest', action='store_true', help='Train on simulated fields and rerank the same candidates (requires scikit-learn)')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    forest = train_random_forest() if args.compare_random_forest else None
    reports = [make_review(path, args.max_speed, forest) for path in args.stacks]
    args.output.write_text(json.dumps(reports, allow_nan=False, separators=(',', ':')) + '\n')
    for data in reports:
        print(data['id'], json.dumps(data['comparison']))


if __name__ == '__main__':
    main()
