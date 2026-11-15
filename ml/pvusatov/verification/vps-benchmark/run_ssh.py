"""Run the bounded v2 benchmark over strict SSH; credentials stay external."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--key', default='/home/usatovpavel/.ssh/spaceapps-1gb-admin-20261115')
    parser.add_argument('--known-hosts', default='/home/usatovpavel/.local/state/spaceapps-migration-20261115-1gb/known_hosts')
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    source = (directory / 'container_probe.py').read_text()
    remote = (directory / 'remote_runner.py').read_text()
    config = dict(container_probe_source=source, container_probe_sha256=hashlib.sha256(source.encode()).hexdigest(),
                  presets=['comet-d6', 'comet-d2', 'vesta-d3'])
    command = ['ssh', '-T', '-i', args.key, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + args.known_hosts,
               '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=4',
               'root@146.103.122.246', 'python3 -c ' + shlex.quote(remote)]
    completed = subprocess.run(command, input=json.dumps(config), text=True, capture_output=True, timeout=600)
    if completed.returncode:
        raise SystemExit('SSH benchmark failed: ' + completed.stderr[:4096])
    report = json.loads(completed.stdout)
    report['driver_source_sha256'] = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                                      for name in ['container_probe.py', 'remote_runner.py', 'run_ssh.py']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(output=str(args.output), image_id=report['pinned_image_id'],
                         executed_probes=report['executed_probes'],
                         success=all(p['container_probe'] and p['container_probe']['success'] for p in report['probes']),
                         leftover_containers=report['leftover_containers_for_run']), indent=2))


if __name__ == '__main__':
    main()
