"""Controlled transport/source/pool checks; no reserved holdout seeds are drawn."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

HERE=Path(__file__).resolve().parent


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file);m=importlib.util.module_from_spec(spec);sys.modules[name]=m
    spec.loader.exec_module(m);return m


def test_wrong_external_anchor_never_executes_validator(tmp_path):
    m=load('association_test_execute','execute.py');marker=tmp_path/'marker';source=tmp_path/'bad.py'
    source.write_text(f"open({str(marker)!r},'w').write('executed')")
    freeze=tmp_path/'freeze.json';freeze.write_text(json.dumps({'sources':{'freeze':{'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}}}))
    with pytest.raises(ValueError,match='anchor'):m.bootstrap(freeze,'0'*64)
    assert not marker.exists()


def test_exact_source_ignores_timestamp_pyc(tmp_path):
    import os,py_compile
    m=load('association_test_freeze','freeze.py');p=tmp_path/'source.py'
    p.write_text('VALUE=1\n');os.utime(p,(1700000000,1700000000));py_compile.compile(str(p),doraise=True)
    p.write_text('VALUE=2\n');os.utime(p,(1700000000,1700000000))
    assert m.exact('association_checked_fixture',m.ref(p)).VALUE==2


def test_native_requires_root_release_before_any_handoff_read(tmp_path):
    m=load('association_test_runner_release','runner.py');m.__source_sha256__='verified'
    args=SimpleNamespace(kind='native',output=str(tmp_path/'out'),authorize_native=False,handoff='/missing',handoff_sha256='0'*64)
    with pytest.raises(ValueError,match='root-authorized'):
        m.run(args,{'sources':{'runner':{'sha256':'verified'}}},SimpleNamespace())


def test_legacy_pair_exclusive_matches_immutable_detector_on_controlled_peaks():
    import numpy as np
    root=HERE.parents[2];sys.path.insert(0,str(root/'backend/inference'))
    from ml_inference.detector import link_detections
    path=root/'experiments/v4/association_pilot/policies.py'
    spec=importlib.util.spec_from_file_location('association_controlled_policy',path);policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
    peaks=[np.asarray([[4+i,4,9.,1.],[12-i,12,7.,1.]],dtype=float)for i in range(4)];times=np.arange(4,dtype=float)
    pool,_=policy.build_hypotheses(peaks,times,.5,60.,1.4,3);kept,account=policy.pair_exclusive(pool)
    actual=[pool[i][1]for i in kept];expected=link_detections(peaks,times,.5,60.,1.4,3)
    assert actual==expected and account['complete'] is True


def test_simulation_failure_retains_planned_field_without_invented_truth(tmp_path):
    m=load('association_test_runner_error','runner.py')
    def broken(*args,**kwargs):raise ValueError('controlled generation failure')
    m.STATE.update(output=tmp_path,sim=SimpleNamespace(simulate=broken),bank=None)
    rows=m.synthetic(3800803)
    assert len(rows)==1 and rows[0]['seed']==3800803 and rows[0]['truth_count']is None
    assert rows[0]['error']['phase']=='synthetic_generation_or_prediction'
    assert Path(rows[0]['compact']['path']).is_file()


def test_native_plan_preserves_exact_matrix_without_drawing_new_latents():
    m=load('association_test_runner_plan','runner.py');group={'parent_id':'controlled','seed':3800804}
    rows=m.planned_native(group)
    assert len(rows)==135 and {r['direction_id']for r in rows}=={0,2,4}
    assert len({r['case_id']for r in rows})==135


def test_predict_checks_actual_legacy_linker_and_direct_feature_score_parity(monkeypatch):
    import numpy as np
    root=HERE.parents[2];sys.path.insert(0,str(root/'backend/inference'))
    from ml_inference import detector
    spec=importlib.util.spec_from_file_location('association_parity_policy',root/'experiments/v4/association_pilot/policies.py')
    policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
    m=load('association_parity_runner','runner.py')
    peaks=[np.asarray([[4+i,4,9.,1.],[12-i,12,7.,1.]],dtype=float)for i in range(4)]
    calls=[]
    def extract(images,times,tracks,**kwargs):
        calls.append('features')
        rows=np.asarray([list(t.features())+[0.]*24 for t in tracks]).reshape(-1,30)
        return {'features_v4':rows,'candidate_ids':[str(i)for i in range(len(tracks))]}
    def score(rows):calls.append('scores');return rows[:,2].astype(np.float32)/10
    actual_linker=detector.link_detections
    def link(*args):calls.append('actual_legacy');return actual_linker(*args)
    d=SimpleNamespace(difference_frames=lambda images,**kw:images,
        _detect_peaks=lambda image,*args:peaks[int(image[0,0])],link_detections=link)
    m.STATE.update(np=np,detector=d,features=SimpleNamespace(extract_features=extract),model=SimpleNamespace(score=score),policies=policy)
    images=np.stack([np.full((20,20),i,dtype=float)for i in range(4)])
    result=m.predict(images,np.arange(4,dtype=float))
    assert result['legacy_candidate_parity']is True and result['legacy_feature_score_parity']is True
    assert calls.count('actual_legacy')==1 and calls.count('features')==2 and calls.count('scores')==2


def test_duplicate_plus_missing_seed_does_not_pass_a_full_length_manifest():
    m=load('association_identity_test','runner.py')
    rows=[dict(kind='synthetic',seed=s,case_id=f'synthetic-{s}')for s in range(4100000,4101000)]
    assert m.check_records(rows,'synthetic')is None
    rows[-1]=dict(rows[0])
    with pytest.raises(ValueError,match='identity'):m.check_records(rows,'synthetic')


def test_native_control_and_matrix_seed_mapping_are_both_required():
    m=load('association_identity_native_test','runner.py')
    groups=[{'parent_id':f'controlled{i}','seed':3800800+i}for i in range(12)]
    rows=[]
    for g in groups:
        rows.extend(m.planned_native(g));rows.append(dict(kind='native_control',parent_id=g['parent_id'],seed=g['seed'],case_id=g['parent_id']+'-control'))
    assert m.check_records(rows,'native',groups)is None
    rows[-1]['seed']+=1
    with pytest.raises(ValueError,match='identity'):m.check_records(rows,'native',groups)
