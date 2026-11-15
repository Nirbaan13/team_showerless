"""Development-only frozen-system compatibility on packaged real presets.

Expected positions are loaded only after both systems finish detection/scoring.
This does not fit, select a second model, run final data, or modify production.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from ml_inference.contracts import validate_request
from ml_inference.detector import find_candidates, baseline_score, difference_frames, _detect_peaks
from ml_inference.model import load_ranker
from ml_inference.pipeline import _bloom_tracks, select_review_entries
from ml_inference.prepare import prepare

BASE = Path(__file__).resolve().parents[2]
V2_SHA = 'dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9'
CASES = ['comet-d2', 'comet-d6', 'vesta-d3', 'vesta-d6']
PROFILE_KEYS = {'min_snr', 'max_peaks', 'psf_sigma', 'min_speed', 'max_speed',
                'match_radius', 'min_epochs', 'min_support', 'leave_one_out'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_candidate(directory, expected_sha256):
    directory = Path(directory)
    freeze_path = directory / 'freeze.json'
    if not freeze_path.is_file():
        raise ValueError('reviewed candidate development freeze is missing')
    freeze = json.loads(freeze_path.read_text())
    metadata = json.loads((directory / 'metadata.json').read_text())
    digest = sha(directory / 'ranker.onnx')
    if digest != expected_sha256 or metadata.get('sha256') != digest or freeze.get('model_sha256') != digest:
        raise ValueError('candidate artifact checksum differs from reviewed hash')
    if freeze.get('final_fields_opened') is not False:
        raise ValueError('candidate freeze must record final fields unopened')
    profile = metadata.get('detector_profile')
    if not isinstance(profile, dict) or set(profile) != PROFILE_KEYS:
        raise ValueError('complete candidate metadata.detector_profile is required')
    if freeze.get('detector_profile') != profile:
        raise ValueError('candidate metadata profile differs from development freeze')
    return metadata, profile, freeze


def load_expected(path, frames):
    """Offline labels keyed by physical observation, after scientific inference."""
    with np.load(path, allow_pickle=False) as data:
        identifiers = np.asarray(data['observation_ids']).astype(str)
        expected = np.asarray(data['expected_xy'], dtype=float)
    if expected.shape != (len(identifiers), 2) or not np.isfinite(expected).all():
        raise ValueError('invalid offline expected positions')
    lookup = {}
    for identifier, position in zip(identifiers, expected):
        if identifier in lookup and not np.array_equal(lookup[identifier], position):
            raise ValueError('inconsistent duplicate observation labels')
        lookup[identifier] = position
    return np.asarray([lookup[frame['observation_id']] for frame in frames])


def recovery(records, bloom, expected, max_candidates=100, *, preserve_bloom=False):
    """One unique known target, equal review budgets, stable score ties."""
    def labeled(row):
        distance = np.linalg.norm(np.asarray(row['positions_xy']) - expected[row['epochs']], axis=1)
        return dict(row, known_target_match=bool(np.all(distance <= 1.5)),
                    max_target_offset_px=float(distance.max()))
    rows = [labeled(row) for row in records]
    order = np.argsort(-np.asarray([row['score'] for row in rows]), kind='stable')
    for rank, index in enumerate(order, 1):
        rows[int(index)]['model_rank'] = rank
    bloom_rows = []
    for index, row in enumerate(bloom):
        if row['score'] is not None:
            raise ValueError('BLOOM evidence cannot carry a model score')
        bloom_rows.append(dict(labeled(row), score=None, model_rank=None, evidence_rank=index + 1,
                               score_kind='flagged_bloom_evidence', ml_score_applied=False))
    model_order = [rows[int(i)] for i in order]
    heuristic_order = sorted(rows, key=lambda row: row['heuristic_rank'])
    def at_k(ordered, k):
        return any(row['known_target_match'] for row in ordered[:k])
    residual = dict(candidate_count=len(rows), detected_before_ranking=any(row['known_target_match'] for row in rows),
                    matching_candidate_rows=sum(row['known_target_match'] for row in rows),
                    unmatched_candidate_identities='unknown, never negatives',
                    model_at_1=at_k(model_order, 1), model_at_3=at_k(model_order, 3),
                    heuristic_at_1=at_k(heuristic_order, 1), heuristic_at_3=at_k(heuristic_order, 3))
    # The shared output policy sees original, unlabelled records only. Truth
    # annotations are joined back afterward and never affect which rows survive.
    annotated = {id(raw): labelled for raw, labelled in zip(records, rows)}
    annotated.update({id(raw): labelled for raw, labelled in zip(bloom, bloom_rows)})
    raw_model = [records[int(i)] for i in order]
    raw_heuristic = sorted(records, key=lambda row: row['heuristic_rank'])
    def published_order(raw_rows):
        entries = [(row, row['heuristic_rank'], row['score'], False) for row in raw_rows]
        entries.extend((row, index + 1, None, True) for index, row in enumerate(bloom))
        selected = select_review_entries(entries, max_candidates, preserve_bloom=preserve_bloom)
        return [annotated[id(entry[0])] for entry in selected]
    model_published = published_order(raw_model)
    heuristic_published = published_order(raw_heuristic)
    def review_records(ordered):
        return [dict(review_rank=index + 1, candidate_index=row['candidate_index'], method=row['method'],
                     score=row['score'], model_rank=row['model_rank'],
                     known_target_match=row['known_target_match']) for index, row in enumerate(ordered)]
    published = dict(candidate_count=len(model_published),
                     before_cap_count=len(rows) + len(bloom_rows),
                     candidate_cap_reached=len(rows) + len(bloom_rows) > max_candidates,
                     ordering='protect_first3_residual_then_flagged_bloom' if preserve_bloom else 'legacy_entries_slice',
                     preserve_bloom=preserve_bloom,
                     residual_count=sum(row['method'] == 'residual_track' for row in model_published),
                     bloom_count=sum(row['method'] == 'bloom_track' for row in model_published),
                     known_target_present=any(row['known_target_match'] for row in model_published),
                     flagged_bloom_omitted=sum(row['method'] == 'bloom_track' for row in model_published) < len(bloom_rows),
                     model_entries=review_records(model_published), heuristic_entries=review_records(heuristic_published),
                     model_at_1=at_k(model_published, 1), model_at_3=at_k(model_published, 3),
                     heuristic_at_1=at_k(heuristic_published, 1), heuristic_at_3=at_k(heuristic_published, 3))
    return dict(residual=residual, published=published,
                bloom=dict(candidate_count=len(bloom_rows), detected_before_ranking=any(row['known_target_match'] for row in bloom_rows),
                           matching_candidate_rows=sum(row['known_target_match'] for row in bloom_rows), ml_score_applied=False),
                residual_records=rows, bloom_records=bloom_rows)


def track_record(track, index, stack, *, bloom=False):
    flags = []
    for epoch, position in zip(track.epochs, track.positions_xy):
        x, y = map(int, np.rint(position))
        flags.append(dict(epoch=int(epoch), outlier=bool(stack.outlier[epoch, y, x]),
                          bloom=bool(stack.bloom[epoch, y, x]) if stack.bloom is not None else False))
    return dict(candidate_index=index, method='bloom_track' if bloom else 'residual_track',
                epochs=list(map(int, track.epochs)), positions_xy=np.asarray(track.positions_xy).tolist(),
                measured_speed_px_per_hour=float(track.speed_px_per_time),
                measured_speed_arcsec_per_hour=float(track.speed_px_per_time * stack.pixel_scale),
                fit_rms_px=float(track.fit_rms_px), detection_flags=flags,
                residual_snr=None if bloom else list(map(float, track.snr)),
                features=None if bloom else list(map(float, track.features())),
                heuristic_score=None if bloom else float(baseline_score(track)),
                warnings=['saturated_bloom_centroid', 'not_photometry', 'not_ml_ranked'] if bloom else [])


def run_profile(stack, ranker, settings):
    """No truth argument or expected-coordinate access exists in this stage."""
    started = time.perf_counter()
    tracks = find_candidates(stack.images, stack.times, **settings)
    detection_seconds = time.perf_counter() - started
    features = np.asarray([track.features() for track in tracks], np.float32).reshape(-1, 6)
    started = time.perf_counter()
    scores = ranker.score(features)
    scoring_seconds = time.perf_counter() - started
    records = [dict(track_record(track, index, stack), score=float(scores[index]),
                    score_kind=ranker.metadata['score_kind']) for index, track in enumerate(tracks)]
    heuristic_order = np.argsort(-np.asarray([row['heuristic_score'] for row in records]), kind='stable')
    for rank, index in enumerate(heuristic_order, 1):
        records[int(index)]['heuristic_rank'] = rank
    started = time.perf_counter()
    bloom, bloom_capped = _bloom_tracks(stack.bloom, stack.times, settings) if stack.bloom is not None else ([], False)
    bloom_seconds = time.perf_counter() - started
    bloom_records = [dict(track_record(track, index, stack, bloom=True), score=None,
                          heuristic_rank=None) for index, track in enumerate(bloom)]
    started = time.perf_counter()
    peaks = [len(_detect_peaks(diff, np.isfinite(diff), settings['psf_sigma'], settings['min_snr'],
                              settings['max_peaks'], settings['min_support']))
             for diff in difference_frames(stack.images, settings['leave_one_out'])]
    return dict(detector_settings=dict(settings), residual_records=records, bloom_records=bloom_records,
                preserve_bloom_policy='detector_profile' in ranker.metadata,
                peaks_per_epoch=peaks, peak_cap_reached=any(n >= settings['max_peaks'] for n in peaks),
                bloom_peak_cap_reached=bool(bloom_capped),
                stage_wall_seconds=dict(detection=detection_seconds, scoring=scoring_seconds, bloom=bloom_seconds,
                                        peak_diagnostic=time.perf_counter() - started))


def evaluate(candidate_directory, candidate_sha256, baseline_directory=None):
    candidate_directory = Path(candidate_directory)
    metadata, candidate_settings, freeze = verify_candidate(candidate_directory, candidate_sha256)
    baseline_directory = Path(baseline_directory or BASE / 'models')
    if sha(baseline_directory / 'ranker.onnx') != V2_SHA:
        raise ValueError('immutable deployed v2 baseline changed')
    started = time.perf_counter()
    baseline_ranker = load_ranker(baseline_directory)
    baseline_load = time.perf_counter() - started
    started = time.perf_counter()
    candidate_ranker = load_ranker(candidate_directory)
    candidate_load = time.perf_counter() - started
    manifests = {row['id']: row for row in json.loads((BASE / 'fixtures/presets.json').read_text())}
    cases = {}
    for name in CASES:
        path = BASE / 'fixtures' / (name + '.npz')
        if sha(path) != manifests[name]['sha256']:
            raise ValueError('packaged development fixture checksum mismatch')
        request = dict(schema_version=1, analysis_id='development-preset-' + name,
                       source=dict(kind='preset', preset_id=name, path=str(path)))
        options = validate_request(request)
        started = time.perf_counter()
        stack = prepare(request)
        prepare_seconds = time.perf_counter() - started
        baseline_settings = dict(min_snr=options['min_snr'], max_peaks=options['max_peaks'], psf_sigma=1.2,
            min_speed=options['min_speed_arcsec_per_hour'] / stack.pixel_scale,
            max_speed=options['max_speed_arcsec_per_hour'] / stack.pixel_scale,
            match_radius=1.4, min_epochs=options['min_epochs'], min_support=.8, leave_one_out=True)
        systems = {}
        for role, ranker, settings in [('baseline', baseline_ranker, baseline_settings),
                                        ('candidate', candidate_ranker, candidate_settings)]:
            try:
                systems[role] = dict(succeeded=True, **run_profile(stack, ranker, settings))
            except (ValueError, RuntimeError) as error:
                systems[role] = dict(succeeded=False, detector_settings=settings,
                                     error=dict(type=type(error).__name__, message=str(error)))
        # Only this post-inference labeling stage loads expected positions.
        expected = load_expected(path, stack.frames)
        for role, system in systems.items():
            if system['succeeded']:
                system['recovery'] = recovery(system.pop('residual_records'), system.pop('bloom_records'),
                    expected, max_candidates=options['max_candidates'], preserve_bloom=system['preserve_bloom_policy'])
        regressions = []
        if all(system['succeeded'] for system in systems.values()):
            for cohort in ['residual', 'published']:
                for endpoint in ['model_at_1', 'model_at_3']:
                    if systems['baseline']['recovery'][cohort][endpoint] and not systems['candidate']['recovery'][cohort][endpoint]:
                        regressions.append(cohort + '_' + endpoint)
            if systems['baseline']['recovery']['residual']['detected_before_ranking'] and not systems['candidate']['recovery']['residual']['detected_before_ranking']:
                regressions.append('residual_detector_recovery')
        elif systems['baseline']['succeeded'] and not systems['candidate']['succeeded']:
            regressions.append('candidate_execution_failed')
        cases[name] = dict(object_group='3I/ATLAS' if name.startswith('comet') else 'Vesta', detector=int(name[-1]),
            fixture_sha256=sha(path), fixture_bytes=path.stat().st_size, frames=stack.frames,
            registered_shape=list(stack.images.shape), pixel_scale_arcsec=stack.pixel_scale,
            times_hours=stack.times.tolist(), intervals_hours=np.diff(stack.times).tolist(),
            finite_fraction_per_epoch=np.isfinite(stack.images).mean(axis=(1, 2)).tolist(),
            outlier_fraction_per_epoch=stack.outlier.mean(axis=(1, 2)).tolist(),
            bloom_fraction_per_epoch=stack.bloom.mean(axis=(1, 2)).tolist() if stack.bloom is not None else None,
            mask_policy=options['mask_policy'], preparation_warnings=stack.warnings, provenance=stack.provenance,
            expected_xy_evaluation_only=expected.tolist(), target_match_tolerance_px=1.5,
            prepare_wall_seconds=prepare_seconds, systems=systems, regression_flags=regressions,
            native_v3_holdout_support='SWIR D1–3 only; this MWIR D6 preset has no independent v3 native holdout support' if name.endswith('6') else 'Selected development case, not a fresh final field')
        print(name, 'regressions=' + repr(regressions), flush=True)
    sources = [Path(__file__), BASE / 'training/evaluate_real.py', BASE / 'ml_inference/prepare.py',
               BASE / 'ml_inference/detector.py', BASE / 'ml_inference/pipeline.py', BASE / 'ml_inference/model.py']
    return dict(schema_version=1, generated_utc=datetime.now(timezone.utc).isoformat(),
        designation='Four selected real DEVELOPMENT compatibility cases; two known objects, no independent final test',
        independent_known_objects=2, fitting_or_reselection_performed=False, final_data_opened=False,
        baseline=dict(directory=str(baseline_directory), model_sha256=V2_SHA, model_id=baseline_ranker.metadata['model_id']),
        candidate=dict(directory=str(candidate_directory), model_sha256=candidate_sha256, model_id=metadata['model_id'],
                       model_family=metadata.get('model_family'), detector_profile=candidate_settings,
                       metadata_sha256=sha(candidate_directory / 'metadata.json'), development_freeze_sha256=sha(candidate_directory / 'freeze.json')),
        stage_scope='Preparation/detection/scoring/BLOOM and diagnostic peak counts; no rendering, process startup or API queue time',
        model_load_wall_seconds=dict(baseline=baseline_load, candidate=candidate_load),
        unknown_real_tracks='Unlabeled; no precision or false-positive metric', bloom_policy='Unscored flagged-source evidence, never RF/ExtraTrees probability',
        cases=cases, source_sha256={str(p.relative_to(BASE)): sha(p) for p in sources},
        limitations=['Selected recovery/development cases, four views of two objects, not four independent fields',
                     'Native v3 final groups were restricted to SWIR D1–3 and do not verify MWIR D6',
                     'Compatibility regression is reported honestly and never selects a second model or changes the final gate',
                     'Scores are uncalibrated rankings; BLOOM evidence has no model score'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-model', required=True)
    parser.add_argument('--candidate-sha256', required=True)
    parser.add_argument('--baseline-model')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.candidate_model, args.candidate_sha256, args.baseline_model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
