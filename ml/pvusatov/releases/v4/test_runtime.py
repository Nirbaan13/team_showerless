"""Isolated V4 runtime integration; production V3 package remains untouched."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[4]
RELEASE = Path(__file__).resolve().parent
RUNTIME = RELEASE / 'runtime'
ORIGINAL = ROOT / 'ml/pvusatov/backend/inference'
DETECTION = ROOT / 'ml/pvusatov/experiments/v4/detection'


def package():
    name = 'isolated_v4_runtime_ml'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, RUNTIME / 'ml_inference/__init__.py', submodule_search_locations=[str(RUNTIME / 'ml_inference')])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return __import__(name + '.pipeline', fromlist=['pipeline'])


@pytest.fixture
def model(tmp_path):
    from ml.pvusatov.experiments.v4.detection.test_runtime_model import graph, metadata
    value = metadata('RankNetTreeBoost')
    artifact = graph(value).SerializeToString()
    directory = tmp_path / 'model'
    directory.mkdir()
    (directory / 'ranker.onnx').write_bytes(artifact)
    (directory / 'metadata.json').write_text(json.dumps({**value, 'sha256':hashlib.sha256(artifact).hexdigest()}))
    return directory


def request(model, preset='comet-d2', **extra):
    return dict(schema_version=1, analysis_id='v4-controlled', source=dict(kind='preset', preset_id=preset), model_dir=str(model), **extra)


def test_copied_sources_and_fixtures_match_frozen_inputs():
    for source in (ORIGINAL / 'ml_inference').glob('*.py'):
        if source.name not in ('pipeline.py', 'model.py'):
            assert (RUNTIME / 'ml_inference' / source.name).read_bytes() == source.read_bytes()
    assert (RUNTIME / 'ml_inference/features.py').read_bytes() == (DETECTION / 'features.py').read_bytes()
    assert (RUNTIME / 'ml_inference/model.py').read_bytes() == (DETECTION / 'runtime_model.py').read_bytes()
    for source in (ORIGINAL / 'fixtures').iterdir():
        if source.is_file():
            assert (RUNTIME / 'fixtures' / source.name).read_bytes() == source.read_bytes()


def test_bad_model_refuses_before_any_pixel_reader(tmp_path):
    pipeline = package()
    with patch.object(pipeline, 'prepare', side_effect=AssertionError('pixel reader opened')):
        with pytest.raises(pipeline.InferenceError, match='could not be verified') as error:
            pipeline.run(request(tmp_path / 'absent'), tmp_path / 'out')
    assert error.value.code == 'model_unavailable'


def test_default_model_directory_is_explicit_before_prepare(tmp_path):
    pipeline = package()
    req = request(tmp_path); del req['model_dir']
    with patch.object(pipeline, 'load_ranker', side_effect=ValueError('unavailable')) as loader:
        with patch.object(pipeline, 'prepare', side_effect=AssertionError('pixel reader opened')):
            with pytest.raises(pipeline.InferenceError):
                pipeline.run(req, tmp_path / 'out')
    loader.assert_called_once_with('/app/inference/models')


def test_real_preset_scores_full30_and_reports_truthful_score_kind(model, tmp_path):
    pipeline = package()
    original = pipeline.extract_features
    captured = []
    def observe(*args, **kwargs):
        result = original(*args, **kwargs)
        captured.append(result)
        assert kwargs['psf_sigma'] == .8
        assert kwargs['residuals'].shape == args[0].shape
        return result
    with patch.object(pipeline, 'extract_features', side_effect=observe):
        result = pipeline.run(request(model), tmp_path / 'out')
    assert captured[0]['features_v4'].shape[1] == 30
    assert result['candidates']
    assert all(c['score_kind'] == 'sigmoid_pairwise_utility' for c in result['candidates'])
    assert result['model']['feature_names'] == list(captured[0]['feature_names'])
    assert result['model']['feature_source_sha256'] == '8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282'
    assert result['settings']['feature_template_psf_sigma_px'] == .8
    json.dumps(result, allow_nan=False)


def test_bloom_stays_unscored_and_within_protected_review_cap(model, tmp_path):
    from PIL import Image
    pipeline = package()
    result = pipeline.run(request(model, 'vesta-d3'), tmp_path / 'out')
    assert len(result['candidates']) <= 100
    bloom = [c for c in result['candidates'] if c['method'] == 'bloom_track']
    assert bloom and all(c['score'] is None for c in bloom)
    assert all(c['score_kind'] == 'flagged_bloom_evidence' for c in bloom)
    assert all(c['method'] == 'residual_track' for c in result['candidates'][:3])
    assert all(d['residual_snr'] is None for c in bloom for d in c['detections'])
    for resource in result['resources']:
        path = tmp_path / 'out' / resource['name']
        assert path.stat().st_size == resource['size_bytes']
        with Image.open(path) as image:
            image.verify()
    assert result['comparison']['shared_median_count'] >= 0
    assert result['settings']['review_policy'] == 'protect_first3_residual_then_flagged_bloom'


def test_empty_fixture_is_finite_and_does_not_score_fake_candidates(model, tmp_path):
    path = tmp_path / 'empty.npz'
    np.savez_compressed(path, images=np.zeros((3,24,24)),
        dates=np.array(['2025-01-01T00:00:00','2025-01-01T01:00:00','2025-01-01T02:00:00']),
        times=np.array([0.,1.,2.]), observation_ids=np.array(['a','b','c']), center_deg=np.array([20.,5.]),pixel_scale_arcsec=6.15)
    req = request(model); req['source']['path'] = str(path)
    result = package().run(req, tmp_path / 'out')
    assert result['candidates'] == [] and len(result['frames']) == 3
    assert 'no_candidates_above_thresholds' in result['warnings']
    json.dumps(result, allow_nan=False)


def test_actual_cli_writes_safe_model_failure_before_bad_fits(tmp_path):
    req = dict(schema_version=1, analysis_id='v4-error', source=dict(kind='fits', observations=[]), model_dir=str(tmp_path / 'private-model-path'))
    source = tmp_path / 'request.json'; source.write_text(json.dumps(req))
    output = tmp_path / 'out'
    env = {**os.environ, 'PYTHONPATH':str(RUNTIME), 'OPENBLAS_NUM_THREADS':'1', 'OMP_NUM_THREADS':'1'}
    process = subprocess.run([sys.executable,'-m','ml_inference','--request',str(source),'--output',str(output)], env=env, cwd=tmp_path, capture_output=True, text=True)
    assert process.returncode == 2
    result = json.loads((output / 'result.json').read_text())
    assert result['error']['code'] == 'model_unavailable'
    assert 'private-model-path' not in json.dumps(result) + process.stderr
    assert not list(output.glob('*.tmp'))


def test_malformed_actual_graph_refuses_before_reader(model, tmp_path):
    import onnx
    pipeline = package()
    path = model / 'ranker.onnx'
    graph = onnx.load_model_from_string(path.read_bytes())
    graph.graph.node[0].input[0] = 'undeclared-input'
    blob = graph.SerializeToString(); path.write_bytes(blob)
    value = json.loads((model / 'metadata.json').read_text())
    value['sha256'] = hashlib.sha256(blob).hexdigest()
    (model / 'metadata.json').write_text(json.dumps(value))
    with patch.object(pipeline, 'prepare', side_effect=AssertionError('pixel reader opened')):
        with pytest.raises(pipeline.InferenceError) as error:
            pipeline.run(request(model), tmp_path / 'out')
    assert error.value.code == 'model_unavailable'


def test_malformed_field_is_checked_after_verified_model(model, tmp_path):
    pipeline = package(); events = []
    bad = tmp_path / 'bad.npz'; np.savez_compressed(bad, images=np.zeros((2,2)))
    req = request(model); req['source']['path'] = str(bad)
    loader, prepare = pipeline.load_ranker, pipeline.prepare
    def verified(path):
        result = loader(path); events.append('verified_model'); return result
    def field(value):
        events.append('pixel_reader'); return prepare(value)
    with patch.object(pipeline, 'load_ranker', side_effect=verified), patch.object(pipeline, 'prepare', side_effect=field):
        with pytest.raises(pipeline.InferenceError) as error:
            pipeline.run(req, tmp_path / 'out')
    assert events == ['verified_model','pixel_reader']
    assert error.value.code in ('invalid_input','workload_limit')


@pytest.mark.parametrize('preset', ['comet-d2','comet-d6','vesta-d3','vesta-d6'])
def test_selected_trained_model_matches_frozen_preset_features_and_order(preset, tmp_path):
    pipeline = package()
    selected = RELEASE / 'model'
    expected = json.loads((DETECTION / 'results/preset-feature-cache.json').read_text())['cases'][preset]
    extractor = pipeline.extract_features; captured = []
    def observe(*args, **kwargs):
        result = extractor(*args, **kwargs); captured.append(result); return result
    with patch.object(pipeline, 'extract_features', side_effect=observe):
        result = pipeline.run(request(selected, preset), tmp_path / 'out')
    np.testing.assert_array_equal(np.asarray(captured[0]['features_v4'],np.float32), np.asarray(expected['features_v4'],np.float32))
    ranker = pipeline.load_ranker(selected)
    assert ranker.metadata['sha256'] == 'c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
    scores = ranker.score(np.asarray(expected['features_v4'],np.float32))
    order = np.argsort(-scores,kind='stable')
    residual = [c for c in result['candidates'] if c['method'] == 'residual_track']
    assert [c['baseline_rank'] for c in residual] == (order[:len(residual)]+1).tolist()
    np.testing.assert_array_equal([c['score'] for c in residual],scores[order[:len(residual)]])
    assert result['comparison']['leave_one_out_count'] == len(expected['features_v4'])
    assert all(c['score_kind'] == 'sigmoid_pairwise_utility' for c in residual)
    # Coordinates are opened ONLY after all inference/predictions, for eligibility.
    with np.load(RUNTIME / 'fixtures' / (preset+'.npz'),allow_pickle=False) as data:
        truth = data['expected_xy']
    matches = [c for c in result['candidates'] if len(c['detections']) == len(truth) and
        np.max(np.linalg.norm(np.asarray([[d['x'],d['y']]for d in c['detections']])-truth,axis=1)) <= 1.5]
    assert matches
    if preset == 'comet-d2': assert matches[0]['rank'] == 1
    if preset == 'comet-d6': assert matches[0]['rank'] <= 4
    if preset.startswith('vesta'): assert matches[0]['method'] == 'bloom_track' and matches[0]['score'] is None


def test_selected_cli_from_unrelated_cwd_never_imports_fitting_packages(tmp_path):
    model = RELEASE / 'model'
    code = '''
import importlib.abc,json,sys
class NoFit(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('sklearn','joblib','training','torch'):
            raise AssertionError('runtime attempted fitting package: '+fullname)
sys.meta_path.insert(0,NoFit())
from ml_inference.pipeline import run
result=run(json.loads(sys.argv[1]),sys.argv[2])
print(json.dumps({'sha256':result['model']['sha256'],'score_kind':result['model']['score_kind'],'candidates':len(result['candidates'])}))
'''
    env = {**os.environ,'PYTHONPATH':str(RUNTIME),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
    process = subprocess.run([sys.executable,'-c',code,json.dumps(request(model)),str(tmp_path/'out')],env=env,cwd=tmp_path,capture_output=True,text=True)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result['sha256'] == 'c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
    assert result['candidates'] and result['score_kind'] == 'sigmoid_pairwise_utility'


def test_evidence_discards_unused_full_image_maps_between_epochs(model, tmp_path):
    import weakref
    pipeline = package(); references = []; original = pipeline.filtered_evidence
    def observe(*args, **kwargs):
        assert all(ref() is None for ref in references), 'unused smoothed/support maps retained across epochs'
        result = original(*args, **kwargs)
        references.extend([weakref.ref(result[0]),weakref.ref(result[2])])
        return result
    with patch.object(pipeline, 'filtered_evidence', side_effect=observe):
        pipeline.run(request(model), tmp_path / 'out')
    assert all(ref() is None for ref in references)


def test_maximum_probe_timeout_is_bounded_before_source_or_model_access(tmp_path):
    helper = RUNTIME / 'measure_maximum.py'
    spec = importlib.util.spec_from_file_location('isolated_v4_maximum_probe',helper)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.bounded_timeout('1') == 1
    assert module.bounded_timeout('900') == 900
    for value in ['0','-1','901','1.5']:
        with pytest.raises(Exception):
            module.bounded_timeout(value)
    process = subprocess.run([sys.executable,str(helper),'--model-dir',str(tmp_path/'unopened-model'),
        '--output',str(tmp_path/'unused-proof.json'),'--timeout-seconds','901'],capture_output=True,text=True)
    assert process.returncode == 2
    assert 'timeout' in process.stderr and not (tmp_path/'unused-proof.json').exists()
    assert 'FileNotFoundError' not in process.stderr
