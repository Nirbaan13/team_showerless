"""Run immutable ML inputs inside an externally constrained Docker cgroup.

This script does not operate Docker, alter services or fetch inputs. The host
coordinator supplies a read-only /probe bundle and writable /evidence folder.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

BASE = Path('/probe')
EXPECTED_MODEL = 'c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cgroup():
    root = Path('/sys/fs/cgroup')
    return {name:(root / name).read_text().strip()
            for name in ('memory.max', 'memory.swap.max', 'memory.peak', 'memory.events', 'cpu.max', 'cpu.stat')}


def run(mode, destination):
    destination = Path(destination)
    if destination.exists(): raise ValueError('probe output must be new')
    manifest = json.loads((BASE / 'bundle-manifest.json').read_text())
    for row in manifest['files']:
        path = (BASE / row['path']).resolve()
        if not path.is_relative_to(BASE) or digest(path) != row['sha256']:
            raise ValueError('probe bundle changed: ' + row['path'])
    limits_before = cgroup()
    if (limits_before['memory.max'] != str(1024**3) or limits_before['memory.swap.max'] != '0'
            or limits_before['cpu.max'] != '100000 100000'):
        raise ValueError('required hard one-CPU/one-GiB/no-swap cgroup is missing')
    inference = BASE / 'inference'; model = inference / 'models'
    if digest(model / 'ranker.onnx') != EXPECTED_MODEL: raise ValueError('wrong selected graph')
    import sitecustomize
    if not any(type(finder).__name__ == '_NoFitting' for finder in sys.meta_path):
        raise ValueError('fitting import guard was not installed at interpreter startup')
    destination.mkdir(parents=True)
    started = time.perf_counter(); results = []
    if mode == 'maximum':
        proof_path = destination / 'maximum-rss-raw.json'
        command = [sys.executable, str(inference / 'measure_maximum.py'), '--model-dir', str(model),
                   '--output', str(proof_path), '--timeout-seconds', '600']
        child = subprocess.run(command, cwd=inference, capture_output=True, text=True, timeout=750)
        if child.returncode: raise RuntimeError('maximum CLI probe failed: ' + child.stderr[-4000:])
        results.append(dict(kind='maximum', raw_proof=json.loads(proof_path.read_text()),
                            raw_proof_sha256=digest(proof_path), stdout=child.stdout.splitlines()))
    elif mode == 'presets':
        for identity in ('comet-d2', 'comet-d6', 'vesta-d3', 'vesta-d6'):
            request = dict(schema_version=1, analysis_id='v4-hard-cgroup-' + identity, model_dir=str(model),
                           source=dict(kind='preset', preset_id=identity, path=str(inference / 'fixtures' / (identity + '.npz'))))
            request_path = destination / (identity + '-request.json')
            request_path.write_text(json.dumps(request))
            output = destination / identity
            child = subprocess.run([sys.executable, '-m', 'ml_inference', '--request', str(request_path),
                                    '--output', str(output)], cwd=inference, capture_output=True, text=True, timeout=180)
            if child.returncode: raise RuntimeError('real preset failed: ' + identity + child.stderr[-2000:])
            result = json.loads((output / 'result.json').read_text())
            if 'error' in result or result['model']['sha256'] != EXPECTED_MODEL:
                raise ValueError('real inference did not return the selected model')
            from PIL import Image
            for item in result['resources']:
                resource = output / item['name']
                if not resource.is_file(): raise ValueError('missing PNG')
                with Image.open(resource) as image: image.verify()
            results.append(dict(preset=identity, candidates=len(result['candidates']), pngs=len(result['resources']),
                                result_sha256=digest(output / 'result.json'), model=result['model'],
                                score_kinds=sorted({row['score_kind'] for row in result['candidates']})))
    elif mode == 'native-coverage':
        request_path = BASE/'coverage-fixture/request.json'
        output = destination/'native-coverage'
        child = subprocess.run([sys.executable, '-m', 'ml_inference', '--request', str(request_path),
                                '--output', str(output)], cwd=inference, capture_output=True, text=True, timeout=180)
        if child.returncode: raise RuntimeError('native coverage CLI failed: ' + child.stderr[-2000:])
        result = json.loads((output/'result.json').read_text())
        if ('error' in result or result['model']['sha256'] != EXPECTED_MODEL or len(result['frames']) != 4
                or result['frames'][1]['coverage_fraction'] != 0.
                or 'observations_without_usable_requested_coverage' not in result['warnings']
                or any(frame['coverage_fraction'] <= 0 for i, frame in enumerate(result['frames']) if i != 1)):
            raise ValueError('native empty epoch was dropped, fabricated or not explicitly reported')
        from PIL import Image
        for resource in result['resources']:
            with Image.open(output/resource['name']) as image: image.verify()
        with Image.open(output/result['frames'][1]['image_url']) as image:
            if image.getextrema() != (0, 0): raise ValueError('missing native coverage fabricated pixels')
        results.append(dict(kind='native-coverage', engineering_fixture=True, physical_epochs=4,
                            zero_coverage_epoch=1, retained_frame_ids=[frame['frame_id'] for frame in result['frames']],
                            pngs=len(result['resources']), result_sha256=digest(output/'result.json'), model=result['model']))
    else:
        raise ValueError('unknown constrained probe')
    limits_after = cgroup()
    events = dict(line.split() for line in limits_after['memory.events'].splitlines())
    if int(events.get('oom_kill', '0')) or int(events.get('oom', '0')):
        raise ValueError('hard-cgroup memory exhaustion occurred')
    if int(limits_after['memory.peak']) > 1024**3: raise ValueError('memory cgroup peak exceeds the limit')
    for row in manifest['files']:
        if digest(BASE / row['path']) != row['sha256']: raise ValueError('bundle mutated during constrained run')
    result = dict(schema_version=4, scope='isolated VPS Docker engineering gate; production service untouched',
                  mode=mode, model_sha256=EXPECTED_MODEL, probe_source_sha256=digest(__file__),
                  bundle_manifest_sha256=digest(BASE / 'bundle-manifest.json'),
                  python=sys.version.split()[0], versions={name:importlib.metadata.version(name)
                      for name in ('numpy', 'scipy', 'astropy', 'onnxruntime', 'onnx', 'pillow')},
                  elapsed_seconds=time.perf_counter() - started, cgroup_before=limits_before, cgroup_after=limits_after,
                  fitting_import_guard=dict(source_sha256=digest(inference / 'sitecustomize.py'),
                                            forbidden=sorted(sitecustomize.FORBIDDEN_FITTING_ROOTS)),
                  results=results, passes=True,
                  limitations=['engineering workload and fixed real presets, not worst possible candidate density',
                               'these resource and integration checks are separate from independent recovery validation'])
    path = destination / 'proof.json'; path.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(proof=str(path), sha256=digest(path), elapsed_seconds=result['elapsed_seconds'],
                          cgroup_peak_mib=int(limits_after['memory.peak']) / 1024**2)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=('maximum', 'presets', 'native-coverage'))
    parser.add_argument('--output', required=True)
    args = parser.parse_args(); run(args.mode, args.output)
