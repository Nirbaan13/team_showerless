"""One constrained profile-bound numeric and actual packaged-development CLI probe."""
from __future__ import annotations
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import time

EXPECTED_MODEL='c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204'
EXPECTED_METADATA='983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04'
EXPECTED_REFERENCE='53bb2b7aefc79d7b5a17613a25eb0a365a221fc34008d0d87decf6792ee3b89f'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cgroup(name):
    p=Path('/sys/fs/cgroup')/name
    return p.read_text().strip() if p.is_file() else None


def memory():
    values={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmRSS:','VmHWM:'))}
    return dict(vm_hwm_kib=int(values['VmHWM'].split()[0]),vm_rss_kib=int(values['VmRSS'].split()[0]),measurement='Linux current-process /proc/self/status VmHWM; not inherited getrusage')



CASE_HASHES={
 'comet-d2':'8f1ded9c74c78e03cc4269afa39e149e223eda398914da313afdcad817bc83fd',
 'comet-d6':'59ee6eab73fd62ae06d354e77d16d3e483e3c04307ef202712362f0503bfe55f',
 'vesta-d3':'5b8803f3add3d272d2cbcbc44ac6172f87533fa2f43b68e2ec6158e0fe29d93b',
 'vesta-d6':'e9e7e67dd3679025b66cd16c3362c80bedea19a671c191ed6ccbc67ee64a2114'}


def cli_cases(inference,candidate,metadata):
    import numpy as np
    from PIL import Image
    manifests={r['id']:r for r in json.loads((inference/'fixtures/presets.json').read_text())}
    wrapper="""import json,runpy,sys
from pathlib import Path
status=0
try:
 runpy.run_module('ml_inference',run_name='__main__')
except SystemExit as error:
 status=error.code or 0
finally:
 lines=Path('/proc/self/status').read_text().splitlines()
 values={v.split(':',1)[0]:int(v.split(':',1)[1].split()[0]) for v in lines if v.startswith(('VmHWM:','VmRSS:'))}
 print('__CLI_MEMORY__'+json.dumps(values),flush=True)
raise SystemExit(status)
"""
    rows={};computed={}
    with tempfile.TemporaryDirectory(prefix='candidate-cli-presets-',dir='/tmp') as temporary:
        folder=Path(temporary)
        for name,expected_hash in CASE_HASHES.items():
            fixture=inference/'fixtures'/manifests[name]['fixture']
            assert sha(fixture)==expected_hash==manifests[name]['sha256']
            request=folder/(name+'.json');output=folder/name
            request.write_text(json.dumps(dict(schema_version=1,analysis_id='candidate-vps-'+name,model_dir=str(candidate),source=dict(kind='preset',preset_id=name),options=dict(max_candidates=100))))
            started=time.perf_counter()
            try:
                done=subprocess.run([sys.executable,'-u','-c',wrapper,'--request',str(request),'--output',str(output)],cwd='/tmp',env={**os.environ,'PYTHONPATH':str(inference)},capture_output=True,text=True,timeout=120)
                elapsed=time.perf_counter()-started
                result=json.loads((output/'result.json').read_text()) if (output/'result.json').is_file() else None
                mm=[x.removeprefix('__CLI_MEMORY__') for x in done.stdout.splitlines() if x.startswith('__CLI_MEMORY__')]
                usage=json.loads(mm[-1]) if mm else None
                row=dict(success=False,returncode=done.returncode,wall_seconds=elapsed,linux_process_memory_kib=usage,fixture_sha256=expected_hash,stderr=done.stderr[-4096:])
                rows[name]=row
                assert done.returncode==0 and result and not result.get('error')
                assert result['model']['sha256']==EXPECTED_MODEL and result['model']['model_family']=='ExtraTreesClassifier'
                assert result['model']['detector_profile']==metadata['detector_profile']
                assert result['algorithm_version']==metadata['algorithm_version_proposal']
                assert result['settings']['psf_sigma_px']==.8
                assert result['settings']['review_policy']=='protect_first3_residual_then_flagged_bloom'
                assert len(result['frames'])>=3 and result['candidates']
                total=0;png=0;resource_hashes=[]
                for item in result['resources']:
                    assert Path(item['name']).name==item['name']
                    resource=output/item['name'];raw=resource.read_bytes();assert raw.startswith(b'\x89PNG\r\n\x1a\n')
                    with Image.open(resource) as image:image.verify()
                    if 'sha256' in item:assert sha(resource)==item['sha256']
                    resource_hashes.append(dict(name=item['name'],sha256=sha(resource),bytes=len(raw)));total+=len(raw);png+=1
                assert png>0
                for item in result['candidates']:
                    if item['method']=='bloom_track':assert item['score'] is None and all(d['residual_snr'] is None for d in item['detections'])
                row.update(success=True,model=result['model'],algorithm_version=result['algorithm_version'],settings=result['settings'],frames=len(result['frames']),candidates=len(result['candidates']),comparison=result['comparison'],warnings=result['warnings'],resource_count=png,resource_bytes=total,resource_hashes=resource_hashes)
                computed[name]=(fixture,result)
            except Exception as exc:
                rows.setdefault(name,dict(success=False,wall_seconds=time.perf_counter()-started,fixture_sha256=expected_hash))['error']=dict(type=type(exc).__name__,message=str(exc)[:1000])
        # All fixed CLI cases have finished inference before any expected XY is read.
        for name,(fixture,result) in computed.items():
            with np.load(fixture,allow_pickle=False) as data:
                identifiers=np.asarray(data['observation_ids']).astype(str);expected=np.asarray(data['expected_xy'],float)
            assert expected.shape==(len(identifiers),2) and np.isfinite(expected).all()
            lookup={}
            for identifier,position in zip(identifiers,expected):
                if identifier in lookup:assert np.array_equal(lookup[identifier],position)
                lookup[identifier]=position
            known=[]
            for item in result['candidates']:
                distances=[float(np.linalg.norm(np.asarray([d['x'],d['y']])-lookup[d['observation_id']])) for d in item['detections']]
                if distances and all(v<=1.5 for v in distances):known.append(dict(published_rank=item['rank'],method=item['method'],score=item['score'],max_offset_px=max(distances)))
            rows[name]['known_target_evaluation_only']=dict(matches=known,match_tolerance_px=1.5,labels_loaded_after_all_four_inference_runs=True,other_track_identities='unknown; never negatives')
        def known(name):return rows[name].get('known_target_evaluation_only',{}).get('matches',[])
        checks=dict(all_four_cli_success=len(rows)==4 and all(r['success'] for r in rows.values()),
            comet_d2_known_model_rank1=any(r['published_rank']==1 and r['method']=='residual_track' for r in known('comet-d2')),
            comet_d6_known_model_rank4=any(r['published_rank']==4 and r['method']=='residual_track' for r in known('comet-d6')),
            vesta_d3_known_unscored_bloom_rank100=any(r['published_rank']==100 and r['method']=='bloom_track' and r['score'] is None for r in known('vesta-d3')),
            vesta_bloom_targets_always_unscored=all(known(name) and all(r['method']=='bloom_track' and r['score'] is None for r in known(name)) for name in ['vesta-d3','vesta-d6']))
    return dict(cases=rows,checks=checks,success=all(checks.values()))


def main():
    for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[name]='1'
    import numpy as np
    root=Path('/candidate');inference=Path('/app/inference');sys.path.insert(0,str(inference))
    assert sha(root/'ranker.onnx')==EXPECTED_MODEL
    assert sha(root/'metadata.json')==EXPECTED_METADATA
    assert sha(root/'parity-reference.json')==EXPECTED_REFERENCE
    meta=json.loads((root/'metadata.json').read_text());assert meta['sha256']==EXPECTED_MODEL
    assert meta['model_family']=='ExtraTreesClassifier' and meta['detector_profile']['psf_sigma']==.8
    limits={name:cgroup(name) for name in ['cpu.max','memory.max','pids.max']}
    assert limits['memory.max']=='1073741824' and limits['pids.max']=='128'
    assert limits['cpu.max'] and limits['cpu.max'].split()[0]==limits['cpu.max'].split()[1]
    mounts=Path('/proc/self/mountinfo').read_text().splitlines()
    tmp=[line for line in mounts if line.split()[4]=='/tmp'];candidate_mount=[line for line in mounts if line.split()[4]=='/candidate']
    assert len(tmp)==1 and ' - tmpfs ' in tmp[0] and ('size=262144k' in tmp[0] or 'size=256m' in tmp[0])
    assert len(candidate_mount)==1 and 'ro' in candidate_mount[0].split()[5].split(',')
    from ml_inference import model
    assert Path(model.__file__).resolve()==inference/'ml_inference/model.py'
    started=time.perf_counter();ranker=model.load_ranker(root);load_seconds=time.perf_counter()-started
    reference=json.loads((root/'parity-reference.json').read_text());features=np.asarray(reference['features'],np.float32);expected=np.asarray(reference['scores'],float)
    assert features.shape==(3584,6) and expected.shape==(3584,)
    actual=ranker.score(features);np.testing.assert_allclose(actual,expected,rtol=2e-6,atol=2e-6)
    assert np.isfinite(actual).all()
    warm=features[:1000]
    for _ in range(3):ranker.score(warm)
    wall=[];cpu=[]
    for _ in range(20):
        a=time.perf_counter();b=time.process_time();ranker.score(warm);cpu.append(time.process_time()-b);wall.append(time.perf_counter()-a)
    numeric_memory=memory()
    # Separate capability check: loader must reject a valid-looking external
    # profile that conflicts with the profile already bound inside this graph.
    # It changes only a private /tmp metadata copy, never /candidate or services.
    with tempfile.TemporaryDirectory(prefix='candidate-profile-binding-',dir='/tmp') as temporary:
        folder=Path(temporary);shutil.copyfile(root/'ranker.onnx',folder/'ranker.onnx')
        altered=dict(meta);altered['detector_profile']={**meta['detector_profile'],'psf_sigma':1.2}
        (folder/'metadata.json').write_text(json.dumps(altered))
        try:
            other=model.load_ranker(folder);del other;gc.collect();capability=dict(rejected_mismatched_profile=False,error=None)
        except Exception as exc:
            capability=dict(rejected_mismatched_profile=True,error=dict(type=type(exc).__name__,message=str(exc)[:1000]))
    profile_binding=bool(capability['rejected_mismatched_profile'] and 'profile' in capability['error']['message'].lower())
    report=dict(schema_version=1,success=True,model_sha256=EXPECTED_MODEL,metadata_sha256=EXPECTED_METADATA,parity_reference_sha256=EXPECTED_REFERENCE,
        model_family=meta['model_family'],detector_profile=meta['detector_profile'],model_py_path=str(Path(model.__file__).resolve()),model_py_sha256=sha(model.__file__),
        python_version=sys.version,versions={name:importlib.metadata.version(name) for name in ['numpy','scipy','astropy','onnxruntime','pillow']},
        model_load_seconds=load_seconds,parity=dict(rows=len(features),feature_count=6,rtol=2e-6,atol=2e-6,max_absolute_error=float(np.max(abs(actual-expected))),passed=True),
        warm_timing=dict(rows_per_batch=1000,warmups=3,repetitions=20,wall_seconds=wall,cpu_seconds=cpu,median_seconds=float(np.median(wall)),p95_seconds=float(np.quantile(wall,.95)),max_seconds=max(wall)),
        numeric_process_memory=numeric_memory,whole_probe_memory=memory(),cgroup_limits=limits,cgroup_memory_peak_bytes=cgroup('memory.peak'),
        tmp_mount=tmp,candidate_read_only_mount=candidate_mount,loader_has_profile_binding=profile_binding,profile_binding_probe=capability,
        claim_scope='Pure ONNX numeric/resource compatibility in this exact image; no v3 pipeline end-to-end execution',
        inference_pipeline_executed=False,fitting_performed=False,final_data_or_labels_uploaded=False,production_model_overwritten=False)
    report['profile_binding_required']=True
    if not profile_binding:
        report['success']=False;report['cli_cases_skipped']='Current image lacks required profile binding; source/image evidence retained'
    else:
        try:
            cli=cli_cases(inference,root,meta)
            report['cli_cases']=cli['cases'];report['cli_validation_checks']=cli['checks'];report['success']=cli['success']
            report['inference_pipeline_executed']=True
            report['claim_scope']='Actual frozen-c13 CLI on four PACKAGED DEVELOPMENT views of two objects; numeric/resource and output-policy compatibility only, no final-science claim'
        except Exception as exc:
            report['success']=False;report['cli_error']=dict(type=type(exc).__name__,message=str(exc)[:2000])
    report['whole_probe_memory_after_cli']=memory()
    report['cgroup_memory_peak_bytes_after_cli']=cgroup('memory.peak')
    print(json.dumps(report,allow_nan=False),flush=True)
    if not report['success']:raise SystemExit(2)


if __name__=='__main__':main()
