"""Candidate-only source binding and full contract tests, with no held-out data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch
import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.with_name('v4')
REFERENCE_SHA = '8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282'


def package(path=None, name='optimized_candidate_tests'):
    path = path or HERE / 'runtime/ml_inference'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path / '__init__.py', submodule_search_locations=[str(path)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return __import__(name + '.pipeline', fromlist=['pipeline'])


def test_candidate_has_independent_frozen_model_and_truthful_binding():
    assert (HERE / 'runtime/ml_inference/fast_features.py').is_file(), 'isolated adapter missing'
    pipeline = package()
    descriptor = pipeline.verify_feature_producer()
    assert descriptor['actual_source_sha256'] != REFERENCE_SHA
    assert descriptor['reference_source_sha256'] == REFERENCE_SHA
    assert descriptor['model_metadata_feature_source_role'] == 'training_and_reference_source'
    assert descriptor['actual_source_sha256'] == hashlib.sha256((HERE / 'runtime/ml_inference/fast_features.py').read_bytes()).hexdigest()
    for name in ('ranker.onnx', 'metadata.json'):
        assert (HERE / 'model' / name).read_bytes() == (ORIGINAL / 'model' / name).read_bytes()


@pytest.mark.parametrize('target', ['fast_features.py', 'features.py', 'producer-manifest.json', 'model', 'adapter_and_manifest', 'reference_and_manifest'])
def test_tamper_fails_closed_before_pixels(tmp_path, target):
    source = HERE / 'runtime/ml_inference'
    copy = tmp_path / 'ml_inference'
    shutil.copytree(source, copy, ignore=shutil.ignore_patterns('__pycache__'))
    model = tmp_path / 'model'
    shutil.copytree(HERE / 'model', model)
    if target in ('adapter_and_manifest', 'reference_and_manifest'):
        prefix = 'actual' if target == 'adapter_and_manifest' else 'reference'
        name = 'fast_features.py' if prefix == 'actual' else 'features.py'
        path = copy / name
        path.write_bytes(path.read_bytes() + b'\n# modified together with manifest\n')
        manifest = copy / 'producer-manifest.json'
        value = json.loads(manifest.read_text())
        value[prefix + '_source_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(value))
    elif target == 'model':
        path = model / 'ranker.onnx'
        path.write_bytes(path.read_bytes() + b'broken')
    else:
        path = copy / target
        path.write_bytes(path.read_bytes() + (b'\n# altered\n' if target.endswith('.py') else b'broken'))
    pipeline = package(copy, 'tampered_' + target.replace('.', '_'))
    req = dict(schema_version=1, analysis_id='candidate-tamper', source=dict(kind='preset', preset_id='comet-d2'), model_dir=str(model))
    with patch.object(pipeline, 'prepare', side_effect=AssertionError('pixel reader opened')):
        with pytest.raises(pipeline.InferenceError) as err:
            pipeline.run(req, tmp_path / 'out')
    assert err.value.code == 'model_unavailable'


def compare_contract(images, times, tracks, **kw):
    pipeline = package()
    name = pipeline.__package__
    ref = __import__(name + '.features', fromlist=['features'])
    fast = __import__(name + '.fast_features', fromlist=['fast_features'])
    a = ref.extract_features(images, times, tracks, **kw)
    b = fast.extract_features(images, times, tracks, **kw)
    for dtype in (np.float64, np.float32):
        x = np.asarray(a['features_v4'], dtype=dtype)
        y = np.asarray(b['features_v4'], dtype=dtype)
        assert x.tobytes() == y.tobytes()
    for key in ('candidate_ids', 'diagnostics', 'feature_names', 'feature_version', 'feature_contract_sha256', 'template_psf_sigma'):
        assert a[key] == b[key]
    ranker = pipeline.load_ranker(HERE / 'model')
    x = ranker.score(np.asarray(a['features_v4'], np.float32))
    y = ranker.score(np.asarray(b['features_v4'], np.float32))
    assert x.tobytes() == y.tobytes()
    np.testing.assert_array_equal(np.argsort(-x, kind='stable'), np.argsort(-y, kind='stable'))
    assert b['feature_source_sha256'] != a['feature_source_sha256']
    return b


def test_full_contract_signed_masked_empty_epochs_and_edge_tracks():
    pipeline = package()
    detector = __import__(pipeline.__package__ + '.detector', fromlist=['detector'])
    rng = np.random.default_rng(3800801)
    images = rng.normal(size=(6, 32, 32)); images[4] = np.nan; images[:, :3] = np.nan
    outlier = rng.random(images.shape) < .05
    bloom = np.zeros(images.shape, bool); bloom[:, 15:17, 15:17] = True
    tracks = [detector.Candidate(tuple(range(n)), tuple((x+i%2,y+i%3) for i in range(n)), tuple(np.arange(n)+4.3), 1., .4, 1.)
              for n in (3, 4, 5, 6) for x,y in ((1,1), (6,6), (14,15), (30,30))]
    compare_contract(images, np.array([0., .01, .8, 2., 3., 6.]), tracks, psf_sigma=.8, outlier=outlier, bloom=bloom,
                     residuals=detector.difference_frames(images, leave_one_out=True))


@pytest.mark.parametrize('rows', [0, 1, 4095, 4096, 4097])
def test_grouped_block_boundaries_and_empty_contract(rows):
    pipeline = package()
    detector = __import__(pipeline.__package__ + '.detector', fromlist=['detector'])
    images = np.random.default_rng(3800802).normal(size=(4, 12, 12))
    track = detector.Candidate((0,1,2,3), ((4.,4.),(5.,4.),(6.,4.),(7.,4.)), (4.,5.,6.,7.), 1., .4, 1.)
    compare_contract(images, np.arange(4.), [track] * rows, psf_sigma=.8)


@pytest.mark.parametrize('preset', ['comet-d2', 'comet-d6', 'vesta-d3', 'vesta-d6'])
def test_real_presets_full_scientific_json_feature_diagnostics_and_all_png_bytes(tmp_path, preset):
    reference = package(ORIGINAL / 'runtime/ml_inference', 'immutable_v4_parity_tests')
    candidate = package()
    results = {}; measured = {}; dirs = {}
    for key, pipeline in [('reference', reference), ('candidate', candidate)]:
        directory = tmp_path / key
        req = dict(schema_version=1, analysis_id='candidate-parity', source=dict(kind='preset', preset_id=preset,
                   path=str(ORIGINAL / 'runtime/fixtures' / (preset + '.npz'))), model_dir=str(ORIGINAL / 'model'))
        extract = pipeline.extract_features
        def observe(*args, **kwargs):
            value = extract(*args, **kwargs)
            measured[key] = value
            return value
        with patch.object(pipeline, 'extract_features', side_effect=observe):
            results[key] = pipeline.run(req, directory)
        dirs[key] = directory
    descriptor = results['candidate']['provenance'].pop('feature_producer')
    assert descriptor['actual_source_sha256'] != results['candidate']['model']['feature_source_sha256']
    assert results['reference'] == results['candidate']
    for dtype in (np.float64, np.float32):
        assert np.asarray(measured['reference']['features_v4'], dtype=dtype).tobytes() == np.asarray(measured['candidate']['features_v4'], dtype=dtype).tobytes()
    for key in ('candidate_ids', 'diagnostics', 'feature_names', 'feature_version', 'feature_contract_sha256', 'template_psf_sigma'):
        assert measured['reference'][key] == measured['candidate'][key]
    assert sorted(p.name for p in dirs['reference'].glob('*.png')) == sorted(p.name for p in dirs['candidate'].glob('*.png'))
    for image in dirs['reference'].glob('*.png'):
        assert image.read_bytes() == (dirs['candidate'] / image.name).read_bytes()


def test_actual_cli_isolated_from_repository_and_training_imports(tmp_path):
    import os
    import subprocess
    req = dict(schema_version=1,analysis_id='candidate-cli-isolated',source=dict(kind='preset',preset_id='comet-d2'),model_dir=str(HERE/'model'))
    source = tmp_path/'request.json';source.write_text(json.dumps(req))
    code = '''
import importlib.abc,runpy,sys
class RuntimeOnly(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('ml','backend','training','sklearn','joblib','torch'):
            raise AssertionError('forbidden repository/fitting import: '+fullname)
sys.meta_path.insert(0,RuntimeOnly())
sys.argv=['ml_inference','--request',sys.argv[1],'--output',sys.argv[2]]
runpy.run_module('ml_inference',run_name='__main__')
'''
    env = {**os.environ,'PYTHONPATH':str(HERE/'runtime'),'PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
    process = subprocess.run([sys.executable,'-c',code,str(source),str(tmp_path/'out')],cwd=tmp_path,env=env,text=True,capture_output=True,timeout=30)
    assert process.returncode == 0, process.stderr
    result = json.loads((tmp_path/'out/result.json').read_text())
    assert result['candidates']
    assert result['model']['feature_source_sha256'] == REFERENCE_SHA
    assert result['provenance']['feature_producer']['actual_source_sha256'] != REFERENCE_SHA


def test_actual_cli_adapter_tamper_precedes_missing_input(tmp_path):
    import os
    import subprocess
    runtime = tmp_path/'runtime'
    shutil.copytree(HERE/'runtime/ml_inference',runtime/'ml_inference',ignore=shutil.ignore_patterns('__pycache__'))
    adapter = runtime/'ml_inference/fast_features.py'
    # If this adapter executes at import time, it would escape the structured model failure.
    adapter.write_text("raise RuntimeError('tampered adapter was executed')\n")
    req=dict(schema_version=1,analysis_id='candidate-cli-tamper',source=dict(kind='preset',preset_id='comet-d2',path=str(tmp_path/'MISSING.npz')),model_dir=str(HERE/'model'))
    source=tmp_path/'request.json';source.write_text(json.dumps(req))
    env={**os.environ,'PYTHONPATH':str(runtime),'PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
    process=subprocess.run([sys.executable,'-m','ml_inference','--request',str(source),'--output',str(tmp_path/'out')],cwd=tmp_path,env=env,text=True,capture_output=True,timeout=30)
    assert process.returncode==2
    result=json.loads((tmp_path/'out/result.json').read_text())
    assert result['error']['code']=='model_unavailable'
    assert 'tampered adapter was executed' not in process.stderr


def test_unmodified_runtime_modules_dependency_lock_and_fixtures_are_exact():
    for path in (ORIGINAL/'runtime/ml_inference').glob('*.py'):
        if path.name != 'pipeline.py':
            assert path.read_bytes() == (HERE/'runtime/ml_inference'/path.name).read_bytes()
    for path in (ORIGINAL/'runtime/fixtures').iterdir():
        if path.is_file():
            assert path.read_bytes() == (HERE/'runtime/fixtures'/path.name).read_bytes()
    for name in ('requirements-inference.in','requirements-inference.txt','dependency-provenance.json'):
        assert (HERE/name).read_bytes() == (ORIGINAL/name).read_bytes()
