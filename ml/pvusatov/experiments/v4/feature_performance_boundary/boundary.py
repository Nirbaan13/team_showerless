"""Frozen bounded engineering parity harness; no labels, training, or promotion."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import sys
import time
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from ml_inference.detector import Candidate, difference_frames
from ml.pvusatov.experiments.v4.detection import features as reference
from ml.pvusatov.experiments.v4.detection.runtime_model import load_ranker
from ml.pvusatov.experiments.v4.feature_performance import prototype

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SCENARIOS = ('finite_noise', 'signed_quality', 'finite_support')
SIZES = (4095, 4096, 4097, 8192, 8193)
REFERENCE_SHA = '8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282'
PROTOTYPE_SHA = '47e3486cc94e65f520244575fc5dee8517ac5aa2e4f84c3f8a70c477df90102d'
MODEL_SHA = 'c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
MODEL_DIR = Path('/tmp/spaceapps-v4-operating-points/models/C596')


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def array_hash(value, dtype):
    a = np.asarray(value, dtype=dtype)
    return hashlib.sha256(str(a.shape).encode() + a.tobytes(order='C')).hexdigest()


def atomic_json(path, value):
    temp = Path(str(path) + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temp.replace(path)


def load_fixed_ranker():
    if digest_file(reference.__file__) != REFERENCE_SHA or digest_file(prototype.__file__) != PROTOTYPE_SHA:
        raise ValueError('immutable comparison source differs')
    model = load_ranker(MODEL_DIR)
    if model.metadata['sha256'] != MODEL_SHA:
        raise ValueError('fixed C596 model differs')
    return model


def make_inputs(epoch_count, boundary_rows, scenario, *, empty=False):
    """Engineer paths, then measure their Candidate fields from numeric arrays.

    These are measured engineering sampling paths, not asserted real detections.
    The boundary is about extractor arithmetic; no linking or source truth claim.
    """
    if epoch_count not in (8, 16) or scenario not in SCENARIOS or not 0 <= boundary_rows <= 8193:
        raise ValueError('case outside frozen engineering domain')
    seed = 3810000 + 100 * epoch_count + SCENARIOS.index(scenario)
    rng = np.random.default_rng(seed)
    times = np.cumsum(.07 + rng.uniform(.03, .15, epoch_count))
    images = rng.normal(size=(epoch_count, 64, 64)) * np.linspace(.5, 2., epoch_count)[:, None, None]
    yy, xx = np.mgrid[:64, :64]
    if scenario != 'finite_noise':
        images += (np.sin(xx / 7.) + np.cos(yy / 9.))[None] * .6
        images += np.where(np.arange(epoch_count) % 2, -.4, .4)[:, None, None]
        outlier = rng.random(images.shape) < .04
        bloom = np.zeros(images.shape, dtype=bool)
        bloom[:, 29:32, 15:48] = True
    else:
        outlier = bloom = None
    if scenario == 'finite_support':
        images[:, :3, :] = np.nan
        images[-2] = 0.
        images[-1] = np.nan
    residuals = difference_frames(images, leave_one_out=True)
    epochs = tuple(range(epoch_count - (scenario == 'finite_support')))
    noise = np.zeros(epoch_count)
    center = np.zeros(epoch_count)
    smooth = np.zeros_like(images)
    for e in epochs:
        values = images[e][np.isfinite(images[e])]
        center[e] = np.median(values)
        noise[e] = 1.4826 * np.median(abs(values - center[e]))
        support = gaussian_filter(np.isfinite(images[e]).astype(float), .8)
        smooth[e] = gaussian_filter(np.where(np.isfinite(images[e]), images[e], 0.), .8) / np.maximum(support, 1e-12)

    def measured(path_epochs, xy):
        ep = np.asarray(path_epochs, dtype=int)
        coords = np.asarray([ep, xy[:, 1], xy[:, 0]])
        signal = np.asarray([map_coordinates(images[e], xy[i:i+1, ::-1].T, order=1, mode='nearest', prefilter=False)[0] for i,e in enumerate(ep)])
        local = map_coordinates(smooth, coords, order=1, mode='nearest', prefilter=False)
        # Constant frames carry measured zero SNR; other epochs retain signed signal.
        snr = np.divide(signal - center[ep], noise[ep], out=np.zeros(len(ep)), where=noise[ep] > 0)
        ratio = np.divide(signal, np.maximum(abs(local), noise[ep]), out=np.zeros(len(ep)), where=np.maximum(abs(local), noise[ep]) > 0)
        t = times[ep] - times[ep].mean()
        velocity = t @ xy / (t @ t)
        fit = xy.mean(axis=0) + t[:, None] * velocity
        rms = np.sqrt(np.mean(np.sum((xy - fit) ** 2, axis=1)))
        candidate = Candidate(tuple(map(int, ep)), tuple(tuple(map(float, p)) for p in xy), tuple(map(float, snr)), float(np.linalg.norm(velocity)), float(rms), float(np.median(ratio)))
        if not np.isfinite(signal).all() or not np.isfinite(candidate.features()).all():
            raise ValueError('measured candidate has unsupported raw sample/nonfinite feature')
        return candidate

    tracks = []
    if not empty:
        dt = (times[list(epochs)] - times[epochs[0]]) / np.ptp(times[list(epochs)])
        for row in range(boundary_rows):
            origin = np.array([16. + (row % 97) * .28, 16. + (row // 97) * .28])
            velocity = np.array([.45 + (row % 7) * .013, -.28 + (row % 11) * .009])
            xy = origin + dt[:, None] * velocity
            tracks.append(measured(epochs, xy))
        for n, origin in [(3, (1., 12.)), (4, (62., 15.)), (3, (25., 24.)), (4, (28., 26.))]:
            xy = np.array(origin) + np.arange(n)[:, None] * np.array([.01, .02])
            tracks.append(measured(epochs[:n], xy))
    if images.shape != (epoch_count, 64, 64) or np.isinf(images).any() or not np.isfinite(times).all() or not np.all(np.diff(times) > 0):
        raise ValueError('invalid image/time input')
    if not np.any(images[np.isfinite(images)] < 0) or not np.any(images[np.isfinite(images)] > 0):
        raise ValueError('signed data requirement absent')
    for track in tracks:
        xy = np.asarray(track.positions_xy)
        if not np.isfinite(xy).all() or np.any(xy < 0) or np.any(xy > 63) or len(set(track.epochs)) != len(track.epochs):
            raise ValueError('invalid engineered sampling path')
    evidence = dict(seed=seed, shape=list(images.shape), boundary_group_rows=boundary_rows if not empty else 0,
        expected_valid_epoch_count=len(epochs), nan_pixels=int(np.isnan(images).sum()), finite_pixels=int(np.isfinite(images).sum()),
        zero_noise_epochs=[int(e) for e in epochs if noise[e] == 0],
        input_sha256=dict(images=array_hash(images, '<f8'), times=array_hash(times, '<f8'), residuals=array_hash(residuals, '<f8'),
            outlier=None if outlier is None else array_hash(outlier, '?'), bloom=None if bloom is None else array_hash(bloom, '?')),
        candidates_sha256=json_hash([dict(epochs=t.epochs, positions=t.positions_xy, snr=t.snr, speed=t.speed_px_per_time, fit=t.fit_rms_px, ratio=t.median_peak_ratio) for t in tracks]),
        representation='actual Candidate; measured engineered sampling paths, no claimed real detections; no labels')
    return images, times, tracks, dict(psf_sigma=.8, outlier=outlier, bloom=bloom, residuals=residuals), evidence


def run_case(epoch_count, boundary_rows, scenario, model, *, empty=False):
    images, times, tracks, options, evidence = make_inputs(epoch_count, boundary_rows, scenario, empty=empty)
    started = time.process_time()
    a = reference.extract_features(images, times, tracks, **options)
    reference_cpu = time.process_time() - started
    started = time.process_time()
    b = prototype.extract_features(images, times, tracks, **options)
    prototype_cpu = time.process_time() - started
    x = np.asarray(a['features_v4'], dtype=np.float64)
    y = np.asarray(b['features_v4'], dtype=np.float64)
    sx = model.score(x.astype(np.float32))
    sy = model.score(y.astype(np.float32))
    ox = np.argsort(-sx, kind='stable')
    oy = np.argsort(-sy, kind='stable')
    f64diff = x.view(np.uint64) != y.view(np.uint64)
    f32diff = x.astype(np.float32).view(np.uint32) != y.astype(np.float32).view(np.uint32)
    counts = {}
    for diagnostic in a['diagnostics']:
        key = str(len(diagnostic['photometry_valid_epochs']))
        counts[key] = counts.get(key, 0) + 1
    expected = str(evidence['expected_valid_epoch_count'])
    group_verified = empty or (counts.get(expected) == boundary_rows and b['batch_performance']['groups_by_valid_epoch_count'].get(expected) == boundary_rows)
    # Independent returned per-candidate support diagnostics establish actual group membership.
    first_group_support = all(len(d['photometry_valid_epochs']) == int(expected) for d in a['diagnostics'][:boundary_rows])
    edge_missing = empty or all(len(d['photometry_valid_epochs']) == 0 and bool(d['missing_statistics']) for d in a['diagnostics'][boundary_rows:boundary_rows+2])
    same_metadata = all(a[k] == b[k] for k in ('feature_names', 'feature_version', 'feature_contract_sha256', 'template_psf_sigma'))
    distinct = a['feature_source_sha256'] == REFERENCE_SHA and b['feature_source_sha256'] == PROTOTYPE_SHA and b['reference_feature_source_sha256'] == REFERENCE_SHA and REFERENCE_SHA != PROTOTYPE_SHA
    score_bits_equal = bool(np.array_equal(sx.view(np.uint32), sy.view(np.uint32)))
    result = dict(case_id=f'e{epoch_count}-{scenario}-n{boundary_rows}' + ('-empty' if empty else ''),
        engineering_only=True, epochs=epoch_count, scenario=scenario, rows=len(tracks), boundary_rows=boundary_rows,
        boundary_group_verified=bool(group_verified and first_group_support), edge_missing_support_verified=bool(edge_missing),
        observed_valid_epoch_counts=counts, prototype_batch=b['batch_performance'], evidence=evidence,
        float64_different_bits=int(f64diff.sum()), float32_different_bits=int(f32diff.sum()),
        float64_max_abs_difference=float(np.max(abs(x-y), initial=0.)),
        per_column_float64_different_bits={name:int(f64diff[:,i].sum()) for i,name in enumerate(reference.FEATURE_NAMES) if f64diff[:,i].any()},
        per_column_float32_different_bits={name:int(f32diff[:,i].sum()) for i,name in enumerate(reference.FEATURE_NAMES) if f32diff[:,i].any()},
        candidate_ids_equal=a['candidate_ids'] == b['candidate_ids'], diagnostics_equal=a['diagnostics'] == b['diagnostics'],
        semantic_metadata_equal=same_metadata, producer_source_distinct=distinct,
        C596_score_bits_equal=score_bits_equal, C596_score_max_abs_difference=float(np.max(abs(sx-sy), initial=0.)),
        stable_full_order_equal=bool(np.array_equal(ox, oy)), score_rows=len(sx), reference_unique_score_count=int(len(np.unique(sx))),
        hashes={name:dict(float64=array_hash(value, '<f8'), float32=array_hash(value, '<f4'), ids=json_hash(out['candidate_ids']), diagnostics=json_hash(out['diagnostics']), scores=array_hash(scores, '<f4'), stable_full_order=array_hash(order, '<i8'))
            for name,value,out,scores,order in [('reference',x,a,sx,ox), ('prototype',y,b,sy,oy)]},
        cpu_seconds=dict(reference=reference_cpu, prototype=prototype_cpu), maxrss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    result['all_contract_equal'] = bool(not f64diff.any() and not f32diff.any() and result['candidate_ids_equal'] and result['diagnostics_equal'] and same_metadata and distinct and score_bits_equal and result['stable_full_order_equal'])
    return result


def source_bindings():
    paths = [Path(reference.__file__), Path(prototype.__file__), Path(__file__), HERE/'test_feature_boundary_parity.py', HERE/'Plan.AI.md',
        ROOT/'ml/pvusatov/experiments/v4/detection/runtime_model.py', ROOT/'ml/pvusatov/backend/inference/ml_inference/detector.py', MODEL_DIR/'metadata.json', MODEL_DIR/'ranker.onnx']
    return {str(p):digest_file(p) for p in paths}


def freeze():
    """Write-once plan/source/model binding; never constructs numeric fixtures."""
    path = HERE/'protocol.json'
    if path.exists():
        raise ValueError('protocol already frozen; do not overwrite')
    sources = source_bindings()
    if sources[str(Path(reference.__file__))] != REFERENCE_SHA or sources[str(Path(prototype.__file__))] != PROTOTYPE_SHA or sources[str(MODEL_DIR/'ranker.onnx')] != MODEL_SHA:
        raise ValueError('source/model differs before freeze')
    protocol = dict(designation='bounded numeric engineering parity only; no scientific evaluation or promotion',
        frozen_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), source_sha256=sources,
        cases=[dict(epochs=e, rows=n, scenario=s) for e in (8,16) for s in SCENARIOS for n in SIZES],
        empty_cases=[8,16], limits=dict(cpu=1, math_threads=1, ram_gib=8, elapsed_minutes=30),
        model_sha256=MODEL_SHA, model_directory=str(MODEL_DIR),
        rule='Report all30 F64/F32 column bits, IDs, full diagnostics, actual C596 score bits and complete stable order; preserve every error/difference. Producer source remains explicitly different.')
    atomic_json(path, protocol)
    print('frozen', digest_file(path), flush=True)


def main():
    if sys.argv[1:] == ['--freeze']:
        freeze()
        return
    if sys.argv[1:]:
        raise ValueError('use --freeze once, then invoke without arguments')
    started = time.monotonic()
    protocol = json.loads((HERE/'protocol.json').read_text())
    if source_bindings() != protocol['source_sha256']:
        raise ValueError('source/model changed after freeze')
    cpu = sorted(os.sched_getaffinity(0))[-1]
    os.sched_setaffinity(0, {cpu})
    resource.setrlimit(resource.RLIMIT_AS, (8*1024**3, 8*1024**3))
    model = load_fixed_ranker()
    report = dict(protocol_sha256=digest_file(HERE/'protocol.json'), source_sha256=protocol['source_sha256'],
        python=sys.version, platform=platform.platform(), numpy_version=np.__version__, cpu_affinity=[cpu],
        thread_environment={key:os.environ.get(key) for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')}, results=[])
    cases = [(c['epochs'],c['rows'],c['scenario'],False) for c in protocol['cases']] + [(e,0,'finite_noise',True) for e in protocol['empty_cases']]
    for e,n,s,empty in cases:
        if time.monotonic()-started > 29*60:
            report['resource_stop'] = 'prospective29-minute stop'
            break
        try:
            result = run_case(e,n,s,model,empty=empty)
        except Exception as exc:
            result = dict(case_id=f'e{e}-{s}-n{n}', error=dict(type=type(exc).__name__,message=str(exc)))
        report['results'].append(result)
        report['elapsed_seconds'] = time.monotonic()-started
        atomic_json(HERE/'results-v1.json', report)
        print(result['case_id'], 'rows',result.get('rows'), 'parity',result.get('all_contract_equal'), 'group',result.get('boundary_group_verified'), result.get('error',''), flush=True)
    report['immutable_bindings_unchanged'] = source_bindings() == protocol['source_sha256']
    report['complete'] = len(report['results']) == len(cases)
    report['all_cases_pass'] = report['complete'] and report['immutable_bindings_unchanged'] and all(r.get('all_contract_equal') and r.get('boundary_group_verified') and r.get('edge_missing_support_verified') for r in report['results'])
    atomic_json(HERE/'results-v1.json', report)
    if not report['all_cases_pass']:
        raise SystemExit('negative or incomplete engineering result retained')


if __name__ == '__main__':
    main()
