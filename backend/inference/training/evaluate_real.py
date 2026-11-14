"""Evaluate selected real recovery cases without fitting or labeling unknown tracks.

These are selected development cases: two objects in four detector cutouts,
not four independent test fields and not a precision or false-positive survey.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

from ml_inference.contracts import validate_request
from ml_inference.detector import find_candidates
from ml_inference.model import load_ranker
from ml_inference.prepare import prepare
from ml_inference.pipeline import _bloom_tracks


def recovery(tracks, scores, expected, tolerance=1.5):
    order = np.argsort(-scores, kind='stable')
    ranks = {int(index): rank for rank, index in enumerate(order, 1)}
    matches = []
    for index, track in enumerate(tracks):
        distance = np.linalg.norm(np.asarray(track.positions_xy) - expected[list(track.epochs)], axis=1)
        if np.all(distance <= tolerance):
            matches.append(dict(heuristic_rank=index + 1, model_rank=ranks[index],
                                epochs=len(track.epochs), max_offset_px=float(distance.max())))
    return dict(candidates=len(tracks), known_target_recovered=bool(matches),
                known_target_matches=matches, unmatched_candidates_unlabeled=len(tracks)-len(matches))


def evaluate(model_dir=None, fixture_dir=None):
    base = Path(__file__).resolve().parents[1]
    fixture_dir = Path(fixture_dir or base / 'fixtures')
    ranker = load_ranker(model_dir)
    report = dict(schema_version=1, model_sha256=ranker.metadata['sha256'],
                  designation='selected development/recovery cases', independent_known_objects=2,
                  unmatched_candidates='unlabeled, never counted as false detections', cases={})
    for name in ['comet-d6', 'comet-d2', 'vesta-d6', 'vesta-d3']:
        path = fixture_dir / f'{name}.npz'
        request = dict(schema_version=1, analysis_id=f'evaluation-{name}',
                       source=dict(kind='preset', preset_id=name, path=str(path)))
        # Match the actual production preparation and physical-hour time convention.
        options = validate_request(request)
        stack = prepare(request)
        settings = dict(min_snr=options['min_snr'], max_peaks=options['max_peaks'], psf_sigma=1.2,
                        min_speed=options['min_speed_arcsec_per_hour']/stack.pixel_scale,
                        max_speed=options['max_speed_arcsec_per_hour']/stack.pixel_scale,
                        match_radius=1.4, min_epochs=options['min_epochs'], min_support=.8)
        tracks = find_candidates(stack.images, stack.times, **settings, leave_one_out=True)
        features = np.asarray([t.features() for t in tracks], dtype=np.float32).reshape(-1, 6)
        scores = ranker.score(features)
        # Labels enter only after preparation, detection and frozen model scoring.
        with np.load(path, allow_pickle=False) as archive:
            expected = np.asarray(archive['expected_xy'])
        record = recovery(tracks, scores, expected)
        shared = find_candidates(stack.images, stack.times, **settings, leave_one_out=False)
        record['shared_reference_recovery'] = recovery(shared, np.arange(len(shared), 0, -1), expected)
        if stack.bloom is not None:
            bloom, capped = _bloom_tracks(stack.bloom, stack.times, settings)
            record['bloom_recovery'] = recovery(bloom, np.arange(len(bloom), 0, -1), expected)
            record['bloom_recovery']['ml_score_applied'] = False
            record['bloom_recovery']['peak_cap_reached'] = bool(capped)
        record.update(fixture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      object_group='3I/ATLAS' if name.startswith('comet') else 'Vesta',
                      exposures=len(stack.images), detector_settings=settings,
                      source_revision='2b6dc435b0f73a6f255e50ca795900acfd69cd33')
        report['cases'][name] = record
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir')
    parser.add_argument('--fixture-dir')
    parser.add_argument('--output', default=str(Path(__file__).resolve().parents[1] / 'models' / 'real-evaluation.json'))
    args = parser.parse_args()
    report = evaluate(args.model_dir, args.fixture_dir)
    Path(args.output).write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
