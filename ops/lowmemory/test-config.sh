#!/usr/bin/env bash
# Validate effective release topology locally; no daemon or host mutations.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
python3 - "$repo_root" <<'PY'
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
env = os.environ.copy()
env.update(APP_IMAGE='spaceapps-api:policy-check', ML_IMAGE='spaceapps-ml:policy-check')


def config(base, override=None):
    command = ['docker', 'compose', '--file', str(root / base)]
    if override:
        command.extend(['--file', str(root / override)])
    return json.loads(subprocess.check_output(command + ['config', '--format', 'json'], env=env))


for base, override, expected_services, scratch in (
    ('compose.yaml', 'ops/lowmemory/api.override.yaml', {'api', 'pipeline'},
     {'api': '/opt/spaceapps/runtime-tmp/api', 'pipeline': '/opt/spaceapps/runtime-tmp/pipeline'}),
    ('ops/ml/compose.yaml', 'ops/lowmemory/ml.override.yaml', {'ml-inference'},
     {'ml-inference': '/opt/spaceapps-ml/runtime-tmp'}),
):
    before = config(base)
    after = config(base, override)
    if 'api' in after['services']:
        assert after['services']['api']['environment']['PROCESSING_CONCURRENCY'] == '1'
    assert set(after['services']) == expected_services
    assert before.get('volumes') == after.get('volumes'), 'persistent volume identities changed'
    for name, original in before['services'].items():
        effective = after['services'][name]
        allowed = {'environment', 'tmpfs', 'volumes', 'mem_limit', 'memswap_limit'}
        assert {k: v for k, v in original.items() if k not in allowed} == {
            k: v for k, v in effective.items() if k not in allowed
        }, f'{name}: image, routing or release behavior changed'
        assert not effective.get('tmpfs'), f'{name}: /tmp still consumes RAM'
        assert 0 < int(effective['mem_limit']) < int(effective['memswap_limit'])
        mounts = {mount['target']: mount for mount in effective['volumes']}
        assert mounts['/tmp']['type'] == 'bind'
        assert mounts['/tmp']['source'] == scratch[name]
        # Compose JSON omits false fields when normalizing long bind syntax.
        assert mounts['/tmp']['bind'].get('create_host_path', False) is False
        for mount in original['volumes']:
            assert mounts[mount['target']] == mount, f'{name}: persistent mount changed'
        for key, value in original.get('environment', {}).items():
            if key != 'IRSA_MIRROR_MAX_INDEX_BYTES':
                assert effective['environment'][key] == value, f'{name}: release environment changed'
print('Low-memory API/pipeline/ML Compose config validated; persistent mounts and release topology retained')
PY
