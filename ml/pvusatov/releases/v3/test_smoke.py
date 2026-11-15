"""Check the release smoke from an unrelated cwd with explicit model binding."""
from pathlib import Path
import os
import subprocess
import sys


def test_real_release_cli_with_explicit_model_and_inference_paths(tmp_path):
    release = Path(__file__).resolve().parent
    inference = release.parents[1] / 'backend' / 'inference'
    result = subprocess.run(
        [sys.executable, str(release / 'smoke.py'), '--model-dir', str(release / 'model'),
         '--inference-root', str(inference)], cwd=tmp_path,
        env={**os.environ, 'PYTHONPATH': str(inference)}, capture_output=True, text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204' in result.stdout
    assert 'PNG' in result.stdout
