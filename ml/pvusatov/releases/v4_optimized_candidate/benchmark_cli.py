"""Bounded paired full-CLI benchmark; fixed real presets and engineering inputs only.

Run with the shared UtilsAI interpreter. No FINAL/holdout/model-selection reads.
Large NPZ/JSON/PNG outputs remain outside Git in --scratch.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import numpy as np

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.with_name('v4')
REPO = HERE.parents[3]
LIMIT_RSS = 2 * 1024**3
TIMEOUT = 300
CPU = max(os.sched_getaffinity(0))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def scientific(value):
    value = json.loads(json.dumps(value))
    value['provenance'].pop('feature_producer', None)
    return value


def run_cli(runtime, request, output):
    env = {**os.environ, 'PYTHONPATH': str(runtime), 'PYTHONDONTWRITEBYTECODE':'1',
           'OPENBLAS_NUM_THREADS':'1', 'OMP_NUM_THREADS':'1', 'MKL_NUM_THREADS':'1', 'NUMEXPR_NUM_THREADS':'1'}
    start = time.perf_counter(); peak = 0; interruption = None
    with output.with_suffix('.stdout').open('w') as stdout, output.with_suffix('.stderr').open('w') as stderr:
        child = subprocess.Popen([sys.executable, '-m', 'ml_inference', '--request', str(request), '--output', str(output)],
                                 cwd=output.parent, env=env, stdout=stdout, stderr=stderr,
                                 start_new_session=True, preexec_fn=lambda: os.sched_setaffinity(0, {CPU}))
        while True:
            pid, status, usage = os.wait4(child.pid, os.WNOHANG)
            if pid:
                child.returncode = os.waitstatus_to_exitcode(status)
                break
            try:
                status_text = Path('/proc', str(child.pid), 'status').read_text()
                rss = next(int(s.split()[1])*1024 for s in status_text.splitlines() if s.startswith('VmRSS:'))
                peak = max(peak, rss)
            except (FileNotFoundError, StopIteration):
                pass
            elapsed = time.perf_counter()-start
            if interruption is None and (peak >= LIMIT_RSS or elapsed >= TIMEOUT):
                interruption = 'rss_stop' if peak >= LIMIT_RSS else 'timeout_stop'
                os.killpg(child.pid, signal.SIGKILL)
            time.sleep(.02)
    return dict(wall_seconds=time.perf_counter()-start, cpu_seconds=usage.ru_utime+usage.ru_stime,
                user_seconds=usage.ru_utime, system_seconds=usage.ru_stime, maxrss_mib=usage.ru_maxrss/1024,
                sampled_peak_rss_mib=peak/1024**2, exit_code=child.returncode, interruption=interruption)


def engineering(scratch):
    probe_path = REPO/'ml/pvusatov/verification/v4-runtime/density-stress/probe.py'
    spec = importlib.util.spec_from_file_location('fixed_density_generator', probe_path)
    probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
    paths = probe.source_paths(8)
    images = np.random.default_rng(4200008).normal(0., .05, (32,512,512)).astype(np.float32)
    for source in paths:
        for image, xy in zip(images, source):
            probe.add_source(image, *xy)
    path = scratch/'fixed-engineering-density8.npz'
    np.savez_compressed(path, images=images, dates=probe.epoch_dates(),
                        observation_ids=np.asarray(['engineering-'+str(i) for i in range(32)]),
                        center_deg=np.asarray([20.,5.]),pixel_scale_arcsec=6.15)
    return path, digest(probe_path), hashlib.sha256(images.tobytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch', type=Path, required=True)
    args = parser.parse_args(); scratch = args.scratch.resolve(); scratch.mkdir(parents=True, exist_ok=False)
    assert not scratch.is_relative_to(REPO)
    before = json.loads((HERE/'source-inputs-before.json').read_text())
    assert all(digest(REPO/p) == h for p,h in before.items())
    candidate_before = {str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*')
                        if p.is_file() and '__pycache__' not in str(p) and p.suffix in ('.py','.onnx','.npz')}
    engineering_path, generator_sha, image_sha = engineering(scratch)
    empty = scratch/'empty.npz'
    np.savez_compressed(empty, images=np.zeros((3,24,24)), dates=np.array(['2025-01-01T00:00:00','2025-01-01T01:00:00','2025-01-01T02:00:00']),
                        observation_ids=np.array(['empty-a','empty-b','empty-c']),center_deg=np.array([20.,5.]),pixel_scale_arcsec=6.15)
    cases=[(preset,ORIGINAL/'runtime/fixtures'/(preset+'.npz'),preset) for preset in ['comet-d2','comet-d6','vesta-d3','vesta-d6']]
    cases += [('engineering-density8',engineering_path,'comet-d2'),('empty-negative',empty,'comet-d2')]
    inputs={str(path):digest(path) for _,path,_ in cases}
    report=dict(status='unpromoted_performance_candidate', benchmark_source_sha256=digest(__file__),
                cpu_affinity=[CPU], math_threads=1, rss_stop_bytes=LIMIT_RSS, timeout_seconds=TIMEOUT,
                resource_statement='wait4 maximum RSS plus sampled RSS termination; not a hard cgroup/allocation cap',
                runtime_environment=dict(python=sys.version,interpreter=sys.executable),
                engineering=dict(shape=[32,512,512],sources=8,seed=4200008,generator_sha256=generator_sha,image_sha256=image_sha),
                source_inputs_before=before, candidate_sources_before=candidate_before,input_sha256=inputs,
                design='3 paired alternating repetitions per case, reference/candidate then candidate/reference then reference/candidate; same model and input path',
                cases=[])
    for name,fixture,preset in cases:
        row=dict(case=name,input_sha256=digest(fixture),repetitions=[])
        request=dict(schema_version=1,analysis_id='candidate-cli-'+name,model_dir=str(ORIGINAL/'model'),
                     source=dict(kind='preset',preset_id=preset,path=str(fixture)))
        if name=='engineering-density8':request['options']=dict(min_snr=4.,max_candidates=100,max_peaks=100)
        request_path=scratch/(name+'-request.json');write(request_path,request)
        for repeat in range(3):
            pair={}; paths={}; order=('reference','candidate') if repeat%2==0 else ('candidate','reference')
            for implementation in order:
                runtime=(ORIGINAL if implementation=='reference' else HERE)/'runtime'
                out=scratch/(name+'-'+str(repeat)+'-'+implementation)
                pair[implementation]=run_cli(runtime,request_path,out); paths[implementation]=out
                assert pair[implementation]['exit_code']==0, pair
                assert pair[implementation]['interruption'] is None
                assert pair[implementation]['maxrss_mib']<2048
            a=json.loads((paths['reference']/'result.json').read_text());b=json.loads((paths['candidate']/'result.json').read_text())
            assert scientific(a)==scientific(b), 'scientific JSON differs: '+name
            imgs=sorted(p.name for p in paths['reference'].glob('*.png'))
            assert imgs==sorted(p.name for p in paths['candidate'].glob('*.png'))
            for png in imgs:assert (paths['reference']/png).read_bytes()==(paths['candidate']/png).read_bytes(),png
            pair.update(repetition=repeat,execution_order=list(order),scientific_json_exact=True,
                        candidate_scores_ids_order_resources_exact=True,all_png_bytes_exact=True,png_count=len(imgs),
                        scientific_sha256=hashlib.sha256(json.dumps(scientific(a),sort_keys=True).encode()).hexdigest(),
                        candidate_count=len(a['candidates']),linked_tracks=a['comparison']['leave_one_out_count'],
                        resource_sha256={png:digest(paths['reference']/png) for png in imgs})
            row['repetitions'].append(pair)
            print(name,repeat,'reference',round(pair['reference']['wall_seconds'],3),'candidate',round(pair['candidate']['wall_seconds'],3),'png',len(imgs),flush=True)
            write(scratch/'partial-benchmark.json',report|dict(cases=report['cases']+[row]))
        row['median']={impl:{metric:float(np.median([p[impl][metric] for p in row['repetitions']]))
                             for metric in ('wall_seconds','cpu_seconds','maxrss_mib')} for impl in ('reference','candidate')}
        row['whole_cli_wall_speedup']=row['median']['reference']['wall_seconds']/row['median']['candidate']['wall_seconds']
        row['whole_cli_cpu_speedup']=row['median']['reference']['cpu_seconds']/row['median']['candidate']['cpu_seconds']
        row['slower_or_equal_wall']=row['whole_cli_wall_speedup']<=1.
        report['cases'].append(row)
    assert all(digest(REPO/p)==h for p,h in before.items())
    assert all(digest(HERE/p)==h for p,h in candidate_before.items())
    assert all(digest(path)==h for path,h in inputs.items())
    report['source_model_input_hashes_unchanged']=True
    report['scope']='Local paired engineering evidence only; does not establish global equivalence, new-architecture benefit, or holdout sensitivity. No promotion.'
    write(HERE/'benchmark-cli-evidence.json',report)
    write(scratch/'benchmark-complete.json',report)


if __name__=='__main__':main()
