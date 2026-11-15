"""Regression checks for the actual ML image COPY boundary and runtime closure."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def scope_module():
    spec = importlib.util.spec_from_file_location('ml_image_scope', HERE / 'scope.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ImageScopeTests(unittest.TestCase):
    def test_copy_uses_only_explicit_files(self):
        sources = scope_module().copy_files(ROOT)
        self.assertIn('ml/service.py', sources)
        self.assertIn('science/motion/ranker.py', sources)
        self.assertTrue(all((ROOT / path).is_file() for path in sources))
        self.assertFalse(any('pvusatov' in path or '/test' in path for path in sources))

    def test_missing_local_import_or_runtime_asset_rejects_copy(self):
        scope = scope_module()
        sources = scope.copy_files(ROOT)
        for missing in ['science/motion/ranker.py', 'ml/candidate-example.json',
                        'science/motion/cases/vesta-d6.npz']:
            with self.subTest(missing=missing):
                with self.assertRaises(ValueError):
                    scope.validate_runtime(ROOT, {k: v for k, v in sources.items() if k != missing})

    def test_recursive_or_research_copy_is_rejected(self):
        scope = scope_module()
        for source in ['ml/', 'ml/*.py', 'ml/benchmark.py', 'ml/pvusatov/experiments/v4/']:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'Dockerfile'
                path.write_text(f'COPY {source} ./\n')
                with self.assertRaises(ValueError):
                    scope.copy_files(ROOT, dockerfile=path)

    def test_dockerignore_exposes_only_exact_runtime_files(self):
        scope = scope_module()
        sources = scope.copy_files(ROOT)
        scope.validate_ignore(ROOT, sources)
        # A broad exception would admit future research despite today's file set.
        text = (ROOT / 'ml/Dockerfile.dockerignore').read_text()
        for exception in ['!ml/*.py', '!ml/']:
            with self.subTest(exception=exception), tempfile.TemporaryDirectory() as temp:
                ignore = Path(temp) / 'ignore'
                ignore.write_text(text + '\n' + exception + '\n')
                with self.assertRaises(ValueError):
                    scope.validate_ignore(ROOT, sources, ignore=ignore)

    def test_isolated_copy_runs_existing_runtime_and_http_smoke(self):
        scope = scope_module()
        with tempfile.TemporaryDirectory(prefix='ml-image-scope-') as temp:
            stage = Path(temp) / 'app'
            scope.stage_runtime(ROOT, stage)
            self.assertFalse((stage / 'pvusatov').exists())
            result = subprocess.run([sys.executable, str(stage / 'smoke_deployment.py'),
                                     '--check-runtime'], cwd=stage, capture_output=True,
                                    text=True, timeout=120,
                                    env=dict(os.environ, PYTHONPATH=str(stage), PYTHONDONTWRITEBYTECODE='1'))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('"isolated_sqlite": true', result.stdout)
            self.assertIn('"status": "ok"', result.stdout)


if __name__ == '__main__':
    unittest.main()
