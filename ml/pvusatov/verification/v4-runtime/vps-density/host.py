"""Root coordinator for an isolated, fixed-code VPS density resource probe."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

BASE = Path('/opt/spaceapps/ml-pvusatov-v4-probe')
ARCHIVE = BASE / 'density-code-20261115.tar.gz'
CODE = BASE / 'density-code-20261115'
OUTPUT = BASE / 'evidence-density-20261115'
NAME = 'spaceapps-v4-probe-density-20261115'
IMAGE = 'spaceapps-ml-v4-deps-probe:20261115'
EXPECTED_IMAGE = 'sha256:8df7927bd71083a8419454906591d25d1e203b73a84608e2bce1e941da352573'
digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    assert digest(ARCHIVE) == 'c6ee4b38cda56c07c08193dffa086e82de487d8e31706352c5ffb3a66c5d5233'
    assert subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', IMAGE], text=True).strip() == EXPECTED_IMAGE
    CODE.mkdir()
    OUTPUT.mkdir()
    os.chown(OUTPUT, 10001, 10001)
    with tarfile.open(ARCHIVE, 'r:gz') as tar:
        tar.extractall(CODE, filter='data')
    manifest = CODE / 'code-manifest.json'
    assert digest(manifest) == '770a8b0c08c51947b38c111edfa61ef762ef030f6555540c6fa8eb17c55f5152'
    inputs = json.loads(manifest.read_text())['files']
    for row in inputs:
        assert digest(CODE / row['path']) == row['sha256']
    args = ['docker', 'create', '--name', NAME, '--cpus', '1', '--memory', '1g', '--memory-swap', '1g',
            '--pids-limit', '64', '--network', 'none', '--read-only', '--no-healthcheck',
            '--tmpfs', '/tmp:rw,size=512m,mode=1777',
            '--mount', 'type=bind,src=' + str(BASE / 'bundle-v3') + ',dst=/probe,readonly',
            '--mount', 'type=bind,src=' + str(CODE) + ',dst=/density,readonly',
            '--mount', 'type=bind,src=' + str(OUTPUT) + ',dst=/evidence',
            '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'OPENBLAS_NUM_THREADS=1',
            '--env', 'OMP_NUM_THREADS=1', '--env', 'MKL_NUM_THREADS=1',
            '--entrypoint', '/opt/inference-venv/bin/python', IMAGE,
            '/density/portable.py', '--runtime', '/probe/inference', '--model-dir', '/probe/inference/models',
            '--output', '/evidence/density']
    subprocess.run(args, check=True, stdout=subprocess.PIPE, text=True)
    subprocess.run(['docker', 'start', NAME], check=True, stdout=subprocess.PIPE, text=True)
    # Read actual cgroup files while the wrapper/worker is alive. Linux has a
    # private cgroup namespace here, so these describe this container only.
    reader = ('import json,pathlib; p=pathlib.Path("/sys/fs/cgroup");'
              'print(json.dumps({n:(p/n).read_text() for n in '
              '["memory.max","memory.swap.max","cpu.max","memory.events","memory.peak"]}))')
    before = json.loads(subprocess.check_output(['docker', 'exec', NAME, '/opt/inference-venv/bin/python', '-c', reader], text=True))
    assert before['memory.max'].strip() == str(1024**3)
    assert before['memory.swap.max'].strip() == '0'
    assert before['cpu.max'].strip() == '100000 100000'
    waited = subprocess.run(['docker', 'wait', NAME], capture_output=True, text=True, timeout=1020)
    inspect = json.loads(subprocess.check_output(['docker', 'inspect', NAME], text=True))[0]
    logs = subprocess.run(['docker', 'logs', NAME], capture_output=True, text=True)
    (OUTPUT / 'stdout.log').write_text(logs.stdout)
    (OUTPUT / 'stderr.log').write_text(logs.stderr)
    proof = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(), container=NAME,
                 host_coordinator_sha256=digest(__file__), input_archive_sha256=digest(ARCHIVE),
                 code_manifest_sha256=digest(manifest), image_id=inspect['Image'],
                 state={key: inspect['State'][key] for key in ('Status', 'Running', 'OOMKilled', 'ExitCode', 'StartedAt', 'FinishedAt')},
                 limits={key: inspect['HostConfig'][key] for key in ('Memory', 'MemorySwap', 'NanoCpus', 'PidsLimit', 'NetworkMode', 'ReadonlyRootfs')},
                 cgroup_at_start=before, docker_wait_stdout=waited.stdout.strip(),
                 mounts=[{key: row.get(key) for key in ('Type', 'Destination', 'RW')} for row in inspect['Mounts']],
                 production_services_modified=False)
    receipt = OUTPUT / 'density/portable-receipt.json'
    if receipt.exists():
        proof['portable_receipt'] = json.loads(receipt.read_text())
        proof['portable_receipt_sha256'] = digest(receipt)
    for row in inputs:
        assert digest(CODE / row['path']) == row['sha256']
    (OUTPUT / 'host-proof.json').write_text(json.dumps(proof, indent=2, allow_nan=False) + '\n')
    print(json.dumps(proof, indent=2))
    assert waited.returncode == 0 and waited.stdout.strip() == '0', 'probe process failed'
    assert not inspect['State']['OOMKilled'] and inspect['State']['ExitCode'] == 0, 'probe container failed'
    assert receipt.exists(), 'all planned cases did not produce the bounded wrapper receipt'


if __name__ == '__main__':
    main()
