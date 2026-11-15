#!/usr/bin/env bash
# Exercise real release handlers without an image archive, Docker daemon or host writes.
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/.." && pwd)
python3 - "$repo_root" <<'PY'
import json
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(sys.argv.pop())
REVISION = 'a' * 40
OLD_REVISION = 'b' * 40
FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['DOCKER_CALLS'], 'a') as log:
    log.write(json.dumps(args) + '\n')
if args[:2] == ['image', 'inspect']:
    print(os.environ['TEST_REVISION'] if 'Labels' in args[3] else ('old-id' if args[-1].endswith('b' * 40) else 'new-id'))
elif args[0] == 'create':
    print('config-container')
elif args[0] == 'cp':
    pathlib.Path(args[2]).write_text('services: {}\n# candidate release\n')
elif args[0] == 'inspect':
    print('new-id')
elif args[0] == 'compose':
    if 'up' in args and any('candidate.' in arg for arg in args) and os.environ['FAIL_CANDIDATE'] == '1':
        sys.exit(42)
    if 'ps' in args:
        print('running-container')
'''


class HostOverrides(unittest.TestCase):
    def exercise(self, service, override, fail, previous, shared_lock=False,
                 retention=False, archive_symlink=False):
        with tempfile.TemporaryDirectory() as task:
            task = Path(task)
            app = task / 'app'
            app.mkdir()
            bin_dir = task / 'bin'
            bin_dir.mkdir()
            docker = bin_dir / 'docker'
            docker.write_text(FAKE_DOCKER)
            docker.chmod(0o755)
            helper = bin_dir / 'prune-images'
            helper.write_text('#!/usr/bin/env python3\nimport json,os,sys\n'
                              'with open(os.environ["PRUNE_CALLS"], "a") as out: out.write(json.dumps(sys.argv[1:])+"\\n")\n'
                              'sys.exit(1)\n')
            helper.chmod(0o755)
            if retention:
                (app / 'prune-images.enabled').touch()
            archive = app / 'incoming-image.tar'
            if archive_symlink:
                (task / 'archive-target').write_text('preserve symlink target')
                archive.symlink_to(task / 'archive-target')
            else:
                archive.write_text('completed image upload')
            sentinel = task / 'shell-was-evaluated'
            host = app / 'host.override.yaml'
            host_text = f'# $(touch {sentinel})\nservices: {{}}\n'
            if override:
                host.write_text(host_text)
            image_var = {'api': 'APP_IMAGE', 'ml': 'ML_IMAGE', 'frontend': 'FRONTEND_IMAGE'}[service]
            image_prefix = f'spaceapps-{service}'
            old_env = f'{image_var}={image_prefix}:{OLD_REVISION}\n'
            old_compose = 'services: {}\n# previous release\n'
            if previous:
                (app / 'current.env').write_text(old_env)
                (app / 'compose.yaml').write_text(old_compose)
            env = os.environ.copy()
            env.update(PATH=f'{bin_dir}:{env["PATH"]}', APP_DIR=str(app), ML_DIR=str(app),
                       FRONTEND_DIR=str(app), IMAGE_PRUNE_HELPER=str(helper),
                       PRUNE_CALLS=str(task / 'prune-calls'),
                       RELEASE_LOCK_FILE=str(task / 'shared.lock'),
                       DOCKER_CALLS=str(task / 'calls'), TEST_REVISION=REVISION,
                       FAIL_CANDIDATE=str(int(fail)),
                       SSH_ORIGINAL_COMMAND=f'{"deploy" if service == "api" else "deploy-" + service} {REVISION}')
            script = ROOT / 'ops' / ('deploy.sh' if service == 'api' else f'deploy-{service}.sh')
            if shared_lock:
                with (task / 'shared.lock').open('w') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    process = subprocess.Popen(['bash', str(script)], stdin=subprocess.DEVNULL,
                                               text=True, env=env, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE)
                    try:
                        with self.assertRaises(subprocess.TimeoutExpired):
                            process.communicate(timeout=1)
                        self.assertFalse((task / 'calls').exists(), 'Docker ran while another release held the lock')
                        self.assertFalse((app / 'deploy.lock').exists(), 'local lock acquired before shared lock')
                    finally:
                        fcntl.flock(lock, fcntl.LOCK_UN)
                        stdout, stderr = process.communicate(timeout=15)
                    result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
            else:
                result = subprocess.run(['bash', str(script)], input='', text=True, env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 1 if fail else 0, result.stderr)
            calls = [json.loads(line) for line in (task / 'calls').read_text().splitlines()]
            compose_calls = [call for call in calls if call[0] == 'compose']
            self.assertTrue(compose_calls)
            for call in compose_calls:
                files = [call[i + 1] for i, value in enumerate(call) if value == '--file']
                self.assertEqual(files[1:], [str(host)] if override else [], call)
            rollback = [call for call in compose_calls if str(app / 'current.env') in call]
            self.assertEqual(bool(rollback), fail and previous)
            if fail:
                self.assertTrue(any('logs' in call for call in compose_calls))
                if previous:
                    self.assertEqual((app / 'current.env').read_text(), old_env)
                    self.assertEqual((app / 'compose.yaml').read_text(), old_compose)
                else:
                    self.assertTrue(any('down' in call for call in compose_calls))
            else:
                self.assertIn(f'{image_var}={image_prefix}:{REVISION}', (app / 'current.env').read_text())
                if service != 'frontend':
                    self.assertIn('# candidate release', (app / 'compose.yaml').read_text())
            self.assertEqual(host.exists(), override)
            if override:
                self.assertEqual(host.read_text(), host_text)
            self.assertFalse(sentinel.exists(), 'host override was evaluated as shell')
            prune_calls = task / 'prune-calls'
            self.assertEqual(prune_calls.exists(), retention and not fail)
            if prune_calls.exists():
                self.assertEqual(json.loads(prune_calls.read_text()),
                                 [str(app), f'{image_prefix}:{REVISION}',
                                  f'{image_prefix}:{OLD_REVISION}' if previous else ''])
            self.assertEqual(archive.exists(), not (service == 'api' and retention and not fail and not archive_symlink))
            if archive_symlink:
                self.assertTrue(archive.is_symlink())
                self.assertEqual((task / 'archive-target').read_text(), 'preserve symlink target')

    def test_optional_policy_survives_releases_and_rollbacks(self):
        # Removing the host --file argument from either release or rollback must fail.
        for service in ('api', 'ml'):
            for override in (False, True):
                for fail, previous in ((False, False), (False, True), (True, False), (True, True)):
                    with self.subTest(service=service, override=override, fail=fail, previous=previous):
                        self.exercise(service, override, fail, previous)

    def test_existing_shared_lock_serializes_docker_work_before_local_lock(self):
        for service in ('api', 'ml'):
            with self.subTest(service=service):
                self.exercise(service, True, False, True, shared_lock=True)

    def test_retention_only_after_health_and_cleanup_failure_is_nonfatal(self):
        for service in ('api', 'ml', 'frontend'):
            for fail in (False, True):
                with self.subTest(service=service, fail=fail):
                    self.exercise(service, False, fail, True, retention=True)

    def test_api_archive_symlinks_are_preserved(self):
        self.exercise('api', True, False, True, retention=True, archive_symlink=True)

    def test_frontend_without_marker_does_not_run_retention(self):
        self.exercise('frontend', False, False, True)


unittest.main()
PY
