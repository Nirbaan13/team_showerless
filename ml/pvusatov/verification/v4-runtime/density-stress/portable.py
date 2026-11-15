"""Translate the fixed local density probe to a read-only VPS runtime bundle.

Only filesystem roots/output placement change. Original source, case plan,
generator, options, wait4 accounting and stop limits remain byte-identical.
The host owns Docker/cgroup validation; this process never operates Docker.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    runtime, model, output = args.runtime.resolve(), args.model_dir.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError('New output directory required')
    plan = json.loads((source / 'plan-v2.json').read_text())
    if sha(source / 'probe.py') != plan['probe_sha256']:
        raise ValueError('Original generator/runner source changed')
    if sha(model / 'ranker.onnx') != plan['model_sha256'] or sha(model / 'metadata.json') != plan['metadata_sha256']:
        raise ValueError('Selected artifact changed')
    expected = {Path(p).name:h for p, h in plan['source_sha256'].items()}
    actual = {p.name:sha(p) for p in (runtime / 'ml_inference').glob('*.py')}
    if actual != expected:
        raise ValueError('Runtime bundle source set/hash changed')
    # Single affinity also covers NumPy fixture generation in this process.
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if os.environ.get(key) != '1':
            raise ValueError('Launch with one math thread before Python imports')
    spec = importlib.util.spec_from_file_location('fixed_density_probe', source / 'probe.py')
    probe = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(probe)
    output.mkdir(parents=True)
    shutil.copyfile(source / 'plan-v2.json', output / 'plan-v2.json')
    with tempfile.TemporaryDirectory(prefix='density-root-translation-') as translated_name:
        translated = Path(translated_name)
        virtual = translated / 'ml/pvusatov/releases/v4'
        virtual.mkdir(parents=True)
        (virtual / 'runtime').symlink_to(runtime, target_is_directory=True)
        # Explicit root aliases affect only IO paths; run_case remains original.
        probe.OWN = output
        probe.roots = lambda: (translated, runtime, model)
        for count in probe.COUNTS:
            probe.run_case(count)
    rows = [json.loads((output / ('case-v2-' + str(n)) / 'proof.json').read_text()) for n in probe.COUNTS]
    receipt = dict(scope='Portable fixed engineering density probe, host cgroup proof remains external',
                   wrapper_sha256=sha(__file__), original_probe_sha256=sha(source / 'probe.py'),
                   plan_sha256=sha(source / 'plan-v2.json'), runtime=str(runtime), model_dir=str(model),
                   output=str(output), cpu_affinity=sorted(os.sched_getaffinity(0)), python=sys.version,
                   translated_logical_source_root='Temporary symlink aliases original plan repo-relative source paths to --runtime',
                   unchanged_generator_options_sources=True,
                   cases=[{k:r[k] for k in ('case', 'status', 'exit_code', 'error', 'elapsed_seconds',
                                             'child_maxrss_mib', 'monitor_interruption', 'fixture_sha256')} for r in rows])
    (output / 'portable-receipt.json').write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(receipt=str(output / 'portable-receipt.json'), sha256=sha(output / 'portable-receipt.json'))))


if __name__ == '__main__':
    main()
