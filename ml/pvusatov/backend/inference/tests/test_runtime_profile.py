"""An installed model must bind its measured feature profile into its artifact."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from ml_inference.model import FEATURE_NAMES, SCORE_KIND, load_ranker


PROFILE = dict(min_snr=4., max_peaks=100, psf_sigma=.8, min_speed=.5,
               max_speed=60., match_radius=1.4, min_epochs=3, min_support=.8,
               leave_one_out=True)


@pytest.fixture
def installed(tmp_path):
    import onnx
    base = Path(__file__).resolve().parents[3] / 'releases/v2/backend/inference/models'
    graph = onnx.load(base / 'ranker.onnx')
    metadata = json.loads((base / 'metadata.json').read_text())
    # This graph is the real historical RF, tagged as a test installation only;
    # the test does not pretend it was fitted using the narrower detector.
    metadata.update(model_id='test-profile-bound-rf', detector_profile=dict(PROFILE),
                    model_family='RandomForestClassifier', algorithm_version_proposal='motion-rf-v3-sigma08')
    props = {v.key:v.value for v in graph.metadata_props}
    props.update(detector_profile=json.dumps(PROFILE, sort_keys=True),
                 model_family=metadata['model_family'],
                 algorithm_version_proposal=metadata['algorithm_version_proposal'])
    onnx.helper.set_model_props(graph, props)
    raw = graph.SerializeToString()
    (tmp_path / 'ranker.onnx').write_bytes(raw)
    metadata['sha256'] = hashlib.sha256(raw).hexdigest()
    (tmp_path / 'metadata.json').write_text(json.dumps(metadata))
    return tmp_path, metadata


def test_verified_profile_is_exposed_and_legacy_keeps_original_settings(installed):
    path, _ = installed
    assert load_ranker(path).detector_profile == PROFILE
    legacy = Path(__file__).resolve().parents[3] / 'releases/v2/backend/inference/models'
    assert load_ranker(legacy).detector_profile == {**PROFILE, 'psf_sigma':1.2}


@pytest.mark.parametrize('change', [dict(detector_profile={**PROFILE, 'psf_sigma':1.2}),
                                   dict(model_family='ExtraTreesClassifier'),
                                   dict(algorithm_version_proposal='different-algorithm')])
def test_external_profile_family_or_algorithm_cannot_change_without_artifact(installed, change):
    path, metadata = installed
    metadata.update(change)
    (path / 'metadata.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='profile|family|algorithm'):
        load_ranker(path)


def test_stripping_external_profile_from_a_bound_graph_is_rejected(installed):
    path, metadata = installed
    for key in ['detector_profile', 'model_family', 'algorithm_version_proposal']:
        del metadata[key]
    (path / 'metadata.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='profile'):
        load_ranker(path)


@pytest.mark.parametrize('key,value', [('psf_sigma', .01), ('match_radius',2.),
                                     ('min_support', .2), ('leave_one_out',False)])
def test_unsupported_feature_definition_is_rejected_even_when_embedded_agrees(installed, key, value):
    import onnx
    path, metadata = installed
    metadata['detector_profile'][key] = value
    graph = onnx.load(path / 'ranker.onnx')
    props = {v.key:v.value for v in graph.metadata_props}
    props['detector_profile'] = json.dumps(metadata['detector_profile'], sort_keys=True)
    onnx.helper.set_model_props(graph, props)
    raw = graph.SerializeToString()
    (path / 'ranker.onnx').write_bytes(raw)
    metadata['sha256'] = hashlib.sha256(raw).hexdigest()
    (path / 'metadata.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='profile'):
        load_ranker(path)


def test_pipeline_uses_verified_sigma_for_actual_tracks_and_published_settings(installed, tmp_path):
    from ml_inference.contracts import validate_request
    from ml_inference.detector import find_candidates
    from ml_inference.pipeline import run
    from ml_inference.prepare import prepare

    path, metadata = installed
    request = dict(schema_version=1, analysis_id='profile-test',
                   source=dict(kind='preset', preset_id='comet-d6'), model_dir=str(path))
    result = run(request, tmp_path / 'output')
    assert result['settings']['psf_sigma_px'] == .8
    assert result['algorithm_version'] == metadata['algorithm_version_proposal']
    assert result['model']['model_family'] == 'RandomForestClassifier'
    stack = prepare(request)
    options = validate_request(request)
    settings = {**PROFILE,
                'min_speed':options['min_speed_arcsec_per_hour']/stack.pixel_scale,
                'max_speed':options['max_speed_arcsec_per_hour']/stack.pixel_scale}
    tracks = find_candidates(stack.images, stack.times, **settings)
    rows = np.asarray([t.features() for t in tracks], np.float32).reshape(-1,len(FEATURE_NAMES))
    order = np.argsort(-load_ranker(path).score(rows), kind='stable')
    expected = [tracks[i].positions_xy for i in order[:options['max_candidates']]]
    measured = [tuple((d['x'],d['y']) for d in c['detections'])
                for c in result['candidates'] if c['method']=='residual_track']
    assert measured == expected
    assert result['comparison']['leave_one_out_count'] == len(tracks)
    assert all(c['score_kind']==SCORE_KIND for c in result['candidates'] if c['method']=='residual_track')


def test_profile_keeps_real_unscored_bloom_evidence_when_residuals_fill_the_limit(installed, tmp_path):
    from ml_inference.pipeline import run
    request = dict(schema_version=1, analysis_id='bloom-budget',
                   source=dict(kind='preset',preset_id='vesta-d3'),model_dir=str(installed[0]))
    result = run(request,tmp_path/'output')
    assert result['comparison']['leave_one_out_count'] > 100
    assert len(result['candidates']) == 100
    assert 'candidate_cap_reached_search_incomplete' in result['warnings']
    assert result['settings']['review_policy'] == 'protect_first3_residual_then_flagged_bloom'
    with np.load(Path(__file__).resolve().parents[1]/'fixtures/vesta-d3.npz') as archive:
        expected = archive['expected_xy']
    matches = [c for c in result['candidates'] if c['method']=='bloom_track'
               and len(c['detections'])==len(expected)
               and np.all(np.linalg.norm(np.asarray([(d['x'],d['y']) for d in c['detections']])-expected,axis=1)<=1.5)]
    assert matches
    assert all(c['score'] is None for c in matches)
