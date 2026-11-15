"""Idealized DEVELOPMENT sensitivity/observability study, never instrument calibration.

The root reserved seeds3802000..3802099 solely for this stress. A source-bound
protocol must exist and validate before any RNG/model call. No selection/promotion
uses this experiment. Independent units are100 shared-noise parent fields, not
2,000 correlated derivatives. All template searches remain blind over the grid.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import resource
import time
from types import SimpleNamespace
import numpy as np
from ml_inference.detector import find_candidates, difference_frames, _detect_peaks
from ml_inference.model import load_ranker
from ml.pvusatov.experiments.v4.detection import joint_tracking, joint_competitor
from ml.pvusatov.experiments.v4.detection.pilot_joint_tracking import SETTINGS, C13, evaluate, atomic, digest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
INF = REPO / 'ml/pvusatov/backend/inference'
AUTH = None
RANKER = None
AMPLITUDES = (0., 2., 3., 4., 6.)
THRESHOLDS = (5., 6., 7.)
SEEDS = tuple(range(3802000, 3802100))


def make_variants(noise, angle, center):
    """Pure paired image construction; no target coordinates enter a detector."""
    noise = np.asarray(noise, float)
    if noise.shape != (8, 64, 64) or not np.isfinite(noise).all():
        raise ValueError('eight64-square finite shared-noise images required')
    yy, xx = np.indices((64, 64), dtype=float)
    ry, rx = np.mgrid[-3:4, -3:4]
    kernel = np.exp(-(rx * rx + ry * ry) / (2 * .8 ** 2))
    kernel /= kernel.sum()
    # Known simulation amplitude relative to unit white-noise template variance.
    reference_norm = float(np.sqrt(np.sum(kernel * kernel)))
    noise_sha = hashlib.sha256(np.ascontiguousarray(noise).tobytes()).hexdigest()
    direction = np.asarray([np.cos(angle), np.sin(angle)])
    for cadence, duration in [('short', .35), ('long', 7.)]:
        times = np.linspace(0., duration, 8)
        path = np.asarray(center) + 4. * (times - duration / 2)[:, None] * direction
        response = np.exp(-((xx[None] - path[:, 0, None, None]) ** 2 +
                            (yy[None] - path[:, 1, None, None]) ** 2) / (2 * .8 ** 2))
        response /= response.sum(axis=(1, 2))[:, None, None]
        for count, epochs in [(3, [0, 3, 7]), (8, list(range(8)))]:
            for nominal in AMPLITUDES:
                amplitude = nominal / reference_norm
                images = noise[epochs] + amplitude * response[epochs]
                yield dict(cadence=cadence, epoch_count=count, original_epochs=epochs,
                    nominal_template_amplitude=nominal, known_simulated_integrated_amplitude=amplitude,
                    known_per_epoch_white_noise_template_snr=(amplitude * np.sqrt(np.sum(response[epochs] ** 2, axis=(1, 2)))).tolist(),
                    shared_noise_sha256=noise_sha, times_hours=times[epochs], images=images,
                    truth_paths=[path] if nominal else [],
                    true_span_px=float(np.linalg.norm(path[-1] - path[0])), noise_units='independent Gaussian N(0,1); no physical photometric calibration')


def initialize(protocol_path, protocol_sha):
    global AUTH
    path = Path(protocol_path)
    if digest(path) != protocol_sha:
        raise ValueError('idealized protocol bytes changed')
    value = json.loads(path.read_text())
    if value['seeds'] != list(SEEDS) or value['nominal_template_amplitudes'] != list(AMPLITUDES):
        raise ValueError('only reserved DEVELOPMENT idealized matrix accepted')
    if any(digest(path) != sha for path, sha in value['source_sha256'].items()):
        raise ValueError('idealized source/model closure changed before calls')
    AUTH = value


def draw_parent(seed):
    if AUTH is None or seed not in SEEDS:
        raise ValueError('validated DEVELOPMENT protocol required before RNG')
    noise = np.random.default_rng(seed).normal(size=(8, 64, 64))
    geometry = np.random.default_rng(np.random.SeedSequence([seed, 4281]))
    angle = float(geometry.uniform(0., 2 * np.pi))
    center = [31.5, 31.5] + geometry.uniform(-2., 2., 2)
    return noise, angle, center


def one(seed):
    global RANKER
    noise, angle, center = draw_parent(seed)
    if RANKER is None:
        RANKER = load_ranker(REPO / 'ml/pvusatov/releases/v3/model')
        if RANKER.metadata['sha256'] != C13:
            raise ValueError('strong frozen baseline differs')
    records = []
    for variant in make_variants(noise, angle, center):
        images = variant.pop('images'); times = variant.pop('times_hours'); truth = variant.pop('truth_paths')
        epochs = variant['original_epochs']; started = time.perf_counter(); cpu = time.process_time()
        row = dict(variant, seed=seed, independent_parent=str(seed), truth_count=len(truth), times_hours=times.tolist())
        try:
            base_start = time.perf_counter()
            original = find_candidates(images, times, **SETTINGS)
            scores = RANKER.score(np.asarray([t.features() for t in original], np.float32).reshape(-1, 6))
            order = np.argsort(-scores, kind='stable')
            baseline = [SimpleNamespace(epochs=tuple(epochs[e] for e in original[i].epochs), positions_xy=original[i].positions_xy) for i in order]
            residuals = difference_frames(images, leave_one_out=True)
            peak_counts = [len(_detect_peaks(d, np.isfinite(d), .8, 4., 100, .8)) for d in residuals]
            row['baseline'] = dict(evaluate(baseline, truth, False), wall_seconds=time.perf_counter() - base_start,
                peaks_per_epoch=peak_counts, peak_cap_reached=any(n >= 100 for n in peak_counts))
            maps, normalization = joint_tracking.nuisance_maps(images)
            methods = {}; diagnostics = []
            for statistic in ['nuisance_sum', 'robust_positive', 'single_epoch_competitor']:
                module = joint_competitor if statistic == 'single_epoch_competitor' else joint_tracking
                tracks, diag = module.search_maps(maps, times, reference_epoch_count=len(times), real_epochs=epochs,
                    threshold=5., max_work=600000000, statistic=statistic)
                diagnostics.append(diag)
                for threshold in THRESHOLDS:
                    selected = [t for t in tracks if t.search_statistic >= threshold]
                    hidden = diag['first_unpublished_statistic'] is not None and diag['first_unpublished_statistic'] >= threshold
                    methods[f'{statistic}:{threshold:g}'] = dict(evaluate(selected, truth, False),
                        capped_publication=hidden, hypothesis_search_complete=diag['hypothesis_search_complete'])
            row.update(methods=methods, diagnostics=diagnostics, normalization=normalization, error=None)
        except Exception as exc:
            row['error'] = type(exc).__name__ + ': ' + str(exc)
        row.update(wall_seconds=time.perf_counter() - started, cpu_seconds=time.process_time() - cpu,
            rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
        records.append(row)
    return records


def summarize(records):
    output = {}
    for cadence in ['short', 'long']:
        for count in [3, 8]:
            for amplitude in AMPLITUDES:
                fields = [r for r in records if (r['cadence'], r['epoch_count'], r['nominal_template_amplitude']) == (cadence, count, amplitude)]
                ok = [r for r in fields if r['error'] is None]
                methods = {}
                for name in ['baseline'] + [f'{s}:{t:g}' for s in ['nuisance_sum', 'robust_positive', 'single_epoch_competitor'] for t in THRESHOLDS]:
                    values = [r['baseline'] if name == 'baseline' else r['methods'][name] for r in ok]
                    methods[name] = dict(allplanned=len(fields), completed=len(ok), errors=len(fields) - len(ok),
                        truth_count=sum(r['truth_count'] for r in fields),
                        **{k:sum(v[k] for v in values) for k in ['candidate_rows','detected','top1','top3','resolved_detected','resolved_top1','resolved_top3']},
                        fields_with_proposals=sum(v['candidate_rows'] > 0 for v in values),
                        capped_publications=sum(v.get('capped_publication', v.get('peak_cap_reached', False)) for v in values))
                output[f'{cadence}:{count}:{amplitude:g}'] = methods
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--protocol', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.workers <= 6 or Path(args.output).exists():
        raise ValueError('bounded workers and new immutable output required')
    sources = [Path(__file__), HERE / 'joint_tracking.py', HERE / 'joint_tracking.cpp',
        HERE / 'joint_competitor.py', HERE / 'joint_competitor.cpp', HERE / 'pilot_joint_tracking.py',
        INF / 'ml_inference/detector.py', INF / 'ml_inference/model.py',
        REPO / 'ml/pvusatov/releases/v3/model/ranker.onnx', REPO / 'ml/pvusatov/releases/v3/model/metadata.json']
    plans = []
    for duration in [.35, 7.]:
        times = np.linspace(0., duration, 8)
        for epochs in [[0,3,7], list(range(8))]:
            plans.append(dict(duration_hours=duration, epochs=epochs,
                **joint_tracking.plan_search(times[epochs], (64,64), reference_epoch_count=len(epochs))))
    value = dict(schema_version=1, designation='IDEALIZED DEVELOPMENT stress, no instrument calibration or promotion selection',
        seeds=list(SEEDS), source_sha256={str(p):digest(p) for p in sources}, baseline_sha256=C13,
        nominal_template_amplitudes=list(AMPLITUDES), thresholds=list(THRESHOLDS), plans=plans,
        independent_fields=100, derivatives_per_field=20, allplanned_derivatives=2000,
        geometry='speed4px/h, center31.5+-2, angleuniform; short.35h/long7h; full64-square blind template grid',
        pairing='same8noiseimages,sourceangle,midpoint in all20derivatives;3epochs selectoriginal0,3,7',
        limitations=['white Gaussian equal-noise background only', 'Gaussian point PSF matches search approximation',
            'no native WCS/masks/passband/PSF variation or photon noise', 'known amplitude simulation units, not measured flux/confidence',
            'short1.4px truthspan is unresolved by3px engineering criterion', 'no promotion from this stress'])
    protocol = Path(args.protocol)
    if protocol.exists():
        if json.loads(protocol.read_text()) != json.loads(json.dumps(value)):
            raise ValueError('existing idealized protocol differs')
    else:
        atomic(protocol, value)
    protocol_sha = digest(protocol)
    if args.plan_only:
        print(json.dumps(dict(protocol=str(protocol), sha256=protocol_sha, allplanned=2000,
            nominal_pixel_epoch_tests=100 * len(AMPLITUDES) * 3 * sum(p['planned_pixel_epoch_tests'] for p in plans))))
        return
    started = time.perf_counter(); records = []
    journal = Path(args.output + '.jsonl')
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open('x') as stream, ProcessPoolExecutor(max_workers=args.workers, initializer=initialize, initargs=(str(protocol), protocol_sha)) as pool:
        for fields in pool.map(one, SEEDS, chunksize=1):
            records.extend(fields)
            for field in fields:
                stream.write(json.dumps(field, allow_nan=False) + '\n')
            stream.flush()
            print(json.dumps(dict(completed=len(records), planned=2000, last_parent=fields[0]['seed'],
                errors=sum(f['error'] is not None for f in fields), elapsed=time.perf_counter()-started)), flush=True)
    if any(digest(path) != sha for path, sha in value['source_sha256'].items()):
        raise ValueError('source closure changed during idealized stress')
    report = dict(protocol_sha256=protocol_sha, source_sha256=value['source_sha256'], summary=summarize(records),
        fields=records, elapsed_seconds=time.perf_counter()-started, independent_parents=100,
        designation=value['designation'], limitations=value['limitations'])
    atomic(args.output, report)
    print(json.dumps(dict(output=args.output, completed=len(records), errors=sum(r['error'] is not None for r in records), elapsed=report['elapsed_seconds'])), flush=True)


if __name__ == '__main__':
    main()
