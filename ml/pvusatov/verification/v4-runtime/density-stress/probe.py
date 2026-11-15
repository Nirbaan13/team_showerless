"""Fixed engineering density probe; no fitting, truth-labelled metrics or final data."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import numpy as np

OWN = Path(__file__).resolve().parent
COUNTS = (8, 32, 100)
PLAN = 'plan-v2.json'
MODEL = 'c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
META = '472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def source_paths(count):
    if count not in COUNTS:
        raise ValueError('Only predeclared densities are supported')
    starts = np.asarray([(50. + 40. * (i % 10), 50. + 40. * (i // 10)) for i in range(count)])
    return starts[:, None, :] + np.arange(32)[None, :, None] * np.asarray([1., .2])


def add_source(image, x, y):
    left, bottom = int(np.floor(x)) - 4, int(np.floor(y)) - 4
    yy, xx = np.mgrid[bottom:bottom + 10, left:left + 10]
    kernel = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * .8 ** 2))
    image[bottom:bottom + 10, left:left + 10] += (50 * kernel / kernel.sum()).astype(np.float32)


def epoch_dates():
    return (np.datetime64('2025-01-01T00:00:00', 's') + np.arange(32) * np.timedelta64(1, 'h')).astype('datetime64[s]').astype(str)


def roots():
    repo = next(p for p in OWN.parents if (p / 'ml/pvusatov/releases/v4').is_dir())
    return repo, repo / 'ml/pvusatov/releases/v4/runtime', repo / 'ml/pvusatov/releases/v4/model'


def declare():
    path = OWN / PLAN
    if path.exists():
        raise ValueError('Plan already frozen')
    repo, runtime, model = roots()
    assert digest(model / 'ranker.onnx') == MODEL and digest(model / 'metadata.json') == META
    sources = {str(p.relative_to(repo)): digest(p) for p in sorted((runtime / 'ml_inference').glob('*.py'))}
    plan = dict(declared_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                question='Engineering workload density at maximum accepted shape, not sensitivity or worst-case guarantee',
                shape=[32, 512, 512], dtype='float32', counts=list(COUNTS), seeds=[4200000 + n for n in COUNTS],
                noise_sigma=.05, psf_sigma=.8, discrete_source_amplitude=50.,
                paths='10x10 row-major grid starts(50+40col,50+40row); x+=epoch,y+=.2epoch; no wrap',
                hourly_epochs=32, options=dict(min_snr=4., max_candidates=100, max_peaks=100),
                cpu_count=1, math_threads=1, timeout_seconds=300, observed_rss_stop_bytes=1024**3,
                rss_poll_seconds=.05, memory_statement='Sampled RSS stop is not a hard cgroup, allocation cap or OOM proof',
                model_sha256=MODEL, metadata_sha256=META, source_sha256=sources,
                probe_sha256=digest(__file__), fixture_identity='ENGINEERING, not real comet-d2 despite trusted preset parser identifier',
                acceptance='Record every planned outcome, including CLI workload_limit or monitor interruption; no tuning/replacements',
                persistence='No NPZ/PNG fixtures committed; hashes/results survive temporary-directory cleanup')
    plan['amendment'] = dict(original_plan_sha256=digest(OWN / 'plan.json'),
                             retained_failed_attempt='case-8', reason='Fixture serialization used hourly precision rejected before detection; seconds ISO corrected, images/options unchanged',
                             date_serialization='datetime64[s] ISOT with seconds')
    write(path, plan)
    return plan


def run_case(count):
    repo, runtime, model = roots()
    plan = json.loads((OWN / PLAN).read_text())
    assert plan['probe_sha256'] == digest(__file__)
    assert digest(model / 'ranker.onnx') == MODEL and digest(model / 'metadata.json') == META
    for p, h in plan['source_sha256'].items():
        assert digest(repo / p) == h
    case = OWN / ('case-v2-' + str(count))
    case.mkdir(exist_ok=False)
    paths = source_paths(count)
    with tempfile.TemporaryDirectory(prefix='spaceapps-v4-density-') as scratch_name:
        scratch = Path(scratch_name)
        package = scratch / 'runtime/ml_inference'
        package.mkdir(parents=True)
        for p in (runtime / 'ml_inference').glob('*.py'):
            shutil.copyfile(p, package / p.name)
        images = np.random.default_rng(4200000 + count).normal(0., .05, (32, 512, 512)).astype(np.float32)
        for source in paths:
            for image, xy in zip(images, source):
                add_source(image, *xy)
        fixture = scratch / 'engineering.npz'
        dates = epoch_dates()
        np.savez_compressed(fixture, images=images, dates=dates,
                            observation_ids=np.asarray(['engineering-' + str(i) for i in range(32)]),
                            center_deg=np.asarray([20., 5.]), pixel_scale_arcsec=6.15)
        del images
        fixture_sha = digest(fixture)
        request = dict(schema_version=1, analysis_id='ENGINEERING-density-' + str(count), model_dir=str(model),
                       source=dict(kind='preset', preset_id='comet-d2', path=str(fixture)), options=plan['options'])
        request_path = case / 'request.json'
        write(request_path, request)
        env = {**os.environ, 'PYTHONPATH':str(scratch / 'runtime'), 'PYTHONDONTWRITEBYTECODE':'1',
               'OPENBLAS_NUM_THREADS':'1', 'OMP_NUM_THREADS':'1', 'MKL_NUM_THREADS':'1'}
        cpu = min(os.sched_getaffinity(0))
        started = time.perf_counter()
        observed_peak = 0
        interruption = None
        with (case / 'stdout.log').open('w') as stdout, (case / 'stderr.log').open('w') as stderr:
            child = subprocess.Popen([sys.executable, '-m', 'ml_inference', '--request', str(request_path),
                                      '--output', str(scratch / 'output')], cwd=scratch, env=env,
                                     stdout=stdout, stderr=stderr, start_new_session=True,
                                     preexec_fn=lambda: os.sched_setaffinity(0, {cpu}))
            while True:
                pid, status, usage = os.wait4(child.pid, os.WNOHANG)
                if pid:
                    child.returncode = os.waitstatus_to_exitcode(status)
                    break
                try:
                    state = Path('/proc', str(child.pid), 'status').read_text()
                    rss = next(int(row.split()[1]) * 1024 for row in state.splitlines() if row.startswith('VmRSS:'))
                    observed_peak = max(observed_peak, rss)
                except (FileNotFoundError, StopIteration):
                    pass
                elapsed = time.perf_counter() - started
                if interruption is None and (observed_peak >= plan['observed_rss_stop_bytes'] or elapsed >= plan['timeout_seconds']):
                    interruption = 'observed_rss_stop' if observed_peak >= plan['observed_rss_stop_bytes'] else 'timeout_stop'
                    os.killpg(child.pid, signal.SIGKILL)
                time.sleep(plan['rss_poll_seconds'])
        elapsed = time.perf_counter() - started
        result_path = scratch / 'output/result.json'
        result = json.loads(result_path.read_text()) if result_path.exists() else None
        if result is not None:
            shutil.copyfile(result_path, case / 'result.json')
        resources = []
        if result is not None and 'error' not in result:
            assert result['model']['sha256'] == MODEL
            assert len(result['frames']) == 32
            assert all((f['width'], f['height']) == (512, 512) for f in result['frames'])
            for row in result['resources']:
                p = scratch / 'output' / row['name']
                resources.append(dict(name=row['name'], sha256=digest(p), bytes=p.stat().st_size))
        proof = dict(case=count, engineering_sources=count, shape=plan['shape'], plan_sha256=digest(OWN / PLAN),
                     probe_sha256=digest(__file__), fixture_sha256=fixture_sha, fixture_bytes=fixture.stat().st_size,
                     request_sha256=digest(request_path), model_sha256=MODEL, metadata_sha256=META,
                     source_sha256=plan['source_sha256'], cpu_affinity=[cpu], math_threads=1,
                     elapsed_seconds=elapsed, child_user_seconds=usage.ru_utime, child_system_seconds=usage.ru_stime,
                     child_maxrss_mib=usage.ru_maxrss / 1024, observed_peak_rss_mib=observed_peak / 1024**2,
                     exit_code=child.returncode, monitor_interruption=interruption,
                     status='MONITOR_INTERRUPTED' if interruption else ('CLI_SUCCESS' if result is not None and 'error' not in result and child.returncode == 0 else 'CLI_ERROR'),
                     error=None if result is None else result.get('error'),
                     candidate_count=None if result is None or 'error' in result else len(result['candidates']),
                     warnings=[] if result is None else result.get('warnings', []),
                     settings=None if result is None else result.get('settings'),
                     resources=resources, temporary_fixtures_deleted_after_case=True,
                     limits='Local child wait4 RSS and sampled monitor only; NOT hard cgroup/OOM proof; no recovery or sensitivity measurement')
        assert digest(fixture) == fixture_sha
        for p, h in plan['source_sha256'].items():
            assert digest(repo / p) == h
        assert digest(model / 'ranker.onnx') == MODEL and digest(model / 'metadata.json') == META
    write(case / 'proof.json', proof)
    print(json.dumps({k:proof[k] for k in ['case', 'status', 'elapsed_seconds', 'child_maxrss_mib', 'exit_code', 'error', 'candidate_count']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--declare', action='store_true')
    parser.add_argument('--case', type=int, choices=COUNTS)
    args = parser.parse_args()
    if args.declare:
        declare()
    elif args.case is not None:
        run_case(args.case)
    else:
        parser.error('Choose --declare or one fixed --case')
