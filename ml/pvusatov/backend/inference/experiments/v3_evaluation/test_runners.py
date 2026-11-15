"""Tests use toy files and1900000-series development seeds only."""
import pytest
from experiments.v3_evaluation import run_native,run_synthetic


@pytest.mark.parametrize('runner',[run_native,run_synthetic])
def test_missing_freeze_fails_before_scientific_loader(tmp_path,monkeypatch,runner):
    calls=[]
    monkeypatch.setattr(run_native,'_science',lambda _:calls.append('science'),raising=False)
    with pytest.raises(ValueError,match='freeze'):
        runner.run(tmp_path/'missing.json','0'*64,tmp_path/'output')
    assert calls==[]


@pytest.mark.parametrize('runner',[run_native,run_synthetic])
def test_tampered_freeze_fails_before_scientific_loader(tmp_path,monkeypatch,runner):
    path=tmp_path/'freeze.json';path.write_text('{}')
    calls=[]
    monkeypatch.setattr(run_native,'_science',lambda _:calls.append('science'),raising=False)
    with pytest.raises(ValueError,match='freeze'):
        runner.run(path,'0'*64,tmp_path/'output')
    assert calls==[]

import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np


def reference(path):return dict(path=str(path),sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def freeze_fixture(tmp_path,candidate_sigma=1.2):
    root=Path(run_native.__file__).resolve().parents[2]
    acq=tmp_path/'acquisition.json';acq.write_text('{"toy":true}')
    rows=[]
    for i in range(3):
        image=tmp_path/f'toy{i}.fits';image.write_bytes(('toy'+str(i)).encode());rows.append({**reference(image),'frame_id':f'frame{i}'})
    downloads=tmp_path/'downloads.json';downloads.write_text(json.dumps(rows))
    bank=tmp_path/'calibration.npz';bank.write_bytes(b'toy instrument knowledge')
    models={}
    for role,sigma in [('baseline',1.2),('candidate',candidate_sigma)]:
        artifact=tmp_path/(role+'.onnx');artifact.write_bytes(role.encode());metadata=tmp_path/(role+'.json');metadata.write_text(json.dumps({'sha256':reference(artifact)['sha256']}))
        models[role]=dict(artifact=reference(artifact),metadata=reference(metadata),psf_sigma=sigma)
    document=dict(schema_version=1,status='frozen',scope='development',authorized_final=False,
        package_root=str(root),runtime=dict(workers=1,math_threads=1,max_frames=32,max_grid=512),
        options={name:{**run_native.OPTIONS,'min_speed':speed}for name,speed in [('primary',.5),('secondary',.005)]},
        versions=run_native.versions(),models=models,
        sources={key:reference(root/relative)for key,relative in run_native.SOURCES.items()},
        native=dict(matrix=run_native.MATRIX,region=dict(width_arcmin=2.46,height_arcmin=2.46,pixel_scale_arcsec=6.15,mask_policy='motion'),
            acquisition_manifests=[reference(acq)],parents=[dict(parent_id='toy-parent',seed=1900001,center_deg=[15.,-30.],downloads_manifest=reference(downloads))]),
        synthetic=dict(seeds=[1900000,1900001],calibration_bank=reference(bank),generator=dict(extended_every_nth_field=3,varying_psf=True)))
    path=tmp_path/'freeze.json';path.write_text(json.dumps(document));return path,reference(path)['sha256'],document


class ToyScience:
    def __init__(self,error_call=None):
        self.calls=[];self.detections=[];self.simulations=[];self.error_call=error_call;self.model_errors={}
        self.models={role:SimpleNamespace(score=lambda features:np.full(len(features),.5))for role in ['baseline','candidate']}
        self.base=np.stack([np.arange(24*24,dtype=float).reshape(24,24)/100+i/100 for i in range(3)])
        self.times=np.array([0.,.02,.04])
    def prepare(self,request):
        self.calls.append('prepare');return SimpleNamespace(images=self.base.copy(),times=self.times.copy(),frames=[dict(frame_id=f'frame{i}')for i in range(3)],grid=None,warnings=[])
    def read_native(self,path,grid,shape):self.calls.append('read_native');return None
    def project_response(self,native,grid,position):
        response=np.zeros((24,24));x,y=np.rint(position).astype(int)
        if 0<=x<24 and 0<=y<24:response[y,x]=1
        return response,dict(toy=True)
    def add_injection(self,images,responses,flux):return images+responses*flux
    def find_candidates(self,images,times,**settings):
        self.detections.append((hashlib.sha256(images.tobytes()).hexdigest(),settings))
        if len(self.detections)==self.error_call:raise RuntimeError('toy bounded detector failure')
        return []
    def difference_frames(self,images,leave_one_out):return images*0
    def detect_peaks(self,*args):return np.empty((0,4))
    def baseline_score(self,track):return 1.
    def load_bank(self,path):self.calls.append('load_bank');return 'toy bank'
    def simulate(self,seed,bank,**settings):
        self.simulations.append(seed);truth=[np.array([[8.,8.],[9.,8.],[10.,8.]])]
        return self.base.copy(),self.times.copy(),truth,'injected',dict(cadence_family=0,epoch_count=3)


def read_cache(path):
    with gzip.open(path,'rt')as stream:return json.load(stream)


@pytest.mark.parametrize('target',['source','model','acquisition','downloads','native_bytes','calibration'])
def test_tampered_dependency_fails_before_scientific_loader(tmp_path,monkeypatch,target):
    path,sha,document=freeze_fixture(tmp_path)
    target_path={'source':None,'model':document['models']['candidate']['artifact']['path'],
        'acquisition':document['native']['acquisition_manifests'][0]['path'],
        'downloads':document['native']['parents'][0]['downloads_manifest']['path'],
        'native_bytes':str(tmp_path/'toy0.fits'),'calibration':document['synthetic']['calibration_bank']['path']}[target]
    if target=='source':
        document['sources']['prepare']['sha256']='0'*64;path.write_text(json.dumps(document));sha=reference(path)['sha256']
    else:Path(target_path).write_bytes(b'tampered')
    calls=[];monkeypatch.setattr(run_native,'_science',lambda _:calls.append('science'))
    with pytest.raises(ValueError,match='freeze'):run_native.run(path,sha,tmp_path/'output')
    assert calls==[]


def test_native_latents_are_paired_and_identical_sigma_reuses_tracks(tmp_path,monkeypatch):
    path,sha,_=freeze_fixture(tmp_path);science=ToyScience();monkeypatch.setattr(run_native,'_science',lambda _:science)
    outputs=run_native.run(path,sha,tmp_path/'output');caches=[read_cache(p)for p in outputs]
    assert len(caches)==4
    assert all(len(c['fields'])==270 and c['summary']['planned']==270 for c in caches)
    assert len(science.detections)==2+270*2
    first=caches[0]['fields']
    for other in caches[1:]:
        assert [(f['expected_xy'],f['injected_flux'])for f in other['fields']]==[(f['expected_xy'],f['injected_flux'])for f in first]
    assert all(f['features']==[]and f['scores']==[] for c in caches for f in c['fields'])
    assert not list((tmp_path/'output').glob('.*'))


def test_native_detection_failure_retains_all_planned_trials(tmp_path,monkeypatch):
    path,sha,_=freeze_fixture(tmp_path);science=ToyScience(error_call=3);monkeypatch.setattr(run_native,'_science',lambda _:science)
    caches=[read_cache(p)for p in run_native.run(path,sha,tmp_path/'output')]
    primary=[c for c in caches if c['profile']=='primary']
    assert all(c['summary']['planned']==270 and c['summary']['error_trials']==1 for c in primary)
    assert all(c['fields'][0]['injected_flux']is not None and c['fields'][0]['error']['phase']=='detection'for c in primary)


def test_synthetic_simulates_each_field_once_and_never_reserved_seeds(tmp_path,monkeypatch):
    path,sha,_=freeze_fixture(tmp_path,candidate_sigma=.8);science=ToyScience();monkeypatch.setattr(run_native,'_science',lambda _:science)
    outputs=run_synthetic.run(path,sha,tmp_path/'output');caches=[read_cache(p)for p in outputs]
    assert science.simulations==[1900000,1900001]
    assert len(caches)==4 and all(len(c['fields'])==2 for c in caches)
    assert all('parent_id'not in f for c in caches for f in c['fields'])
    assert all(c['summary']['planned']==2 for c in caches)


@pytest.mark.parametrize('mutation',['reserved_synthetic','reserved_native','unauthorized_final','missing_source','wrong_sigma','different_profile'])
def test_invalid_scope_and_options_never_reach_science(tmp_path,monkeypatch,mutation):
    path,_,document=freeze_fixture(tmp_path)
    if mutation=='reserved_synthetic':document['synthetic']['seeds']=[2000000]
    elif mutation=='reserved_native':document['native']['parents'][0]['seed']=2200001
    elif mutation=='unauthorized_final':document['scope']='final'
    elif mutation=='missing_source':del document['sources']['prepare']
    elif mutation=='wrong_sigma':document['models']['candidate']['psf_sigma']=1.6
    else:document['options']['secondary']['min_snr']=3.
    path.write_text(json.dumps(document));calls=[];monkeypatch.setattr(run_native,'_science',lambda _:calls.append('science'))
    with pytest.raises(ValueError,match='freeze'):run_native.run(path,reference(path)['sha256'],tmp_path/'output')
    assert calls==[]


def test_reader_failure_records270_planned_failures_without_invented_flux(tmp_path,monkeypatch):
    path,sha,_=freeze_fixture(tmp_path);science=ToyScience()
    def unreadable(request):raise ValueError('toy FITS unreadable')
    science.prepare=unreadable;monkeypatch.setattr(run_native,'_science',lambda _:science)
    caches=[read_cache(p)for p in run_native.run(path,sha,tmp_path/'output')]
    assert all(c['summary']['planned']==270 and c['summary']['error_trials']==270 for c in caches)
    assert all(f['expected_xy']is None and f['injected_flux']is None and f['truth_count']==1 for c in caches for f in c['fields'])
    assert science.detections==[]


def test_paired_outputs_pass_root_accounting_and_unique_truth_matching(tmp_path,monkeypatch):
    from experiments.v3_evaluation.paired import validate_cache_pair,paired_report
    from ml_inference.detector import Candidate
    path,sha,_=freeze_fixture(tmp_path,candidate_sigma=.8);science=ToyScience();monkeypatch.setattr(run_native,'_science',lambda _:science)
    caches=[read_cache(p)for p in run_native.run(path,sha,tmp_path/'output')]
    for profile in run_native.PROFILES:
        left=next(c for c in caches if c['profile']==profile and c['system']=='baseline')
        right=next(c for c in caches if c['profile']==profile and c['system']=='candidate')
        validate_cache_pair(left,right)
        report=paired_report(left['fields'],right['fields'],[f['scores']for f in left['fields']],[f['scores']for f in right['fields']],bootstrap_samples=10)
        assert report['all_planned']['trials']==270
    track=Candidate((0,1,2),((1,1),(2,1),(3,1)),(6.,6.,6.),1.,0.,1.)
    paths=[np.array([[1.,1.],[2.,1.],[3.,1.]]),np.array([[1.5,1.],[2.5,1.],[3.5,1.]])]
    measured=run_native._record([track,track],paths,False)
    assert measured['matches']==[0,0]and all(g['truth_index']==0 for g in measured['matched_geometry'])


def test_atomic_summary_counts_unique_objects_not_duplicate_rows(tmp_path):
    from ml_inference.detector import Candidate
    track=Candidate((0,1,2),((1,1),(2,1),(3,1)),(6.,6.,6.),1.,0.,1.)
    truth=[np.array([[1.,1.],[2.,1.],[3.,1.]])]
    field={**run_native._record([track,track],truth,False),'scores':[.5,.5],'error':None,'peak_cap_reached':False}
    writer=run_native.AtomicCache(tmp_path/'cache.json.gz',dict(kind='toy'))
    writer.append(field);cache=read_cache(writer.finish())
    assert cache['summary']['spatial_recovered']==1
    assert cache['summary']['spatial_recovered_trials']==1
    assert cache['summary']['candidate_rows']==2


def test_model_scoring_error_is_explicit_and_preserves_measured_geometry(tmp_path,monkeypatch):
    from ml_inference.detector import Candidate
    science=ToyScience();track=Candidate((0,1,2),((1,1),(2,1),(3,1)),(6.,6.,6.),1.,0.,1.)
    science.models['candidate']=SimpleNamespace(score=lambda _:np.array([float('nan')]))
    measurement={**run_native._empty_measurement(None),'tracks':[track]}
    result=run_native._field({},measurement,[np.array([[1.,1.],[2.,1.],[3.,1.]])],'candidate',science,True)
    assert result['error']['phase']=='model_scoring'and result['scores']==[]and result['features']==[]
    assert result['unscored_measurements']['matched_geometry'][0]['candidate_index']==0


@pytest.mark.parametrize('mutation',['metadata_artifact_hash','metadata_profile','development_final_path'])
def test_semantically_invalid_manifest_fails_before_readers(tmp_path,monkeypatch,mutation):
    path,_,document=freeze_fixture(tmp_path)
    if mutation=='development_final_path':
        forbidden=tmp_path/'quarantine_final';forbidden.mkdir();data=forbidden/'toy.fits';data.write_bytes(b'toy closed')
        downloads=tmp_path/'downloads.json';rows=json.loads(downloads.read_text());rows[0]=reference(data);downloads.write_text(json.dumps(rows));document['native']['parents'][0]['downloads_manifest']=reference(downloads)
    else:
        metadata=Path(document['models']['candidate']['metadata']['path']);value=json.loads(metadata.read_text())
        if mutation=='metadata_artifact_hash':value['sha256']='0'*64
        else:value['detector_profile']={**document['options']['secondary'],'psf_sigma':1.2}
        metadata.write_text(json.dumps(value));document['models']['candidate']['metadata']=reference(metadata)
    path.write_text(json.dumps(document));calls=[];monkeypatch.setattr(run_native,'_science',lambda _:calls.append('science'))
    with pytest.raises(ValueError,match='freeze'):run_native.run(path,reference(path)['sha256'],tmp_path/'output')
    assert calls==[]


def test_caps_and_atomic_run_failure_status_are_explicit(tmp_path,monkeypatch):
    path,sha,_=freeze_fixture(tmp_path);science=ToyScience();science.detect_peaks=lambda *args:np.zeros((100,4))
    monkeypatch.setattr(run_native,'_science',lambda _:science)
    caches=[read_cache(p)for p in run_native.run(path,sha,tmp_path/'output')]
    assert all(c['summary']['peak_cap_trials']==270 and c['control_diagnostics']['peak_cap_reached']for c in caches)
    manifest=json.loads((tmp_path/'output'/'run-native-manifest.json').read_text())
    assert manifest['evaluation_complete']and len(manifest['outputs'])==4
    assert all(not row['summary']['search_coverage_complete']for row in manifest['outputs'])
    assert all(reference(row['path'])['sha256']==row['sha256']for row in manifest['outputs'])


def test_synthetic_failure_invalidates_completion_and_retains_both_draws(tmp_path,monkeypatch):
    path,sha,_=freeze_fixture(tmp_path);science=ToyScience();simulate=science.simulate
    def failed(seed,bank,**settings):
        if seed==1900001:raise RuntimeError('toy simulation failure')
        return simulate(seed,bank,**settings)
    science.simulate=failed;monkeypatch.setattr(run_native,'_science',lambda _:science)
    caches=[read_cache(p)for p in run_synthetic.run(path,sha,tmp_path/'output')]
    assert all(c['summary']['planned']==2 and c['summary']['error_trials']==1 and c['summary']['truth_count_unknown_trials']==1 for c in caches)
    assert all(not c['summary']['evaluation_complete']for c in caches)
    assert all(c['fields'][1]['truth_count_known']is False and c['fields'][1]['expected_xy']is None for c in caches)
    assert not json.loads((tmp_path/'output'/'run-synthetic-manifest.json').read_text())['evaluation_complete']


def test_cli_failure_exit_preserves_all_planned_atomic_outputs(tmp_path,monkeypatch):
    path,sha,_=freeze_fixture(tmp_path);science=ToyScience()
    def failed(request):raise RuntimeError('toy unavailable reader')
    science.prepare=failed;monkeypatch.setattr(run_native,'_science',lambda _:science)
    monkeypatch.setattr('sys.argv',['run_native','--freeze',str(path),'--freeze-sha256',sha,'--output-dir',str(tmp_path/'output')])
    with pytest.raises(SystemExit)as exc:run_native.main()
    assert exc.value.code==2
    assert len(list((tmp_path/'output').glob('*.json.gz')))==4
    assert not list((tmp_path/'output').glob('.*'))


def test_model_initialization_failure_never_opens_native_or_simulates(tmp_path,monkeypatch):
    path,sha,_=freeze_fixture(tmp_path);science=ToyScience()
    science.model_errors={'candidate':dict(phase='model_loading',type='ValueError',message='toy invalid graph binding')}
    monkeypatch.setattr(run_native,'_science',lambda _:science)
    native=[read_cache(p)for p in run_native.run(path,sha,tmp_path/'native')]
    synthetic=[read_cache(p)for p in run_synthetic.run(path,sha,tmp_path/'synthetic')]
    assert 'prepare'not in science.calls and 'load_bank'not in science.calls and science.simulations==[]
    assert all(c['summary']['error_trials']==270 for c in native)
    assert all(c['summary']['error_trials']==2 for c in synthetic)
    assert all(f['error']['phase']=='model_loading'for c in native+synthetic for f in c['fields'])
