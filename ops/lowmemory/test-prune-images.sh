#!/usr/bin/env bash
# Exercise retention against a Docker boundary double; never contact a daemon.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
python3 - "$repo_root" <<'PY'
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(sys.argv.pop())
SHA = {letter: letter * 40 for letter in 'abcdef'}
FAKE = r'''#!/usr/bin/env python3
import json, os, sys
args=sys.argv[1:]
with open(os.environ['PRUNE_CALLS'],'a') as log: log.write(json.dumps(args)+'\n')
images=json.loads(os.environ['PRUNE_IMAGES'])
if args[:2]==['image','ls']:
    print('\n'.join(images))
elif args[:2]==['image','inspect']:
    print(images[args[-1]])
elif args[:2]==['ps','--quiet']:
    print('running-container')
elif args[0]=='inspect':
    print('running-id')
elif args[:2]==['image','rm']:
    if args[-1].endswith('e'*40): sys.exit(1)
else:
    raise SystemExit('Unexpected Docker command: '+str(args))
'''


class Retention(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.task = Path(self.directory.name)
        (self.task / 'bin').mkdir()
        docker = self.task / 'bin/docker'
        docker.write_text(FAKE)
        docker.chmod(0o755)
        self.app = self.task / 'app'
        self.app.mkdir()
        self.env = os.environ.copy()
        self.env.update(PATH=f'{self.task / "bin"}:{self.env["PATH"]}',
                        PRUNE_CALLS=str(self.task / 'calls'))

    def run_helper(self, repo, previous, current=None):
        self.env['PRUNE_IMAGES'] = json.dumps({
            f'{repo}:{SHA["a"]}': 'current-id',
            f'{repo}:{SHA["b"]}': 'previous-id',
            f'{repo}:{SHA["c"]}': 'stale-id',
            f'{repo}:{SHA["d"]}': 'running-id',
            f'{repo}:{SHA["e"]}': 'stopped-container-id',
            f'unrelated:{SHA["f"]}': 'unrelated-id',
            f'{repo}:latest': 'current-id',
            f'{repo}:{"A" * 40}': 'non-release-id',
        })
        return subprocess.run(['bash', str(ROOT / 'ops/lowmemory/prune-images.sh'),
                               str(self.app), current or f'{repo}:{SHA["a"]}', previous],
                              env=self.env, text=True, capture_output=True)

    def calls(self):
        path = self.task / 'calls'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_keeps_two_releases_running_and_unrelated_images_and_tolerates_in_use_refusal(self):
        for repo in ('spaceapps-api', 'spaceapps-ml', 'spaceapps-frontend'):
            with self.subTest(repo=repo):
                (self.task / 'calls').unlink(missing_ok=True)
                result = self.run_helper(repo, f'{repo}:{SHA["b"]}')
                self.assertEqual(result.returncode, 0, result.stderr)
                removals = [call for call in self.calls() if call[:2] == ['image', 'rm']]
                self.assertEqual(removals, [['image', 'rm', f'{repo}:{SHA["c"]}'],
                                            ['image', 'rm', f'{repo}:{SHA["e"]}']])
                self.assertEqual((self.app / 'previous.env').read_text(),
                                 f'PREVIOUS_IMAGE={repo}:{SHA["b"]}\n')

    def test_same_revision_rerun_preserves_distinct_previous_release(self):
        repo = 'spaceapps-api'
        (self.app / 'previous.env').write_text(f'PREVIOUS_IMAGE={repo}:{SHA["b"]}\n')
        result = self.run_helper(repo, f'{repo}:{SHA["a"]}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.app / 'previous.env').read_text(), f'PREVIOUS_IMAGE={repo}:{SHA["b"]}\n')
        self.assertNotIn(['image', 'rm', f'{repo}:{SHA["b"]}'], self.calls())

    def test_invalid_references_fail_before_any_docker_action(self):
        for current, previous in (
            ('ubuntu:' + SHA['a'], ''), ('spaceapps-api:latest', ''),
            ('spaceapps-api:' + 'A' * 40, ''),
            ('spaceapps-api:' + SHA['a'], 'spaceapps-ml:' + SHA['b']),
            ('spaceapps-api:' + SHA['a'], 'spaceapps-api:$(false)'),
        ):
            with self.subTest(current=current, previous=previous):
                result = self.run_helper('spaceapps-api', previous, current)
                self.assertEqual(result.returncode, 64, result.stderr)
                self.assertEqual(self.calls(), [])
                self.assertFalse((self.app / 'previous.env').exists())


unittest.main()
PY
