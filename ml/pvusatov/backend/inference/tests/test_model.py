"""Frozen inference must reject mismatches and match the offline sklearn estimator."""
import hashlib
import importlib
import json
from pathlib import Path

import numpy as np
import pytest

FEATURES = ['epoch_count', 'fit_rms_px', 'median_snr', 'min_snr',
            'snr_coefficient_of_variation', 'median_peak_ratio']


@pytest.fixture(scope='module')
def exported(tmp_path_factory):
    from sklearn.ensemble import RandomForestClassifier
    from skl2onnx import to_onnx
    import onnx
    rng = np.random.default_rng(631)
    x = rng.uniform(0, 12, (250, 6)).astype(np.float32)
    y = ((x[:, 2] > 5) & (x[:, 1] < 8)).astype(np.int64)
    forest = RandomForestClassifier(n_estimators=17, min_samples_leaf=2, random_state=57, n_jobs=1).fit(x, y)
    graph = to_onnx(forest, x[:1], options={id(forest): {'zipmap': False}}, target_opset=17)
    onnx.helper.set_model_props(graph, {'schema_version': '1', 'feature_names': json.dumps(FEATURES),
                                      'class_labels': '[0, 1]', 'score_kind': 'random_forest_vote_fraction'})
    directory = tmp_path_factory.mktemp('ranker')
    data = graph.SerializeToString()
    (directory / 'ranker.onnx').write_bytes(data)
    metadata = dict(schema_version=1, model_id='test-rf', sha256=hashlib.sha256(data).hexdigest(),
                    feature_names=FEATURES, class_labels=[0, 1], positive_class=1,
                    score_kind='random_forest_vote_fraction')
    (directory / 'metadata.json').write_text(json.dumps(metadata))
    return directory, forest, x


def load(directory=None):
    return importlib.import_module('ml_inference.model').load_ranker(directory)


def test_onnx_matches_sklearn_for_unseen_features(exported):
    directory, forest, x = exported
    ranker = load(directory)
    rng = np.random.default_rng(881)
    probes = np.vstack([x, rng.uniform(-2, 15, (1000, 6))]).astype(np.float32)
    np.testing.assert_allclose(ranker.score(probes), forest.predict_proba(probes)[:, 1], rtol=2e-6, atol=2e-6)
    assert ranker.metadata['model_id'] == 'test-rf'


def test_empty_candidates_return_empty_float_vector(exported):
    assert load(exported[0]).score(np.empty((0, 6))).shape == (0,)


@pytest.mark.parametrize('x', [np.ones(6), np.ones((3, 5)), np.ones((2, 3, 6)),
                              np.full((1, 6), np.nan), np.full((1, 6), np.inf),
                              np.full((1, 6), 1e100)])
def test_invalid_features_rejected(exported, x):
    with pytest.raises(ValueError, match='features|finite|shape'):
        load(exported[0]).score(x)


@pytest.mark.parametrize('update', [{'schema_version': 2}, {'feature_names': FEATURES[::-1]},
                                    {'class_labels': [1, 0]}, {'positive_class': 0},
                                    {'score_kind': 'planet_probability'}, {'sha256': '0' * 64}])
def test_mismatched_metadata_rejected(exported, tmp_path, update):
    directory = exported[0]
    (tmp_path / 'ranker.onnx').write_bytes((directory / 'ranker.onnx').read_bytes())
    metadata = json.loads((directory / 'metadata.json').read_text())
    metadata.update(update)
    (tmp_path / 'metadata.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        load(tmp_path)


def test_corrupt_artifact_rejected_before_runtime(exported, tmp_path):
    (tmp_path / 'ranker.onnx').write_bytes(b'not an ONNX model')
    (tmp_path / 'metadata.json').write_bytes((exported[0] / 'metadata.json').read_bytes())
    with pytest.raises(ValueError, match='digest|checksum|SHA'):
        load(tmp_path)


def test_default_frozen_model_is_present_and_scores():
    ranker = load()
    scores = ranker.score(np.array([[6, .2, 10, 8, .1, 1.4], [3, .6, 4.5, 4, .8, 4.0]]))
    assert scores.shape == (2,)
    assert np.isfinite(scores).all()
    assert np.all((0 <= scores) & (scores <= 1))


def test_graph_class_order_cannot_disagree_with_declared_order(exported, tmp_path):
    import onnx
    graph = onnx.load(exported[0] / 'ranker.onnx')
    for node in graph.graph.node:
        if node.op_type == 'TreeEnsembleClassifier':
            for attr in node.attribute:
                if attr.name == 'classlabels_int64s':
                    attr.ints[:] = [1, 0]
    data = graph.SerializeToString()
    (tmp_path / 'ranker.onnx').write_bytes(data)
    metadata = json.loads((exported[0] / 'metadata.json').read_text())
    metadata['sha256'] = hashlib.sha256(data).hexdigest()
    (tmp_path / 'metadata.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='class'):
        load(tmp_path)


def test_installed_model_matches_saved_offline_sklearn_scores():
    ranker = load()
    path = Path(__file__).resolve().parents[1] / 'models' / 'parity-reference.json'
    reference = json.loads(path.read_text())
    np.testing.assert_allclose(ranker.score(np.asarray(reference['features'])), reference['scores'],
                               rtol=2e-6, atol=2e-6)


def test_inference_loads_in_fresh_process_without_training_dependencies():
    import subprocess
    import sys
    script = '''
import builtins
original_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'sklearn', 'skl2onnx', 'training', 'onnx'}:
        raise RuntimeError('inference attempted training dependency: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded
from ml_inference.model import load_ranker
import numpy as np
assert load_ranker().score(np.ones((2, 6))).shape == (2,)
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
