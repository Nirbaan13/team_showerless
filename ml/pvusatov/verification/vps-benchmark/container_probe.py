"""Measure one packaged real preset inside a fresh constrained container."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

EXPECTED_MODEL = 'dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9'


def cgroup(name):
    path = Path('/sys/fs/cgroup') / name
    return path.read_text().strip() if path.is_file() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=['comet-d6', 'comet-d2', 'vesta-d3'], required=True)
    args = parser.parse_args()
    root = Path('/app/inference')
    digest = hashlib.sha256((root / 'models/ranker.onnx').read_bytes()).hexdigest()
    assert digest == EXPECTED_MODEL, 'Benchmark requires immutable deployed v2'
    metadata = json.loads((root / 'models/metadata.json').read_text())
    assert metadata['sha256'] == digest
    presets = json.loads((root / 'fixtures/presets.json').read_text())
    preset = next(row for row in presets if row['id'] == args.preset)
    assert hashlib.sha256((root / 'fixtures' / preset['fixture']).read_bytes()).hexdigest() == preset['sha256']
    limits = {name: cgroup(name) for name in ['cpu.max', 'memory.max', 'pids.max']}
    assert limits['memory.max'] == '1073741824'
    assert limits['pids.max'] == '128'
    assert limits['cpu.max'] and limits['cpu.max'].split()[0] == limits['cpu.max'].split()[1]
    mountinfo = Path('/proc/self/mountinfo').read_text().splitlines()
    tmp_mount = [line for line in mountinfo if line.split()[4] == '/tmp']
    assert len(tmp_mount) == 1 and ' - tmpfs ' in tmp_mount[0]
    assert 'size=262144k' in tmp_mount[0] or 'size=256m' in tmp_mount[0]
    with tempfile.TemporaryDirectory(prefix='spaceapps-v2-vps-', dir='/tmp') as temporary:
        folder = Path(temporary)
        request = folder / 'request.json'
        output = folder / 'output'
        request.write_text(json.dumps(dict(schema_version=1, analysis_id='vps-v2-benchmark',
                                          source=dict(kind='preset', preset_id=args.preset), options={})))
        command = [sys.executable, '-m', 'ml_inference', '--request', str(request), '--output', str(output)]
        started = time.perf_counter()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   env=dict(os.environ, PYTHONPATH=str(root)), cwd='/tmp')
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate()
        elapsed = time.perf_counter() - started
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        result_path = output / 'result.json'
        result = json.loads(result_path.read_text()) if result_path.is_file() else None
        success = not timed_out and process.returncode == 0 and result is not None and not result.get('error')
        if success:
            assert result['model']['sha256'] == digest
            assert len(result['frames']) >= 3
            assert result['candidates'], 'Preset produced no computed tracks'
            for row in result['resources']:
                assert Path(row['name']).name == row['name']
                assert (output / row['name']).is_file()
            assert any(candidate.get('score') is not None for candidate in result['candidates'])
        report = dict(schema_version=1, measured_at_utc=datetime.now(timezone.utc).isoformat(),
                      preset=args.preset, preset_fixture_sha256=preset['sha256'],
                      model_id=metadata['model_id'], model_sha256=digest,
                      python_version=sys.version, versions={name: importlib.metadata.version(name)
                          for name in ['numpy', 'scipy', 'astropy', 'onnxruntime', 'pillow']},
                      success=success, returncode=process.returncode, timed_out=timed_out,
                      child_wall_seconds=elapsed,
                      child_resource=dict(max_rss_kib=usage.ru_maxrss, max_rss_bytes=usage.ru_maxrss * 1024,
                          user_cpu_seconds=usage.ru_utime, system_cpu_seconds=usage.ru_stime,
                          minor_faults=usage.ru_minflt, major_faults=usage.ru_majflt,
                          input_blocks=usage.ru_inblock, output_blocks=usage.ru_oublock,
                          voluntary_context_switches=usage.ru_nvcsw, involuntary_context_switches=usage.ru_nivcsw),
                      measurement_scope='Linux RUSAGE_CHILDREN for the sole inference Python subprocess; not SSH or Docker CLI RSS',
                      cgroup_limits=limits, cgroup_memory_peak_bytes=cgroup('memory.peak'), tmp_mount=tmp_mount,
                      frames=len(result['frames']) if success else None,
                      candidates=len(result['candidates']) if success else None,
                      registered_shapes=[[row['width'], row['height']] for row in result['frames']] if success else None,
                      output_resource_count=len(result['resources']) if success else None,
                      output_resource_bytes=sum((output / row['name']).stat().st_size for row in result['resources']) if success else None,
                      settings=result.get('settings') if success else None,
                      warnings=result.get('warnings') if success else None,
                      error=result.get('error') if result else 'No result JSON',
                      stdout=stdout[:4096], stderr=stderr[:4096], fitting_performed=False,
                      inputs='Packaged known-object development presets only; no production data or final fields')
        print(json.dumps(report, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
