"""Remote read-only inspection and at most three sequential ephemeral probes.

Read JSON config from stdin. Never exec into or modify a production container.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys
import time
import uuid


def docker_json(*args):
    return json.loads(subprocess.check_output(['docker', *args], text=True))


def inspect_backend():
    container = docker_json('inspect', 'spaceapps-api-1')[0]
    assert container['State']['Running'], 'Backend is not running'
    return dict(container_id=container['Id'], image_id=container['Image'],
                revision=container['Config']['Labels'].get('org.opencontainers.image.revision'),
                health=container['State'].get('Health', {}).get('Status'))


def main():
    config = json.load(sys.stdin)
    source = config['container_probe_source']
    assert hashlib.sha256(source.encode()).hexdigest() == config['container_probe_sha256']
    presets = config['presets']
    assert 1 <= len(presets) <= 3
    assert all(p in ['comet-d6', 'comet-d2', 'vesta-d3'] for p in presets)
    before = inspect_backend()
    pinned_image = before['image_id']
    image = docker_json('image', 'inspect', pinned_image)[0]
    assert image['Id'] == pinned_image
    revision_tag = docker_json('image', 'inspect', 'spaceapps-api:' + before['revision'])[0]['Id']
    assert revision_tag == pinned_image, 'Running image and exact revision tag differ'
    run_id = uuid.uuid4().hex[:12]
    results = []
    for index, preset in enumerate(presets, 1):
        name = f'spaceapps-v2-benchmark-{run_id}-{index}'
        command = ['docker', 'run', '--rm', '--name', name,
                   '--label', 'spaceapps.benchmark.run=' + run_id,
                   '--network', 'none', '--read-only',
                   '--tmpfs', '/tmp:rw,nosuid,nodev,size=268435456,mode=1777',
                   '--cpus=1', '--memory=1g', '--pids-limit=128',
                   '--entrypoint', '/opt/inference-venv/bin/python',
                   pinned_image, '-u', '-c', source, '--preset', preset]
        started = time.perf_counter()
        timed_out = False
        try:
            completed = subprocess.run(command, text=True, capture_output=True, timeout=180)
            stdout, stderr, returncode = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as error:
            timed_out = True
            stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or '')
            stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else (error.stderr or '')
            returncode = None
        finally:
            remaining = subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$'], text=True).strip()
            forced_cleanup = bool(remaining)
            if remaining:
                subprocess.run(['docker', 'rm', '-f', name], capture_output=True, text=True, check=True)
        try:
            payload = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            payload = None
        results.append(dict(index=index, preset=preset, container_name=name,
                            docker_wall_seconds=time.perf_counter() - started,
                            docker_returncode=returncode, docker_timed_out=timed_out,
                            forced_cleanup=forced_cleanup, container_probe=payload,
                            docker_stderr=stderr[:4096], unparsed_stdout=stdout[:4096] if payload is None else None))
        if timed_out or returncode != 0 or payload is None or not payload['success']:
            break
    leftovers = subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'label=spaceapps.benchmark.run=' + run_id], text=True).strip()
    assert not leftovers, 'Ephemeral benchmark container was not cleaned up'
    after = inspect_backend()
    report = dict(schema_version=1, checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  run_id=run_id, backend_before=before, backend_after=after,
                  pinned_image_id=pinned_image, image_created=image['Created'],
                  image_revision=image['Config']['Labels'].get('org.opencontainers.image.revision'),
                  requested_limits=dict(cpus=1, memory_bytes=1073741824, pids=128, tmpfs_tmp_bytes=268435456,
                      network='none', read_only_root=True, remove_after_exit=True),
                  probe_source_sha256=config['container_probe_sha256'],
                  planned_presets=presets, executed_probes=len(results), probes=results,
                  leftover_containers_for_run=0, production_exec_or_service_changes_performed=False,
                  host_data_bind_mounts_requested=False, candidate_uploaded_or_fitted=False)
    print(json.dumps(report, indent=2, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
