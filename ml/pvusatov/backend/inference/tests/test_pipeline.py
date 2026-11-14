import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_cli_invalid_request_writes_safe_error_atomically(tmp_path):
    request=tmp_path/'request.json'; request.write_text('{"schema_version":9,"analysis_id":"bad"}')
    output=tmp_path/'out'
    process=subprocess.run([sys.executable,'-m','ml_inference','--request',str(request),'--output',str(output)],capture_output=True,text=True)
    assert process.returncode==2
    result=json.loads((output/'result.json').read_text())
    assert result['error']['retryable'] is False
    assert result['error']['code']=='invalid_request'
    assert str(tmp_path) not in json.dumps(result)
    assert not list(output.glob('*.tmp'))


@pytest.mark.parametrize('preset', ['comet-d6','comet-d2','vesta-d6','vesta-d3'])
def test_real_cases_recover_computed_evidence(preset,tmp_path):
    from ml_inference.pipeline import run
    from PIL import Image
    req={'schema_version':1,'analysis_id':'real','source':{'kind':'preset','preset_id':preset}}
    result=run(req,tmp_path)
    assert result['model']['model_id']
    assert result['frames'] and result['candidates']
    assert result['comparison']['leave_one_out_count'] >= 0
    with np.load(ROOT/'fixtures'/f'{preset}.npz',allow_pickle=False) as fixture:
        expected=fixture['expected_xy']
    matches=[]
    for candidate in result['candidates']:
        if len(candidate['detections'])!=len(expected): continue
        actual=np.array([[d['x'],d['y']] for d in candidate['detections']])
        if np.max(np.linalg.norm(actual-expected,axis=1))<=1.5: matches.append(candidate)
    assert matches
    if preset.startswith('vesta'):
        assert matches[0]['method']=='bloom_track'
        assert matches[0]['score'] is None
        assert all(d['residual_snr'] is None for d in matches[0]['detections'])
    else:
        assert matches[0]['method']=='residual_track'
        assert 0<=matches[0]['score']<=1
    for resource in result['resources']:
        path=tmp_path/resource['name']
        assert path.parent==tmp_path
        assert path.stat().st_size==resource['size_bytes']<1024*1024
        with Image.open(path) as image: image.verify()
    json.dumps(result,allow_nan=False)


def test_expected_positions_cannot_affect_production_output(tmp_path):
    from ml_inference.pipeline import run
    with np.load(ROOT/'fixtures'/'comet-d6.npz',allow_pickle=False) as data:
        contents={k:data[k] for k in data.files}
    a=tmp_path/'a.npz'; b=tmp_path/'b.npz'
    np.savez_compressed(a,**contents)
    contents['expected_xy']=np.full((4,2),-999999.)
    contents['target_name']=np.array('This label must not affect production inference')
    np.savez_compressed(b,**contents)
    req={'schema_version':1,'analysis_id':'same','source':{'kind':'preset','preset_id':'comet-d6','path':str(a)}}
    first=run(req,tmp_path/'first')
    req['source']['path']=str(b)
    second=run(req,tmp_path/'second')
    assert first==second


def test_empty_stack_returns_finite_empty_results_with_frozen_model(tmp_path):
    from ml_inference.pipeline import run
    path=tmp_path/'empty.npz'
    np.savez_compressed(path,images=np.zeros((3,24,24)),dates=np.array(['2025-01-01T00:00:00','2025-01-01T01:00:00','2025-01-01T02:00:00']),
                        times=np.array([0,1,2]),observation_ids=np.array(['a','b','c']),center_deg=np.array([20.,5.]),pixel_scale_arcsec=6.15)
    result=run({'schema_version':1,'analysis_id':'empty','source':{'kind':'preset','preset_id':'comet-d6','path':str(path)}},tmp_path/'out')
    assert result['candidates']==[]
    assert len(result['frames'])==3
    assert result['model']['model_id']
    assert 'no_candidates_above_thresholds' in result['warnings']
    json.dumps(result,allow_nan=False)


def test_truncated_candidates_are_explicitly_flagged(tmp_path):
    from ml_inference.pipeline import run
    result=run({'schema_version':1,'analysis_id':'bounded','source':{'kind':'preset','preset_id':'comet-d6'},
                'options':{'max_candidates':1}},tmp_path)
    assert len(result['candidates'])==1
    assert 'candidate_cap_reached_search_incomplete' in result['warnings']


def test_missing_model_does_not_leak_local_path(tmp_path):
    request=tmp_path/'request.json'
    request.write_text(json.dumps({'schema_version':1,'analysis_id':'model-error','source':{'kind':'preset','preset_id':'comet-d6'},
                                   'model_dir':str(tmp_path/'secret-model-location')}))
    output=tmp_path/'out'
    process=subprocess.run([sys.executable,'-m','ml_inference','--request',str(request),'--output',str(output)],capture_output=True,text=True)
    assert process.returncode==2
    result=(output/'result.json').read_text()
    assert json.loads(result)['error']['code']=='model_unavailable'
    assert str(tmp_path) not in result+process.stderr+process.stdout


def test_schema_boolean_is_rejected(tmp_path):
    from ml_inference.pipeline import run
    from ml_inference.contracts import InferenceError
    with pytest.raises(InferenceError):
        run({'schema_version':True,'analysis_id':'bool','source':{'kind':'preset','preset_id':'comet-d6'}},tmp_path)


def test_result_exposes_reconstructable_grid_and_precise_fixture_provenance(tmp_path):
    from ml_inference.pipeline import run
    result=run({'schema_version':1,'analysis_id':'provenance','source':{'kind':'preset','preset_id':'comet-d6'}},tmp_path)
    grid=result['provenance']['grid']
    assert grid['projection']=='TAN'
    assert grid['center_deg']==[166.79,5.29]
    assert grid['crpix_fits']==[128.5,72.5]
    assert grid['cdelt_deg'][0]<0 and grid['cdelt_deg'][1]<0
    assert grid['coordinate_origin']=='zero_based_xy'
    assert result['frames'][0]['release']=='qr2'
    assert result['frames'][0]['processing_version']=='l2b-v20-2025-349'
