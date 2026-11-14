"""Verify the explicit v3 package with the actual CLI and decoded PNG resources."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

EXPECTED_SHA256 = 'c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204'


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path,
                        default=os.environ.get('ML_RELEASE_MODEL_DIR', here / 'model'))
    parser.add_argument('--inference-root', type=Path,
                        default=os.environ.get('ML_ROOT', here.parents[1] / 'backend' / 'inference'))
    args = parser.parse_args()
    model = args.model_dir.resolve()
    inference = args.inference_root.resolve()
    assert hashlib.sha256((model / 'ranker.onnx').read_bytes()).hexdigest() == EXPECTED_SHA256
    metadata = json.loads((model / 'metadata.json').read_text())
    assert metadata['sha256'] == EXPECTED_SHA256
    assert metadata['model_family'] == 'ExtraTreesClassifier'
    assert metadata['algorithm_version_proposal'] == 'motion-extra-v3-sigma08'
    assert metadata['detector_profile']['psf_sigma'] == .8
    # Loading verifies every bound graph property against administrative metadata.
    sys.path.insert(0, str(inference))
    from ml_inference.model import load_ranker
    from PIL import Image
    ranker = load_ranker(model)
    assert ranker.detector_profile == metadata['detector_profile']
    with tempfile.TemporaryDirectory(prefix='spherex-v3-release-smoke-') as temporary:
        folder = Path(temporary)
        request = folder / 'request.json'
        output = folder / 'output'
        request.write_text(json.dumps(dict(schema_version=1, analysis_id='v3-release-smoke',
            model_dir=str(model), source=dict(kind='preset', preset_id='comet-d6'), options={})))
        subprocess.run([sys.executable, '-m', 'ml_inference', '--request', str(request),
                        '--output', str(output)], cwd=folder,
                       env={**os.environ, 'PYTHONPATH': str(inference)}, check=True, timeout=120)
        result = json.loads((output / 'result.json').read_text())
        assert not result.get('error'), result.get('error')
        assert len(result['frames']) == 4
        assert result['model']['sha256'] == EXPECTED_SHA256
        assert result['model']['model_family'] == metadata['model_family']
        assert result['model']['detector_profile'] == metadata['detector_profile']
        assert result['algorithm_version'] == metadata['algorithm_version_proposal']
        assert result['settings']['psf_sigma_px'] == .8
        assert any(item.get('score') is not None for item in result['candidates'])
        assert result['resources'], 'CLI produced no actual resources'
        for resource in result['resources']:
            name = resource['name']
            assert Path(name).name == name, 'resource escaped output directory'
            path = output / name
            assert path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            with Image.open(path) as image:
                image.verify()
        print(f'V3 release CLI/profile/family/version and {len(result["resources"])} PNG resources verified: {EXPECTED_SHA256}')


if __name__ == '__main__':
    main()
