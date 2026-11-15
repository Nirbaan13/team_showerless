"""Analytic archive and guard tests; no native outcome inputs are used."""
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

HERE = Path(__file__).resolve().parent
CHECKER_SHA = '5b6105c10bfbdca1ea5e6ba4218d8cc357e3c9d10be2fc52cb527c20bd9bb8ca'


class PortableProofTests(unittest.TestCase):
    def helper(self):
        path = HERE / 'prove_portable.py'
        self.assertTrue(path.is_file(), 'portable preparation helper is missing')
        spec = importlib.util.spec_from_file_location('native_portable_preparation', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def archive(self, root, entries):
        path = root / 'analytic.tar'
        with tarfile.open(path, 'w') as archive:
            for name, kind, payload in entries:
                item = tarfile.TarInfo(name)
                item.type = kind
                item.linkname = '../outside'
                item.size = len(payload) if kind == tarfile.REGTYPE else 0
                archive.addfile(item, io.BytesIO(payload) if item.isfile() else None)
        return path

    def test_numeric_member_bytes_survive_extraction(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = self.archive(root, [('native-release-1/run-manifest.json', tarfile.REGTYPE, b'{"analytic":true}\n')])
            destination = root / 'cache'
            members = helper.safe_extract(archive, destination)
            self.assertEqual((destination / 'native-release-1/run-manifest.json').read_bytes(), b'{"analytic":true}\n')
            self.assertEqual(members[0]['bytes'], 18)
            self.assertEqual(members[0]['path'], 'native-release-1/run-manifest.json')

    def test_unsafe_members_are_rejected_before_any_payload_is_written(self):
        helper = self.helper()
        cases = [
            ('/tmp/escape.json', tarfile.REGTYPE),
            ('native-release-1/../escape.json', tarfile.REGTYPE),
            ('native-release-1/full/link.json.gz', tarfile.SYMTYPE),
            ('native-release-1/full/link.json.gz', tarfile.LNKTYPE),
            ('native-release-1/full/raw.fits', tarfile.REGTYPE),
            ('native-release-1/full/arbitrary.gz', tarfile.REGTYPE),
            ('unplanned/report.json', tarfile.REGTYPE),
            ('native-release-1/run-manifest.json', tarfile.REGTYPE),
            ('native-release-1/full/device.json.gz', tarfile.FIFOTYPE),
        ]
        for name, kind in cases:
            with self.subTest(name=name, kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = self.archive(root, [
                    ('native-release-1/run-manifest.json', tarfile.REGTYPE, b'{}'),
                    (name, kind, b'{}'),
                ])
                destination = root / 'cache'
                with self.assertRaises(ValueError):
                    helper.safe_extract(archive, destination)
                self.assertFalse(any(p.is_file() for p in destination.rglob('*')))

    def test_declared_archive_byte_budget_is_enforced_before_writes(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = self.archive(root, [('native-release-1/run-manifest.json', tarfile.REGTYPE, b'{}')])
            with self.assertRaises(ValueError):
                helper.safe_extract(archive, root / 'cache', max_bytes=1)
            self.assertFalse(any(p.is_file() for p in (root / 'cache').rglob('*')))

    def test_file_count_limit_rejects_an_archive_before_writes(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = self.archive(root, [
                ('native-release-1/full/analytic.json.gz', tarfile.REGTYPE, b'opaque gzip bytes'),
                ('native-release-1/compact/analytic.json.gz', tarfile.REGTYPE, b'opaque gzip bytes'),
            ])
            with self.assertRaises(ValueError):
                helper.safe_extract(archive, root / 'cache', max_files=1)
            self.assertFalse(any(p.is_file() for p in (root / 'cache').rglob('*')))

    def test_planned_numeric_roots_accept_full_compact_and_report_members(self):
        helper = self.helper()
        names = ['native-release-1/full/analytic.json.gz', 'native-release-1/compact/analytic.json.gz',
            'native-release-1/run-manifest.json', 'report-native-release-1/research-report.json',
            'report-native-release-1/portable-fields.jsonl.gz']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = self.archive(root, [(name, tarfile.REGTYPE, b'analytic') for name in names])
            members = helper.safe_extract(archive, root / 'cache')
            self.assertEqual([member['path'] for member in members], sorted(names))
            self.assertTrue(all((root / 'cache' / name).read_bytes() == b'analytic' for name in names))

    def test_verified_source_is_rebased_without_changing_bytes(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            (source / 'source.py').write_bytes(b'original')
            reference = {'path': '/historical/repo/source.py', 'sha256': hashlib.sha256(b'original').hexdigest()}
            result = helper.copy_verified(reference, source, root / 'fresh', Path('/historical/repo'))
            self.assertEqual((root / 'fresh/source.py').read_bytes(), b'original')
            self.assertEqual(result['path'], 'source.py')
            self.assertEqual(result['bytes'], 8)
            with self.assertRaises(ValueError):
                helper.copy_verified({'path': '/outside/source.py', 'sha256': reference['sha256']},
                    source, root / 'other', Path('/historical/repo'))

    def test_changed_source_is_not_copied_to_the_fresh_closure(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            (source / 'source.py').write_bytes(b'changed')
            reference = {'path': '/historical/repo/source.py', 'sha256': hashlib.sha256(b'original').hexdigest()}
            with self.assertRaises(ValueError):
                helper.copy_verified(reference, source, root / 'fresh', Path('/historical/repo'))
            self.assertFalse((root / 'fresh/source.py').exists())

    def test_exact_checker_guard_precedes_its_first_input_read(self):
        self.helper()
        child = HERE / 'guarded_child.py'
        self.assertTrue(child.is_file(), 'guarded child wrapper is missing')
        source = HERE.parent / 'independent-audit/check.py'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), CHECKER_SHA)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, cache, output = root / 'repo', root / 'cache', root / 'proof'
            for path in (repo, cache, output):
                path.mkdir()
            checker = repo / 'check.py'
            checker.write_bytes(source.read_bytes())
            proof = output / 'child.json'
            command = [sys.executable, str(child), '--checker', str(checker),
                '--repo-root', str(repo), '--cache-root', str(cache), '--freeze', '/etc/passwd',
                '--handoff', str(repo / 'unused.json'), '--run', str(cache / 'unused.json'),
                '--report', str(cache / 'unused-report.json'), '--output', str(output / 'audit.json'),
                '--proof-output', str(proof)]
            completed = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(completed.returncode, 0, completed.stdout)
            result = json.loads(proof.read_text())
            self.assertEqual(result['error_type'], 'PermissionError')
            self.assertEqual(result['intentional_denied_reads'], [
                '/home/usatovpavel/.codex/worktrees/spaceapps-zio-backend/ml/pvusatov/experiments/v4/association_validation/protocol.json',
                '/tmp/spaceapps-association-validation/synthetic-repair-1/run-manifest.json',
                '/etc/passwd',
            ])
            self.assertEqual(result['all_denied_reads'][-1], '/etc/passwd')
            self.assertTrue(result['python_io_guard_enabled'])
            self.assertFalse((output / 'audit.json').exists())

    def test_modified_checker_is_rejected_without_executing_its_code(self):
        self.helper()
        child = HERE / 'guarded_child.py'
        self.assertTrue(child.is_file(), 'guarded child wrapper is missing')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker = root / 'check.py'
            checker.write_text("raise RuntimeError('modified checker executed')\n")
            proof = root / 'child.json'
            completed = subprocess.run([sys.executable, str(child), '--checker', str(checker),
                '--repo-root', str(root / 'repo'), '--cache-root', str(root / 'cache'),
                '--freeze', '/etc/passwd', '--handoff', str(root / 'unused.json'),
                '--run', str(root / 'unused-run.json'), '--report', str(root / 'unused-report.json'),
                '--output', str(root / 'audit.json'), '--proof-output', str(proof)],
                text=True, capture_output=True, timeout=30)
            self.assertNotEqual(completed.returncode, 0)
            result = json.loads(proof.read_text())
            self.assertEqual(result['error_type'], 'ValueError')
            self.assertIn('external anchor', result['error'])
            self.assertFalse(result['python_io_guard_enabled'])
            self.assertFalse((root / 'audit.json').exists())


if __name__ == '__main__':
    unittest.main()
