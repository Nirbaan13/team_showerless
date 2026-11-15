"""Exercise the real release boundary; fake only remote GitHub and Docker commands."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

MODULE = Path(__file__).with_name('publish_release.py')


def add(archive, name, data):
    member = tarfile.TarInfo(name)
    member.size = len(data)
    archive.addfile(member, io.BytesIO(data))


class PublishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.publisher = None
        if MODULE.exists():
            spec = importlib.util.spec_from_file_location('demo_publish', MODULE)
            cls.publisher = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.publisher)

    def setUp(self):
        self.assertIsNotNone(self.publisher, 'release publisher has not been implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'input.tar.gz'
        self.revision = 'a' * 40
        self.token = 'test-workflow-token-never-build-with-this'
        self.calls = []
        self.v1_exists = False
        self.immutable_exists = False
        self.make_archive()

    def make_archive(self, profile='v1-real', extra=None, overlay=False):
        payloads = {name: b'public data' for name in self.publisher.bundle.PAYLOADS}
        images = io.BytesIO()
        config = json.dumps({'architecture': 'amd64', 'os': 'linux', 'config': {'Labels': {'org.opencontainers.image.revision': self.revision}}}).encode()
        image_id = hashlib.sha256(config).hexdigest()
        with tarfile.open(fileobj=images, mode='w') as archive:
            add(archive, image_id + '.json', config)
            add(archive, 'manifest.json', json.dumps([{'Config': image_id + '.json', 'RepoTags': ['source:real'], 'Layers': []}]).encode())
        payloads['images.tar'] = images.getvalue()
        record = dict(image='source:real', image_id='sha256:' + image_id, revision=self.revision, os='linux', architecture='amd64')
        inventory = {'services': {name: dict(record) for name in ('frontend', 'api', 'pipeline', 'ml-inference')}}
        if overlay:
            inventory['source_images'] = [dict(record)]
            derived = json.dumps(dict(json.loads(config), comment='derived-real-only')).encode()
            derived_id = hashlib.sha256(derived).hexdigest()
            overlay_archive = io.BytesIO()
            with tarfile.open(fileobj=overlay_archive, mode='w') as archive:
                add(archive, derived_id + '.json', derived)
                add(archive, 'manifest.json', json.dumps([{'Config': derived_id + '.json', 'RepoTags': ['demo:real-only'], 'Layers': []}]).encode())
            payloads['overlay-images.tar'] = overlay_archive.getvalue()
            inventory['services'] = {name: dict(record, image='demo:real-only', image_id='sha256:' + derived_id)
                                     for name in ('frontend', 'api', 'pipeline', 'ml-inference')}
        manifest = {'schema_version': 1, 'profile': profile, 'inventory': inventory, 'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)} for name, data in payloads.items()}}
        with tarfile.open(self.archive, 'w:gz') as archive:
            for name, data in payloads.items():
                add(archive, name, data)
            add(archive, 'manifest.json', json.dumps(manifest).encode())
            if extra:
                add(archive, extra, b'escape')
        self.checksum = hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def request(self, **changes):
        inputs = dict(version='v1', checksum=self.checksum, revision=self.revision, repository='Nirbaan13/team_showerless')
        inputs.update(changes)
        return self.publisher.release_request(**inputs)

    def run_remote(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[:3] == ['gh', 'release', 'download']:
            directory = Path(argv[argv.index('--dir') + 1])
            shutil.copyfile(self.archive, directory / 'spaceapps-demo-v1.tar.gz')
            (directory / 'spaceapps-demo-v1.tar.gz.sha256').write_text(self.checksum + '  spaceapps-demo-v1.tar.gz\n')
        if argv[:3] == ['docker', 'manifest', 'inspect']:
            exists = self.v1_exists if argv[-1].endswith(':v1') else self.immutable_exists
            return subprocess.CompletedProcess(argv, 0 if exists else 1, stdout='{}', stderr='' if exists else 'manifest unknown')
        if argv[:2] == ['docker', 'build']:
            context = Path(argv[-1])
            self.context_files = {item.name for item in context.iterdir()}
            self.context_script = (context / 'bundle.py').read_bytes()
            self.context_bytes = (context / 'bundle.tar.gz').read_bytes()
        return subprocess.CompletedProcess(argv, 0, stdout='', stderr='')

    def publish(self, request=None):
        return self.publisher.publish(request or self.request(), runner=self.run_remote, environment={'GH_TOKEN': self.token, 'GITHUB_TOKEN': self.token, 'PATH': os.environ['PATH'], 'GITHUB_ACTOR': 'demo-actor'})

    def test_rejects_invalid_version_checksum_revision_repository_and_tag_before_remote_io(self):
        for change in ({'version': 'v3'}, {'checksum': '0' * 63}, {'checksum': '../bad'}, {'revision': 'abc'}, {'repository': 'other/repo'}, {'release_tag': 'demo-v2'}, {'release_tag': '--latest'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.request(**change)
        self.assertEqual(self.calls, [])

    def test_rebuilt_v1_downloads_versioned_release_without_changing_asset_or_image_tags(self):
        tag = 'demo-v1-main-' + 'b' * 40
        result = self.publish(self.request(release_tag=tag))
        download = next(argv for argv, _ in self.calls if argv[:3] == ['gh', 'release', 'download'])
        self.assertEqual(download[3], tag)
        self.assertEqual(download[download.index('--pattern') + 1], 'spaceapps-demo-v1.tar.gz')
        self.assertEqual(result['release_tag'], tag)
        self.assertEqual(result['tags'], ['ghcr.io/nirbaan13/team-showerless-demo:v1-' + self.revision,
                                          'ghcr.io/nirbaan13/team-showerless-demo:v1'])

    def test_v2_accepts_its_own_full_sha_main_release_tag(self):
        request = self.request(version='v2', release_tag='demo-v2-main-' + 'b' * 40)
        self.assertEqual(request['release_tag'], 'demo-v2-main-' + 'b' * 40)
        self.assertEqual(request['asset'], 'spaceapps-demo-v2.tar.gz')

    def test_versioned_release_tags_reject_cross_version_short_sha_paths_and_controls(self):
        for version, other in (('v1', 'v2'), ('v2', 'v1')):
            prefix = 'demo-' + version + '-main-'
            bad_tags = [
                'demo-' + other + '-main-' + 'b' * 40,
                prefix + 'b' * 39, prefix + 'b' * 41,
                prefix + 'g' * 40, prefix + 'B' * 40,
                prefix + 'b' * 40 + '/child', '../' + prefix + 'b' * 40,
                prefix + 'b' * 40 + '\n', prefix + 'b' * 40 + '\x00',
                'demo-' + version + '-main', 'demo-' + version + '-other-' + 'b' * 40,
            ]
            for tag in bad_tags:
                with self.subTest(version=version, tag=tag), self.assertRaises(ValueError):
                    self.request(version=version, release_tag=tag)
        self.assertEqual(self.calls, [])

    def test_publishes_only_verified_bundle_with_version_and_immutable_revision_tags(self):
        result = self.publish()
        self.assertEqual(result['tags'], ['ghcr.io/nirbaan13/team-showerless-demo:v1-' + self.revision, 'ghcr.io/nirbaan13/team-showerless-demo:v1'])
        self.assertEqual(result['profile'], 'v1-real')
        self.assertEqual(self.context_files, {'bundle.py', 'bundle.tar.gz'})
        self.assertEqual(self.context_script, MODULE.with_name('bundle.py').read_bytes())
        self.assertEqual(self.context_bytes, self.archive.read_bytes())
        build = next(argv for argv, _ in self.calls if argv[:2] == ['docker', 'build'])
        self.assertIn('org.opencontainers.image.source=https://github.com/Nirbaan13/team_showerless', build)
        self.assertIn('org.opencontainers.image.revision=' + self.revision, build)
        self.assertEqual([argv[-1] for argv, _ in self.calls if argv[:2] == ['docker', 'push']], result['tags'])

    def test_publishes_source_and_derived_images_from_separate_verified_archives(self):
        self.make_archive(overlay=True)
        result = self.publish()
        self.assertEqual(result['profile'], 'v1-real')
        self.assertEqual(self.context_bytes, self.archive.read_bytes())
        self.assertEqual([argv[-1] for argv, _ in self.calls if argv[:2] == ['docker', 'push']],
                         ['ghcr.io/nirbaan13/team-showerless-demo:v1-' + self.revision,
                          'ghcr.io/nirbaan13/team-showerless-demo:v1'])

    def test_token_is_only_used_for_authenticated_download_and_login_stdin(self):
        self.publish()
        for argv, kwargs in self.calls:
            self.assertNotIn(self.token, ' '.join(argv))
            self.assertNotIn('GITHUB_TOKEN', kwargs['env'])
            if argv[0] == 'gh':
                self.assertEqual(kwargs['env']['GH_TOKEN'], self.token)
            else:
                self.assertNotIn('GH_TOKEN', kwargs['env'])
            if argv[:2] == ['docker', 'login']:
                self.assertIn('--password-stdin', argv)
                self.assertEqual(kwargs['input'], self.token + '\n')
            else:
                self.assertNotIn('input', kwargs)
        self.assertNotIn(self.token.encode(), self.context_bytes)

    def test_pinned_checksum_mismatch_prevents_build_and_push(self):
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.publish(self.request(checksum='0' * 64))
        self.assertFalse(any(argv[:2] == ['docker', 'build'] for argv, _ in self.calls))

    def test_corrupt_download_fails_even_when_checksum_asset_matches_pin(self):
        def corrupt_remote(argv, **kwargs):
            result = self.run_remote(argv, **kwargs)
            if argv[:3] == ['gh', 'release', 'download']:
                path = Path(argv[argv.index('--dir') + 1]) / 'spaceapps-demo-v1.tar.gz'
                with path.open('ab') as output:
                    output.write(b'changed in transit')
            return result
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.publisher.publish(self.request(), runner=corrupt_remote,
                                   environment={'GH_TOKEN': self.token, 'GITHUB_ACTOR': 'actor'})
        self.assertFalse(any(argv[:2] == ['docker', 'build'] for argv, _ in self.calls))

    def test_registry_authentication_failure_is_not_treated_as_a_missing_immutable_tag(self):
        def denied_remote(argv, **kwargs):
            if argv[:3] == ['docker', 'manifest', 'inspect']:
                return subprocess.CompletedProcess(argv, 1, stdout='', stderr='unauthorized: denied')
            return self.run_remote(argv, **kwargs)
        with self.assertRaisesRegex(ValueError, 'verify.*absent'):
            self.publisher.publish(self.request(), runner=denied_remote,
                                   environment={'GH_TOKEN': self.token, 'GITHUB_ACTOR': 'actor'})
        self.assertFalse(any(argv[0] == 'gh' or argv[:2] == ['docker', 'build'] for argv, _ in self.calls))

    def test_untrusted_archive_paths_prevent_build_and_do_not_escape(self):
        self.make_archive(extra='../escape')
        with self.assertRaisesRegex(ValueError, 'path'):
            self.publish()
        self.assertFalse(any(argv[:2] == ['docker', 'build'] for argv, _ in self.calls))
        self.assertFalse((self.root / 'escape').exists())

    def test_v1_rejects_mocked_core_bundle(self):
        self.make_archive(profile='v2-mocked-core')
        with self.assertRaisesRegex(ValueError, 'profile|v1'):
            self.publish()
        self.assertFalse(any(argv[:2] == ['docker', 'build'] for argv, _ in self.calls))

    def test_v2_requires_remote_v1_before_downloading_or_building(self):
        with self.assertRaisesRegex(ValueError, 'v1'):
            self.publish(self.request(version='v2'))
        self.assertFalse(any(argv[0] == 'gh' or argv[:2] == ['docker', 'build'] for argv, _ in self.calls))
        self.assertTrue(any(argv[-1] == 'ghcr.io/nirbaan13/team-showerless-demo:v1' for argv, _ in self.calls))

    def test_v2_with_v1_proof_still_rejects_real_only_bundle(self):
        self.v1_exists = True
        # Remote fixture returns v1 assets; fail the profile before considering a build.
        request = self.request(version='v2')
        def remote(argv, **kwargs):
            if argv[:3] == ['gh', 'release', 'download']:
                directory = Path(argv[argv.index('--dir') + 1])
                shutil.copyfile(self.archive, directory / 'spaceapps-demo-v2.tar.gz')
                (directory / 'spaceapps-demo-v2.tar.gz.sha256').write_text(self.checksum + '  spaceapps-demo-v2.tar.gz\n')
                return subprocess.CompletedProcess(argv, 0)
            return self.run_remote(argv, **kwargs)
        with self.assertRaisesRegex(ValueError, 'profile|v2'):
            self.publisher.publish(request, runner=remote, environment={'GH_TOKEN': self.token, 'GITHUB_ACTOR': 'actor'})
        self.assertFalse(any(argv[:2] == ['docker', 'build'] for argv, _ in self.calls))

    def test_existing_immutable_revision_is_never_overwritten(self):
        self.immutable_exists = True
        with self.assertRaisesRegex(ValueError, 'immutable|exists'):
            self.publish()
        self.assertFalse(any(argv[:2] == ['docker', 'push'] for argv, _ in self.calls))


if __name__ == '__main__':
    unittest.main()
