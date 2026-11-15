"""Reproducible offline field-split RF training, ONNX export and evaluation.

Run from repository root with PYTHONPATH=backend/inference python -m training.train.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np
import onnx
import onnxruntime
import scipy
import sklearn
import skl2onnx
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score
from skl2onnx import to_onnx

from ml_inference.detector import baseline_score, find_candidates
from ml_inference.model import FEATURE_NAMES, SCORE_KIND, load_ranker
from training.simulate import simulate

# These are also the production CLI defaults. Leave-one-out references are mandatory.
DETECTOR_SETTINGS = dict(min_snr=4., max_peaks=100, psf_sigma=1.2, min_speed=.5,
                         max_speed=60., match_radius=1.4, min_epochs=3,
                         min_support=.8, leave_one_out=True)
MATCH_TOLERANCE_PX = 1.5


def split_seeds(train, validation, test):
    if min(train, validation, test) < 1 or max(train, validation, test) > 100_000:
        raise ValueError('partition sizes must be in [1, 100000]')
    return dict(train=list(range(train)), validation=list(range(100_000, 100_000 + validation)),
                test=list(range(200_000, 200_000 + test)))


def detections_for_field(seed):
    images, times, truth, mode = simulate(seed)
    tracks = find_candidates(images, times, **DETECTOR_SETTINGS)
    matches = []
    for track in tracks:
        positions = np.asarray(track.positions_xy)
        distances = [np.linalg.norm(positions - path[list(track.epochs)], axis=1) for path in truth]
        matching = [index for index, distance in enumerate(distances) if np.all(distance <= MATCH_TOLERANCE_PX)]
        matches.append(min(matching, key=lambda i: np.mean(distances[i])) if matching else -1)
    return dict(seed=seed, mode=mode, features=[list(map(float, track.features())) for track in tracks],
                matches=matches, truth_count=len(truth), baseline=[float(baseline_score(t)) for t in tracks])


def evaluate(fields, score, top_k):
    injected = recovered = found = false_at_k = candidates = 0
    labels, scores = [], []
    for field in fields:
        injected += field['truth_count']
        matches = np.asarray(field['matches'], dtype=int)
        candidates += len(matches)
        if not len(matches):
            continue
        ratings = score(field)
        selected = matches[np.argsort(-ratings, kind='stable')[:top_k]]
        recovered += len(set(selected) - {-1})
        found += len(set(matches) - {-1})
        false_at_k += int(np.count_nonzero(selected == -1))
        labels.extend(matches >= 0)
        scores.extend(ratings)
    return dict(fields=len(fields), candidates=candidates, injected_tracks=injected,
                recovered_before_ranking=found, recovered_in_top_k=recovered,
                top_k_recall=recovered / injected if injected else None,
                detector_recall=found / injected if injected else None,
                false_tracks_in_top_k=false_at_k,
                false_tracks_per_field_in_top_k=false_at_k / len(fields) if fields else None,
                track_average_precision=float(average_precision_score(labels, scores)) if any(labels) else None)


def feature_matrix(fields):
    x = np.asarray([row for f in fields for row in f['features']], dtype=np.float32).reshape(-1, 6)
    y = np.asarray([match >= 0 for f in fields for match in f['matches']], dtype=np.int64)
    return x, y


def fit_selected(train, validation, top_k):
    x, y = feature_matrix(train)
    if len(set(y)) != 2:
        raise ValueError('training fields must contain both classes')
    experiments = []
    best = None
    for leaf, depth in [(2, 10), (4, 12), (8, None)]:
        params = dict(n_estimators=150, min_samples_leaf=leaf, max_depth=depth,
                      class_weight='balanced', random_state=42, n_jobs=1)
        forest = RandomForestClassifier(**params).fit(x, y)
        metrics = evaluate(validation, lambda f: forest.predict_proba(np.asarray(f['features'], np.float32))[:, 1], top_k)
        experiments.append(dict(parameters=params, validation=metrics))
        key = (metrics['recovered_in_top_k'], -metrics['false_tracks_in_top_k'], metrics['track_average_precision'] or 0)
        if best is None or key > best[0]:
            best = key, forest
    return best[1], experiments


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def run(args):
    started = time.monotonic()
    seeds = split_seeds(args.train_fields, args.validation_fields, args.test_fields)
    fields = {}
    for partition, partition_seeds in seeds.items():
        fields[partition] = []
        for index, seed in enumerate(partition_seeds):
            fields[partition].append(detections_for_field(seed))
            if index % 10 == 0:
                print(f'{partition}: {index + 1}/{len(partition_seeds)} fields, elapsed {time.monotonic()-started:.1f}s', flush=True)
    forest, experiments = fit_selected(fields['train'], fields['validation'], args.top_k)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    x, y = feature_matrix(fields['train'])
    graph = to_onnx(forest, x[:1], options={id(forest): {'zipmap': False}}, target_opset=17)
    onnx.helper.set_model_props(graph, dict(schema_version='1', feature_names=json.dumps(list(FEATURE_NAMES)),
                                          class_labels='[0, 1]', score_kind=SCORE_KIND))
    onnx.checker.check_model(graph)
    artifact = output / 'ranker.onnx'
    artifact.write_bytes(graph.SerializeToString())
    base = Path(__file__).resolve().parent
    source_files = [base / 'train.py', base / 'simulate.py', base.parent / 'ml_inference' / 'detector.py']
    manifest = dict(schema_version=1, partitions=seeds, field_group='complete independent simulated field per seed',
                    real_observations_used=False, real_labels_used=False,
                    generator='training.simulate.simulate', generator_version=1,
                    source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                    source_sha256={str(p.relative_to(base.parent)): sha(p) for p in source_files},
                    attribution={'ml/benchmark.py': 'ca63aa4145f5a539b157f8bd25c237c8cca56148',
                                 'science/motion/ranker.py': '2b6dc435b0f73a6f255e50ca795900acfd69cd33'},
                    detector_settings=DETECTOR_SETTINGS, match_tolerance_px=MATCH_TOLERANCE_PX,
                    training_candidates=len(x), training_positive_candidates=int(y.sum()),
                    versions=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                                  sklearn=sklearn.__version__, skl2onnx=skl2onnx.__version__,
                                  onnx=onnx.__version__, onnxruntime=onnxruntime.__version__),
                    selection_rule='validation unique recoveries at fixed top_k, then fewer false tracks, then AP',
                    validation_experiments=experiments, selected_parameters=forest.get_params(),
                    refit_validation=False, top_k=args.top_k)
    write_json(output / 'training-manifest.json', manifest)
    metadata = dict(schema_version=1, model_id='spherex-track-rf-v1', sha256=sha(artifact),
                    feature_names=list(FEATURE_NAMES), class_labels=[0, 1], positive_class=1,
                    score_kind=SCORE_KIND, status='experimental',
                    score_description='Mean class-1 weighted leaf fraction across trees; not calibrated planet probability',
                    training_manifest_sha256=sha(output / 'training-manifest.json'))
    write_json(output / 'metadata.json', metadata)
    ranker = load_ranker(output)
    # Held-out and random probes make converter agreement reproducible without a pickle.
    heldout, _ = feature_matrix(fields['test'])
    rng = np.random.default_rng(8127)
    probes = np.vstack([x[:100], heldout[:1000], rng.uniform(0, 20, (250, 6))]).astype(np.float32)
    reference = forest.predict_proba(probes)[:, 1]
    actual = ranker.score(probes)
    np.testing.assert_allclose(actual, reference, rtol=2e-6, atol=2e-6)
    write_json(output / 'parity-reference.json', dict(features=probes.tolist(), scores=reference.tolist(),
                                                   max_abs_error=float(np.max(np.abs(actual-reference)))))
    report = dict(schema_version=1, top_k_per_field=args.top_k, model_sha256=sha(artifact),
                  training_manifest_sha256=sha(output / 'training-manifest.json'),
                  elapsed_seconds=time.monotonic() - started,
                  parity_max_abs_error=float(np.max(np.abs(actual-reference))), partitions={})
    for partition in ['validation', 'test']:
        report['partitions'][partition] = {}
        for subset in ['all', 'injected', 'noise_only', 'artifacts_only']:
            selected = [f for f in fields[partition] if subset == 'all' or f['mode'] == subset]
            if selected:
                report['partitions'][partition][subset] = dict(
                    baseline=evaluate(selected, lambda f: np.asarray(f['baseline']), args.top_k),
                    random_forest=evaluate(selected, lambda f: ranker.score(np.asarray(f['features'], np.float32)), args.top_k))
    write_json(output / 'evaluation.json', report)
    # Audit feature/label rows preserve full field identity and can be regenerated from seeds.
    write_json(output / 'field-candidates.json', fields)
    print(json.dumps(report, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train-fields', type=int, default=300)
    parser.add_argument('--validation-fields', type=int, default=100)
    parser.add_argument('--test-fields', type=int, default=200)
    parser.add_argument('--top-k', type=int, default=3)
    parser.add_argument('--output-dir', default=str(Path(__file__).resolve().parent.parent / 'models'))
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error('top-k must be positive')
    run(args)


if __name__ == '__main__':
    main()
