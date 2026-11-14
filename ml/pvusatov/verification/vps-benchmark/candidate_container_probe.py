"""One constrained numeric/resource check; no FITS, fitting or pipeline claims."""
from __future__ import annotations
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
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
    print(json.dumps(report,allow_nan=False),flush=True)


if __name__=='__main__':main()
