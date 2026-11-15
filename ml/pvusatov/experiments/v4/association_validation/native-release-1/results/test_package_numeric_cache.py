"""Only fabricated analytic records are used; no native outcomes are read."""
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).with_name('package_numeric_cache.py')


def load_packager():
    spec = importlib.util.spec_from_file_location('numeric_cache_packager', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n')


def numeric(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(value).encode(), mtime=0))
    relative = path.relative_to(path.parents[2])
    return dict(path='/tmp/spaceapps-association-validation/' + relative.as_posix(),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)


def fixture(root):
    run = root / 'native-release-1'
    full = numeric(run / 'full/success.json.gz', {'values': [1, 2, 3]})
    compact = numeric(run / 'compact/success.json.gz', {'full_pool': full})
    failure = {'phase': 'fabricated', 'message': 'analytic failure'}
    failed = numeric(run / 'compact/failed.json.gz', {'error': failure})
    # A full record may precede a failed compact publication; keep actual bytes.
    numeric(run / 'full/failed.json.gz', {'values': []})
    manifest = dict(schema_version=1, kind='native', planned=2, complete=False,
                    error_records=1, freeze_sha256='a' * 64, outputs=[
                        dict(case_id='success', kind='native', compact=compact,
                             full_pool=full, error=None),
                        dict(case_id='failed', kind='native_control', compact=failed,
                             error=failure)])
    write_json(run / 'run-manifest.json', manifest)
    report = root / 'report-native-release-1'
    write_json(report / 'research-report.json', {'freeze_sha256': 'a' * 64})
    (report / 'portable-fields.jsonl.gz').write_bytes(gzip.compress(b'{"record":"header"}\n', mtime=0))
    return manifest


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'relocated-cache'
        self.manifest = fixture(self.root)

    def package(self, name='output', **kwargs):
        return load_packager().package_cache(self.root, self.base / name,
                                             expected_records=2, part_bytes=4096, **kwargs)

    def rewrite(self):
        write_json(self.root / 'native-release-1/run-manifest.json', self.manifest)

    def test_preserves_failed_records_orphan_full_and_exact_source_bytes(self):
        result = self.package()
        output = self.base / 'output'
        manifest = json.loads((output / 'manifest.json').read_text())
        self.assertEqual(result, manifest)
        payload = b''.join((output / p['path']).read_bytes() for p in manifest['parts'])
        self.assertEqual(manifest['archive_sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(manifest['archive_bytes'], len(payload))
        self.assertGreater(len(manifest['parts']), 1)
        with tarfile.open(fileobj=io.BytesIO(payload), mode='r:') as archive:
            names = archive.getnames()
            self.assertEqual(names, sorted([
                'native-release-1/compact/failed.json.gz',
                'native-release-1/compact/success.json.gz',
                'native-release-1/full/failed.json.gz',
                'native-release-1/full/success.json.gz',
                'native-release-1/run-manifest.json',
                'report-native-release-1/portable-fields.jsonl.gz',
                'report-native-release-1/research-report.json']))
            for member in manifest['members']:
                actual = archive.extractfile(member['path']).read()
                self.assertEqual(actual, (self.root / member['path']).read_bytes())
                self.assertEqual(member['bytes'], len(actual))
                self.assertEqual(member['sha256'], hashlib.sha256(actual).hexdigest())
            archived = json.load(archive.extractfile('native-release-1/run-manifest.json'))
            self.assertEqual(archived['outputs'][1]['error']['message'], 'analytic failure')
        for index, part in enumerate(manifest['parts']):
            self.assertEqual(part['path'], f'native-numeric-cache.tar.part{index:03d}')
            data = (output / part['path']).read_bytes()
            self.assertLessEqual(len(data), 4096)
            self.assertEqual((part['bytes'], part['sha256']), (len(data), hashlib.sha256(data).hexdigest()))

    def test_reproducible_parts_and_manifest_ignore_filesystem_timestamps(self):
        self.package('one')
        import os
        for path in self.root.rglob('*'):
            os.utime(path, (123, 456))
        self.package('two')
        one, two = self.base / 'one', self.base / 'two'
        self.assertEqual({p.name: p.read_bytes() for p in one.iterdir()},
                         {p.name: p.read_bytes() for p in two.iterdir()})

    def test_corrupt_reference_digest_and_size_rejected_before_output_created(self):
        for key, bad in [('sha256', '0' * 64), ('bytes', 1)]:
            with self.subTest(key=key):
                original = self.manifest['outputs'][0]['full_pool'][key]
                self.manifest['outputs'][0]['full_pool'][key] = bad
                self.rewrite()
                with self.assertRaises(ValueError):
                    self.package()
                self.assertFalse((self.base / 'output').exists())
                self.manifest['outputs'][0]['full_pool'][key] = original

    def test_missing_closed_manifest_and_incomplete_ledger_are_rejected(self):
        path = self.root / 'native-release-1/run-manifest.json'
        path.unlink()
        with self.assertRaises(ValueError):
            self.package()
        self.manifest['outputs'].pop()
        self.rewrite()
        with self.assertRaises(ValueError):
            self.package()

    def test_error_count_complete_flag_and_duplicate_identity_must_match(self):
        for change in ['error_count', 'complete', 'duplicate']:
            with self.subTest(change=change):
                self.manifest = fixture(self.root)
                if change == 'error_count':
                    self.manifest['error_records'] = 0
                elif change == 'complete':
                    self.manifest['complete'] = True
                else:
                    self.manifest['outputs'][1]['case_id'] = 'success'
                self.rewrite()
                with self.assertRaises(ValueError):
                    self.package()

    def test_reference_path_escape_wrong_role_and_unexpected_extension_rejected(self):
        for path in ['/etc/passwd', '/tmp/spaceapps-association-validation/native-release-1/compact/../full/success.json.gz',
                     'native-release-1/full/success.json.gz', 'native-release-1/compact/raw.fits']:
            with self.subTest(path=path):
                self.manifest['outputs'][0]['compact']['path'] = path
                self.rewrite()
                with self.assertRaises(ValueError):
                    self.package()

    def test_symlinks_raw_fits_and_unexpected_files_are_rejected(self):
        run = self.root / 'native-release-1'
        for name in ['full/raw.fits', 'compact/partial.json.gz.tmp', 'full/link.json.gz']:
            with self.subTest(name=name):
                path = run / name
                if 'link' in name:
                    path.symlink_to(run / 'full/success.json.gz')
                else:
                    path.write_bytes(b'not allowed')
                with self.assertRaises(ValueError):
                    self.package()
                path.unlink()

    def test_existing_output_is_never_modified(self):
        output = self.base / 'output'
        output.mkdir()
        (output / 'keep').write_bytes(b'unchanged')
        with self.assertRaises(ValueError):
            self.package()
        self.assertEqual(list(output.iterdir()), [output / 'keep'])
        self.assertEqual((output / 'keep').read_bytes(), b'unchanged')

    def test_corrupt_failed_record_and_missing_report_are_rejected(self):
        failed = self.root / 'native-release-1/compact/failed.json.gz'
        original = failed.read_bytes()
        failed.write_bytes(b'corruption')
        with self.assertRaises(ValueError):
            self.package()
        failed.write_bytes(original)
        (self.root / 'report-native-release-1/research-report.json').unlink()
        with self.assertRaises(ValueError):
            self.package()
        self.assertFalse((self.base / 'output').exists())

    def test_all_failed_closed_run_can_have_no_full_directory(self):
        run = self.root / 'native-release-1'
        for path in (run / 'full').iterdir():
            path.unlink()
        (run / 'full').rmdir()
        self.manifest['outputs'][0].pop('full_pool')
        self.manifest['outputs'][0]['error'] = {'phase': 'analytic'}
        self.manifest['error_records'] = 2
        self.rewrite()
        result = self.package()
        self.assertEqual(result['error_records'], 2)
        self.assertEqual(len(result['members']), 5)

    def test_non_object_closed_manifest_is_rejected_cleanly(self):
        write_json(self.root / 'native-release-1/run-manifest.json', [])
        with self.assertRaises(ValueError):
            self.package()

    def test_symlink_in_cache_root_ancestry_is_rejected(self):
        alias = self.base / 'alias'
        alias.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            load_packager().package_cache(alias / self.root.name, self.base / 'output', expected_records=2)
        self.assertFalse((self.base / 'output').exists())

    def test_combined_numeric_evidence_is_bounded_before_output_created(self):
        packager = load_packager()
        packager.MAX_CACHE_BYTES = 1200  # Each individual fixture is smaller; their sum is larger.
        with self.assertRaises(ValueError):
            packager.package_cache(self.root, self.base / 'output', expected_records=2)
        self.assertFalse((self.base / 'output').exists())

    def test_cli_defaults_to_strict_1632_and_does_not_create_output(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--cache-root', str(self.root),
                                 '--output', str(self.base / 'cli')], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('1632', result.stderr)
        self.assertFalse((self.base / 'cli').exists())


if __name__ == '__main__':
    unittest.main()
