"""Nonempty maximum-shape local RSS/one-CPU proof, not a cgroup deployment gate."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import numpy as np

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bounded_timeout(value):
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError('timeout seconds must be an integer1..900') from None
    if not 1 <= seconds <= 900:
        raise argparse.ArgumentTypeError('timeout seconds must be within1..900')
    return seconds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--timeout-seconds', type=bounded_timeout, default=240)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise ValueError('new immutable proof path required')
    model = Path(args.model_dir).resolve()
    source_hashes = {p.name:sha(p) for p in sorted((ROOT/'ml_inference').glob('*.py'))}
    selected = json.loads((model/'metadata.json').read_text())
    cpus = sorted(os.sched_getaffinity(0)); cpu = cpus[0]
    with tempfile.TemporaryDirectory(prefix='spaceapps-v4-maximum-runtime-') as scratch:
        scratch = Path(scratch)
        images = np.random.default_rng(0).normal(0.,.05,(32,512,512)).astype(np.float32)
        yy,xx = np.indices((512,512),dtype=float)
        for epoch,image in enumerate(images):
            kernel = np.exp(-((xx-(128+4*epoch))**2+(yy-256)**2)/(2*.8**2))
            kernel /= kernel.sum(); image += 50*kernel
        dates = (np.datetime64('2025-01-01T00:00:00') + np.arange(32)*np.timedelta64(1,'h')).astype(str)
        fixture = scratch/'maximum.npz'
        np.savez_compressed(fixture,images=images,dates=dates,observation_ids=np.asarray([f'e{i:02d}'for i in range(32)]),
            center_deg=np.asarray([20.,5.]),pixel_scale_arcsec=6.15)
        del images,xx,yy,kernel
        request = dict(schema_version=1,analysis_id='maximum-nonempty-runtime',model_dir=str(model),
            source=dict(kind='preset',preset_id='comet-d2',path=str(fixture)),
            options=dict(min_snr=10.,max_candidates=3))
        request_path = scratch/'request.json';request_path.write_text(json.dumps(request))
        env = {**os.environ,'PYTHONPATH':str(ROOT),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
        started = time.perf_counter()
        child = subprocess.run([sys.executable,'-m','ml_inference','--request',str(request_path),'--output',str(scratch/'out')],
            env=env,cwd=scratch,capture_output=True,text=True,timeout=args.timeout_seconds,
            preexec_fn=lambda:os.sched_setaffinity(0,{cpu}))
        elapsed = time.perf_counter()-started
        result = json.loads((scratch/'out/result.json').read_text())
        if child.returncode or 'error' in result or not result['candidates']:
            raise RuntimeError('nonempty maximum runtime failed: '+str(result.get('error'))+' '+child.stderr)
        if len(result['frames']) != 32 or any((f['width'],f['height']) != (512,512)for f in result['frames']):
            raise ValueError('maximum shape silently changed')
        if not any(len(c['detections']) == 32 for c in result['candidates']):
            raise ValueError('nonempty32-epoch measured track not present')
        if source_hashes != {p.name:sha(p)for p in sorted((ROOT/'ml_inference').glob('*.py'))}:
            raise ValueError('runtime sources changed during measurement')
        rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/1024
        proof = dict(designation='LOCAL nonempty32x512x512 inference RSS; no hard memory cgroup claim',
            source_sha256=source_hashes,measurement_source_sha256=sha(Path(__file__)),model_sha256=selected['sha256'],
            model_metadata_sha256=sha(model/'metadata.json'),shape=[32,512,512],cpu_affinity=[cpu],
            worker_peak_rss_mib=rss,below1gib=rss<1024,elapsed_seconds=elapsed,timeout_seconds=args.timeout_seconds,
            runtime_model=result['model'],settings=result['settings'],candidate_count=len(result['candidates']),
            detection_counts=[len(c['detections'])for c in result['candidates']],resources=len(result['resources']),
            stderr_progress=child.stderr.splitlines(),
            limitations=['one measured controlled maximum-shape track, not worst possible candidate density',
                'RSS measured, no hard1GiB memory cgroup; actual deployment gate remains separate',
                'engineering noise/target units, no native/instrument sensitivity claim'])
        if rss >= 1024:
            raise RuntimeError('measured runtime exceeds1GiB RSS: '+str(rss))
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary = output.with_suffix(output.suffix+'.tmp')
    temporary.write_text(json.dumps(proof,indent=2,allow_nan=False)+'\n');temporary.replace(output)
    print(json.dumps(dict(output=str(output),sha256=sha(output),rss_mib=rss,elapsed_seconds=elapsed)))


if __name__ == '__main__':
    main()
