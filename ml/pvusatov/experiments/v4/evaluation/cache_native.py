"""V4 TRAIN/DEV native caches with truthful unknown labels and measured features.

Never opens FINAL inputs. The guarded final runner will have a separate entry
point and external source/model/data freeze. V3 helpers are imported read-only;
their original files and the deployed runtime are never modified.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
from types import SimpleNamespace
import time

NAMESPACE = Path(__file__).resolve().parents[3]
PACKAGE = NAMESPACE / 'backend/inference'
V4 = Path(__file__).resolve().parents[1]
C13 = 'c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204'
SETTINGS = dict(min_snr=4., max_peaks=100, psf_sigma=.8, min_speed=.5,
                max_speed=60., match_radius=1.4, min_epochs=3, min_support=.8, leave_one_out=True)
EXECUTED_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def load_module(name, path, expected_sha256=None):
    path = Path(path).resolve()
    source = path.read_bytes()
    source_sha = hashlib.sha256(source).hexdigest()
    if expected_sha256 is not None and source_sha != expected_sha256:
        raise ValueError('module source closure differs before execution')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # SourceFileLoader may read a stale same-size/same-second timestamp pyc.
    # Execute precisely the bytes whose hash was checked instead.
    exec(compile(source, str(path), 'exec'), module.__dict__)
    module.__source_sha256__ = source_sha
    return module


def verify_source_closure(closure):
    for path, expected in closure.items():
        if digest(path) != expected:
            raise ValueError('source closure changed: ' + path)
    own = str(Path(__file__).resolve())
    if own in closure and closure[own] != EXECUTED_SOURCE_SHA256:
        raise ValueError('executed generator source closure differs from invocation')


def read_json(path):
    def invalid(value):
        raise ValueError('nonfinite JSON: ' + value)
    return json.loads(Path(path).read_text(), parse_constant=invalid)


def validate_development_group(group):
    """Metadata and byte validation before any FITS library or pixel reader."""
    if group.get('split') not in ('train', 'validation'):
        raise ValueError('only TRAIN or DEVELOPMENT validation inputs accepted')
    if any(part.lower().startswith(('final', 'quarant')) for part in Path(group['downloads_manifest']['path']).parts):
        raise ValueError('quarantined inputs forbidden')
    ref = group['downloads_manifest']
    if digest(ref['path']) != ref['sha256']:
        raise ValueError('downloads manifest hash mismatch')
    rows = read_json(ref['path'])
    if not isinstance(rows, list) or not 3 <= len(rows) <= 32:
        raise ValueError('invalid native epoch count')
    observations = []
    for row in rows:
        path = Path(row['path']).resolve()
        if any(part.lower().startswith(('final', 'quarant')) for part in path.parts):
            raise ValueError('quarantined native pixels forbidden')
        if digest(path) != row['sha256']:
            raise ValueError('native input byte hash mismatch')
        observations.append({**row, 'path': str(path), 'frame_id': path.stem,
                             'observation_id': row['obs_id'], 'access_url': row.get('url')})
    if len({row['obs_id'] for row in rows}) != len(rows) or len({row['sha256'] for row in rows}) != len(rows):
        raise ValueError('duplicate physical observation or native bytes')
    if group.get('physical_obsids') is not None and set(group['physical_obsids']) != {row['obs_id'] for row in rows}:
        raise ValueError('native handoff observation identities differ')
    return observations


def matches_truth(tracks, expected_xy):
    import numpy as np
    expected = np.asarray(expected_xy, dtype=float)
    return [bool(np.all(np.linalg.norm(np.asarray(track.positions_xy) - expected[list(track.epochs)], axis=1) <= 1.5))
            for track in tracks]


def label_native_tracks(tracks, expected_xy, *, stationary, preexisting):
    matched = matches_truth(tracks, expected_xy)
    if stationary:
        return [-1 if match and not preexisting else -2 for match in matched]
    return [0 if match else -2 for match in matched]


def _source_closure(feature_path):
    paths = [Path(__file__).resolve(), Path(__file__).with_name('geometry.py'), feature_path,
             PACKAGE / 'experiments/v3_evaluation/run_native.py', PACKAGE / 'training/evaluate_background.py']
    paths += sorted((PACKAGE / 'ml_inference').glob('*.py'))
    return {str(path): digest(path) for path in paths}


def _record_measurement(images, times, stack, extractor, detector, ranker, old):
    import numpy as np
    started = time.perf_counter()
    residuals = detector.difference_frames(images, leave_one_out=True)
    tracks = detector.find_candidates(images, times, **SETTINGS)
    measured = extractor.extract_features(images, times, tracks, psf_sigma=.8,
                                         outlier=stack.outlier, bloom=stack.bloom, residuals=residuals)
    features = np.asarray([track.features() for track in tracks], dtype=np.float32).reshape(-1, 6)
    rich = np.asarray(measured['features_v4'], dtype=np.float32)
    if rich.shape != (len(tracks), len(extractor.FEATURE_NAMES)) or not np.isfinite(rich).all():
        raise ValueError('invalid rich candidate feature matrix')
    if not np.array_equal(rich[:, :6], features):
        raise ValueError('legacy feature columns no longer align with candidate rows')
    scores = ranker.score(features)
    peaks = [len(detector._detect_peaks(image, np.isfinite(image), .8, 4., 100, .8)) for image in residuals]
    record = dict(features=features.tolist(), features_v4=rich.tolist(),
                  candidate_ids=measured['candidate_ids'], baseline=[float(detector.baseline_score(track)) for track in tracks],
                  scores_c13=scores.tolist(), scores=scores.tolist(),
                  candidate_epochs=[list(track.epochs) for track in tracks],
                  candidate_positions_xy=[list(track.positions_xy) for track in tracks],
                  peaks_per_epoch=peaks, peak_cap_reached=any(value >= 100 for value in peaks),
                  feature_diagnostics=measured.get('diagnostics', measured.get('missing_statistics', [])),
                  elapsed_seconds=time.perf_counter() - started, error=None,
                  rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    # Candidate-derived geometry is the original audited matching implementation.
    return tracks, record


def run_group(task):
    group, output, seed, feature_sha, kind, stationary_positions, closure = task
    verify_source_closure(closure)
    observations = validate_development_group(group)
    feature_path = V4 / 'detection/features.py'
    if digest(feature_path) != feature_sha:
        raise ValueError('feature source changed before native reader')
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[name] = '1'
    import sys
    sys.path.insert(0, str(PACKAGE))
    import numpy as np
    from ml_inference import detector
    from ml_inference.model import load_ranker
    from ml_inference.prepare import prepare
    from training.evaluate_background import read_native, project_response, add_projected_injection
    extractor = load_module('v4_native_physical_features', feature_path, closure[str(feature_path)])
    geometry_path = Path(__file__).with_name('geometry.py')
    geometry = load_module('v4_native_geometry', geometry_path, closure[str(geometry_path)])
    old_path = PACKAGE / 'experiments/v3_evaluation/run_native.py'
    old = load_module('v3_immutable_native_helpers', old_path, closure[str(old_path)])
    ranker = load_ranker(NAMESPACE / 'releases/v3/model')
    if ranker.metadata['sha256'] != C13:
        raise ValueError('native baseline differs from deployed frozen C13')
    center = group.get('center_deg', group.get('center'))
    region = dict(right_ascension_deg=center[0], declination_deg=center[1], width_arcmin=6., height_arcmin=6.)
    request = dict(schema_version=1, analysis_id='v4-development-' + group['parent_id'],
                   source=dict(kind='fits', observations=observations, region=region),
                   options=dict(pixel_scale_arcsec=6.15, mask_policy='motion'))
    started = time.perf_counter()
    stack = prepare(request)
    lookup = {row['frame_id']: row for row in observations}
    ordered = [lookup[frame['frame_id']] for frame in stack.frames]
    if len(ordered) != len(observations):
        raise ValueError('native preparation silently changed independent exposure count')
    natives = [read_native(row['path'], stack.grid, stack.images.shape[1:]) for row in ordered]
    science = SimpleNamespace(project_response=project_response, add_injection=add_projected_injection)
    control_tracks, control = _record_measurement(stack.images, stack.times, stack, extractor, detector, ranker, old)
    control.update(matches=[-2] * len(control_tracks), labels='UNKNOWN real tracks; never negative training labels')
    parent = dict(parent_id=group['parent_id'], seed=seed, _scope=group['split'])
    destination = Path(output) / (group['parent_id'] + '-' + kind + '.json.gz')
    metadata = dict(schema_version=4, designation='TRAIN/DEVELOPMENT only; not independent final',
                    parent_id=group['parent_id'], partition=group['split'], seed=seed,
                    input_sources=ordered, center_deg=center, frames=stack.frames,
                    times_hours=stack.times.tolist(), registered_shape=list(stack.images.shape),
                    detector_settings=SETTINGS, preparation_options=request['options'],
                    feature_names=list(extractor.FEATURE_NAMES), feature_version=extractor.FEATURE_VERSION,
                    feature_contract_sha256=extractor.FEATURE_CONTRACT_SHA256, feature_source_sha256=feature_sha,
                    source_sha256=closure, baseline_model_sha256=C13,
                    control=control, control_diagnostics={'peak_cap_reached': control['peak_cap_reached']},
                    downloads_manifest=group['downloads_manifest'], all_derivatives_correlated=True,
                    limitations=['projected after registration', 'fixed flux across passbands',
                                 'no added photon noise or variance update', 'real controls remain UNKNOWN',
                                 'stationary injected sources do not update native mission flags'])
    writer = old.AtomicCache(destination, metadata)
    try:
        if kind in ('moving', 'both'):
            for identity, images, positions, error in old._native_latents(parent, stack, natives, science, list(stack.images.shape[1:]), None):
                if error:
                    raise ValueError('native injection failed: ' + json.dumps(error))
                tracks, measured = _record_measurement(images, stack.times, stack, extractor, detector, ranker, old)
                preexisting = any(matches_truth(control_tracks, positions))
                record = old._record(tracks, [positions], True)
                field = {**identity, **record, **measured, 'truth_kind': 'moving_injection',
                         'attribution_eligible': not preexisting, 'preexisting_control_match': preexisting,
                         'geometric_capability': geometry.geometry_capability(positions, stack.times, identity['center_usable_flags'])}
                writer.append(field)
        if kind in ('stationary', 'both'):
            rng = np.random.default_rng(seed + 200000)
            h, w = stack.images.shape[1:]
            noise = np.asarray([1.4826 * np.median(abs(values - np.median(values))) for image in stack.images
                                for values in [image[np.isfinite(image)]]])
            for index in range(stationary_positions):
                origin = rng.uniform([8., 8.], [w - 8., h - 8.])
                positions = np.tile(origin, (len(stack.times), 1))
                projected = [project_response(native, stack.grid, origin) for native in natives]
                responses = np.asarray([row[0] for row in projected])
                positive = np.max(responses, axis=(1, 2)); positive = positive[positive > 0]
                normalization = float(np.median(positive)) if len(positive) else 1.
                preexisting = any(matches_truth(control_tracks, positions))
                for brightness in (3., 6., 12., 24., 48.):
                    flux = brightness * float(np.median(noise)) / normalization
                    images = add_projected_injection(stack.images, responses, flux)
                    for image in images:
                        image -= np.nanmedian(image)
                    tracks, measured = _record_measurement(images, stack.times, stack, extractor, detector, ranker, old)
                    field = dict(parent_id=parent['parent_id'], partition=group['split'], seed=seed,
                                 trajectory_id='stationary-' + str(index), brightness=brightness,
                                 truth_kind='stationary_injected_artifact', truth_count=0,
                                 expected_xy=positions.tolist(), origin_xy=origin.tolist(), injected_flux=flux,
                                 attribution_eligible=not preexisting, preexisting_control_match=preexisting,
                                 stationary_sky_truth=True, matched_geometry=[],
                                 matches=label_native_tracks(tracks, positions, stationary=True, preexisting=preexisting),
                                 **measured)
                    writer.append(field)
        writer.finish()
    except BaseException:
        writer.abort()
        raise
    verify_source_closure(closure)
    return dict(parent_id=group['parent_id'], partition=group['split'], path=str(destination),
                sha256=digest(destination), summary=writer.summary,
                elapsed_seconds=time.perf_counter() - started, feature_source_sha256=feature_sha)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff', type=Path, required=True)
    parser.add_argument('--parent-id', action='append')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--feature-source-sha256', required=True)
    parser.add_argument('--kind', choices=('moving', 'stationary', 'both'), default='both')
    parser.add_argument('--stationary-positions', type=int, default=60)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 6 or not 0 <= args.stationary_positions <= 100:
        parser.error('unsupported worker or stationary trial count')
    args.output.mkdir(parents=True, exist_ok=True)
    snapshot = args.output / 'handoff.snapshot.json'
    if snapshot.exists() or (args.output / 'development-run-manifest.json').exists():
        raise ValueError('refusing to overwrite an existing native run')
    handoff_bytes = args.handoff.read_bytes()
    snapshot.write_bytes(handoff_bytes)
    handoff_sha = hashlib.sha256(handoff_bytes).hexdigest()
    handoff = read_json(snapshot)
    closure = _source_closure(V4 / 'detection/features.py')
    verify_source_closure(closure)
    archive = args.output / 'source-snapshots'
    archive.mkdir()
    for path, expected in closure.items():
        source = Path(path).read_bytes()
        if hashlib.sha256(source).hexdigest() != expected:
            raise ValueError('source closure changed while snapshotting')
        (archive / (expected + '-' + Path(path).name)).write_bytes(source)
    (args.output / 'source-closure.snapshot.json').write_text(json.dumps(closure, indent=2) + '\n')
    if handoff.get('scope') != 'TRAIN_AND_DEVELOPMENT_VALIDATION_ONLY':
        raise ValueError('native handoff must explicitly exclude FINAL inputs')
    groups = handoff['groups']
    if args.parent_id:
        groups = [group for group in groups if group['parent_id'] in args.parent_id]
        if {group['parent_id'] for group in groups} != set(args.parent_id):
            raise ValueError('requested native development parent is not ready')
    if not groups or len({group['parent_id'] for group in groups}) != len(groups):
        raise ValueError('empty or duplicate native development parents')
    tasks = []
    for group in groups:
        # Identity is assigned before pixels, independently of field outcomes.
        ordinal = int(group['parent_id'][-2:])
        seed = (3200000 if group['split'] == 'train' else 3300000) + ordinal
        tasks.append((group, str(args.output), seed, args.feature_source_sha256, args.kind, args.stationary_positions, closure))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_group, task) for task in tasks]
        results = []
        for future in as_completed(futures):
            value = future.result(); results.append(value)
            print(json.dumps(value), flush=True)
    manifest = dict(schema_version=4, handoff_sha256=handoff_sha, handoff_snapshot=str(snapshot),
                    feature_source_sha256=args.feature_source_sha256, source_sha256=closure,
                    outputs=sorted(results, key=lambda row: row['parent_id']))
    path = args.output / 'development-run-manifest.json'
    if path.exists():
        raise ValueError('refusing to overwrite development run manifest')
    path.write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
