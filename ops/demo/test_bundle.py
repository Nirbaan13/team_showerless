"""Behavior tests for the offline release boundary; no container daemon required."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('demo_bundle', Path(__file__).with_name('bundle.py'))
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


def add_bytes(archive, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    archive.addfile(info, io.BytesIO(data))


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='demo bundle spaces ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.images = self.root / 'images.tar'
        services = {}
        entries = []
        with tarfile.open(self.images, 'w') as archive:
            for name in ('frontend', 'api', 'ml-inference'):
                config = json.dumps({'architecture': 'amd64', 'os': 'linux', 'config': {'Labels': {'org.opencontainers.image.revision': 'a' * 40}}}).encode() + name.encode()[:0]
                # Distinct configs represent three immutable application images.
                config = json.dumps(dict(json.loads(config), comment=name)).encode()
                digest = hashlib.sha256(config).hexdigest()
                image = 'spaceapps-' + name + ':' + 'a' * 40
                add_bytes(archive, digest + '.json', config)
                entries.append({'Config': digest + '.json', 'RepoTags': [image], 'Layers': []})
                services[name] = dict(image=image, image_id='sha256:' + digest, revision='a' * 40, os='linux', architecture='amd64')
            add_bytes(archive, 'manifest.json', json.dumps(entries).encode())
        services['pipeline'] = dict(services['api'])
        self.inventory = {'schema_version': 1, 'services': services}
        self.seed = self.root / 'seed'
        (self.seed / 'api-data').mkdir(parents=True)
        (self.seed / 'ml-data').mkdir()
        (self.seed / 'api-data' / 'science.txt').write_text('public NASA data')
        self.output = self.root / 'bundle.tar.gz'

    def build(self):
        return bundle.build_bundle(self.inventory, self.images, self.seed, self.output)

    def test_complete_bundle_verifies_and_preserves_exact_image_inventory(self):
        self.assertTrue(hasattr(bundle, 'build_bundle'), 'bundle builder has not been implemented')
        self.build()
        dest = self.root / 'release'
        manifest = bundle.unpack_bundle(self.output, dest)
        self.assertEqual(manifest['inventory']['services'], self.inventory['services'])
        self.assertEqual(set(manifest['files']), {'bundle.py', 'run.sh', 'compose.yaml', 'nginx.conf', 'images.tar', 'seeddata.tar'})
        self.assertTrue((dest / 'images.tar').is_file())

    def test_incomplete_inventory_fails_before_creating_release(self):
        self.inventory['services'].pop('pipeline')
        with self.assertRaisesRegex(ValueError, 'pipeline'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_missing_image_from_saved_archive_is_rejected(self):
        self.inventory['services']['frontend']['image_id'] = 'sha256:' + '0' * 64
        with self.assertRaisesRegex(ValueError, 'image|digest'):
            self.build()

    def test_original_deployed_images_are_required_alongside_derived_service_images(self):
        original = dict(self.inventory['services']['frontend'])
        original['image_id'] = 'sha256:' + '0' * 64
        self.inventory['source_images'] = [original]
        with self.assertRaisesRegex(ValueError, 'source|image|digest'):
            self.build()

    def add_oci_index(self, *, bad_digest=False, wrong_tag=False, wrong_link=False):
        with tarfile.open(self.images) as src:
            payload = {m.name: src.extractfile(m).read() for m in src if m.isfile()}
        records = json.loads(payload['manifest.json'])
        descriptors = []
        for record in records:
            config = payload[record['Config']]
            config_id = 'sha256:' + hashlib.sha256(config).hexdigest()
            payload['blobs/sha256/' + config_id.split(':')[1]] = config
            manifest = {'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.manifest.v1+json',
                        'config': {'digest': config_id, 'size': len(config)}, 'layers': []}
            if wrong_link:
                manifest['config']['digest'] = 'sha256:' + '0' * 64
            raw = json.dumps(manifest).encode()
            identity = 'sha256:' + hashlib.sha256(raw).hexdigest()
            payload['blobs/sha256/' + identity.split(':')[1]] = raw + (b'changed' if bad_digest else b'')
            tag = 'wrong:tag' if wrong_tag else 'docker.io/library/' + record['RepoTags'][0]
            descriptors.append({'digest': identity, 'size': len(raw), 'annotations': {'io.containerd.image.name': tag}})
            for expected in self.inventory['services'].values():
                if expected['image_id'] == config_id:
                    expected['image_id'] = identity
        payload['index.json'] = json.dumps({'schemaVersion': 2, 'manifests': descriptors}).encode()
        with tarfile.open(self.images, 'w') as dst:
            for name, raw in payload.items():
                add_bytes(dst, name, raw)

    def test_oci_manifest_id_is_verified_and_linked_to_configuration(self):
        self.add_oci_index()
        original = self.inventory['services']['api']['image_id']
        self.build()
        expected = self.inventory['services']['api']
        self.assertEqual(expected['image_id'], original)
        self.assertTrue(expected['archive_config_id'].startswith('sha256:'))
        self.assertNotEqual(expected['archive_config_id'], original)

    def test_oci_broken_digest_tag_and_configuration_links_are_rejected(self):
        for mutation in ['bad_digest', 'wrong_tag', 'wrong_link']:
            with self.subTest(mutation=mutation):
                self.setUp()
                self.add_oci_index(**{mutation: True})
                with self.assertRaises(ValueError):
                    self.build()

    def test_raw_podman_id_is_accepted_only_with_matching_saved_config_and_rootfs(self):
        expected = dict(self.inventory['services']['api'], archive_config_id='sha256:' + 'b' * 64,
                        archive_rootfs=['sha256:' + 'c' * 64])
        actual = {'Id': 'b' * 64, 'Architecture': 'amd64', 'Os': 'linux',
                  'Config': {'Labels': {'org.opencontainers.image.revision': 'a' * 40}},
                  'RootFS': {'Layers': ['sha256:' + 'c' * 64]}}
        self.assertEqual(bundle.validate_loaded_image(expected, actual), 'sha256:' + 'b' * 64)
        actual['RootFS']['Layers'] = ['sha256:' + 'd' * 64]
        with self.assertRaisesRegex(ValueError, 'root|layer'):
            bundle.validate_loaded_image(expected, actual)
        actual['RootFS']['Layers'] = expected['archive_rootfs']
        actual['Id'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'ID|digest'):
            bundle.validate_loaded_image(expected, actual)

    def create_overlay(self, duplicate_source_tag=False):
        original = dict(self.inventory['services']['frontend'])
        self.inventory['source_images'] = [original]
        config = json.dumps({'architecture': 'amd64', 'os': 'linux', 'comment': 'real-only frontend',
                             'config': {'Labels': {'org.opencontainers.image.revision': 'a' * 40}}}).encode()
        digest = hashlib.sha256(config).hexdigest()
        tag = original['image'] if duplicate_source_tag else 'spaceapps-frontend-real:' + 'a' * 40
        self.overlay = self.root / 'overlay.tar.gz'
        with tarfile.open(self.overlay, 'w:gz') as archive:
            add_bytes(archive, digest + '.json', config)
            add_bytes(archive, 'manifest.json', json.dumps([{'Config': digest + '.json', 'RepoTags': [tag], 'Layers': []}]).encode())
        self.inventory['services']['frontend'] = dict(original, image=tag, image_id='sha256:' + digest)

    def test_derived_service_requires_overlay_and_both_archives_are_checksummed(self):
        self.create_overlay()
        with self.assertRaisesRegex(ValueError, 'digest|missing'):
            self.build()
        bundle.build_bundle(self.inventory, self.images, self.seed, self.output, overlay_images=self.overlay)
        destination = self.root / 'combined'
        manifest = bundle.unpack_bundle(self.output, destination)
        self.assertIn('overlay-images.tar', manifest['files'])
        self.assertEqual((destination / 'images.tar').read_bytes(), self.images.read_bytes())
        self.assertEqual((destination / 'overlay-images.tar').read_bytes(), self.overlay.read_bytes())
        (destination / 'overlay-images.tar').write_bytes(b'corrupted overlay')
        with self.assertRaisesRegex(ValueError, 'checksum|size'):
            bundle.verify_directory(destination)

    def test_overlay_cannot_rebind_an_original_tag_to_another_configuration(self):
        self.create_overlay(duplicate_source_tag=True)
        with self.assertRaisesRegex(ValueError, 'tag|conflict'):
            bundle.build_bundle(self.inventory, self.images, self.seed, self.output, overlay_images=self.overlay)

    def test_changed_payload_is_rejected_before_extraction(self):
        self.build()
        corrupt = self.root / 'corrupt.tar'
        with tarfile.open(self.output) as src, tarfile.open(corrupt, 'w') as dst:
            for member in src:
                data = src.extractfile(member).read()
                add_bytes(dst, member.name, b'changed' if member.name == 'nginx.conf' else data)
        dest = self.root / 'rejected'
        with self.assertRaisesRegex(ValueError, 'hash|size|checksum'):
            bundle.unpack_bundle(corrupt, dest)
        self.assertFalse(dest.exists())

    def test_archive_traversal_and_links_are_rejected(self):
        for name, link in (('../escaped', False), ('/absolute', False), ('config', True)):
            bad = self.root / 'bad.tar'
            with tarfile.open(bad, 'w') as archive:
                if link:
                    info = tarfile.TarInfo(name)
                    info.type = tarfile.SYMTYPE
                    info.linkname = '/etc/passwd'
                    archive.addfile(info)
                else:
                    add_bytes(archive, name, b'bad')
            with self.assertRaises(ValueError):
                bundle.unpack_bundle(bad, self.root / 'rejected')
        self.assertFalse((self.root / 'escaped').exists())

    def test_seed_rejects_unallowlisted_roots_and_symlinks(self):
        (self.seed / '.env').write_text('secret')
        with self.assertRaisesRegex(ValueError, 'allowlist|seed|root'):
            self.build()
        (self.seed / '.env').unlink()
        (self.seed / 'api-data' / 'link').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'link'):
            self.build()

    def test_nested_environment_file_is_not_packaged(self):
        (self.seed / 'api-data' / '.env').write_text('TOKEN=private')
        with self.assertRaisesRegex(ValueError, 'secret|environment'):
            self.build()

    def test_seed_helper_uses_host_engine_stdin_and_namespaced_volume(self):
        self.build()
        calls = []
        class RecordingEngine:
            def call(inner, *args, **kwargs):
                calls.append((args, kwargs))
                if args[:2] == ('volume', 'inspect'):
                    return type('Result', (), {'returncode': 1})()
                if args[0] == 'run':
                    self.assertEqual(kwargs['stdin'].read(1), bytes([31]))
                return type('Result', (), {'returncode': 0, 'stdout': ''})()
        bundle.seed_volume(RecordingEngine(), 'spaceapps-demo-test_api-data', 'spaceapps-demo-test',
                           self.inventory['services']['api']['image_id'], self.output, 'api-data', 'digest')
        command = calls[-1][0]
        self.assertEqual(command[0], 'run')
        self.assertIn('spaceapps-demo-test_api-data:/target', command)
        self.assertEqual(command[command.index('--network') + 1], 'none')
        self.assertNotIn('--privileged', command)

    def test_seed_is_idempotent_and_preserves_runtime_edits(self):
        self.build()
        dest = self.root / 'release'
        manifest = bundle.unpack_bundle(self.output, dest)
        target = self.root / 'volume'
        target.mkdir()
        bundle.seed_directory(dest / 'seeddata.tar', target, 'api-data', 'first', chown=False)
        (target / 'science.txt').write_text('runtime edit')
        bundle.seed_directory(dest / 'seeddata.tar', target, 'api-data', 'first', chown=False)
        self.assertEqual((target / 'science.txt').read_text(), 'runtime edit')
        with self.assertRaisesRegex(ValueError, 'different|existing'):
            bundle.seed_directory(dest / 'seeddata.tar', target, 'api-data', 'second', chown=False)

    def test_engine_command_is_argument_list_and_never_shell(self):
        seen = []
        def runner(argv, **kwargs):
            seen.append((argv, kwargs))
            return type('Result', (), {'stdout': '', 'returncode': 0})()
        engine = bundle.Engine('docker', runner=runner)
        engine.call('image', 'load', '--input', str(self.root / 'archive $(touch hacked).tar'))
        self.assertEqual(seen[0][0][-1], str(self.root / 'archive $(touch hacked).tar'))
        self.assertNotIn('shell', seen[0][1])
        with self.assertRaisesRegex(ValueError, 'project'):
            bundle.validate_project('spaceapps')

if __name__ == '__main__':
    unittest.main()
