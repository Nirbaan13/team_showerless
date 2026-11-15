"""Opaque research closure; no scientific imports, observations or model session."""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MODEL_SHA='c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
META_SHA='472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13'
SOURCES={**{n:'experiments/v4/association_validation/'+n+'.py'for n in ('freeze','execute','runner','accounting')},
 'policies':'experiments/v4/association_pilot/policies.py','features':'experiments/v4/detection/features.py',
 'runtime_model':'experiments/v4/detection/runtime_model.py','prepare':'releases/v4/runtime/ml_inference/prepare.py',
 'native_injections':'experiments/v4/evaluation/native_injections.py','worker_transport':'experiments/v4/evaluation/worker_transport.py',
 'native_helpers':'backend/inference/experiments/v3_evaluation/run_native.py',
 'native_psf':'backend/inference/training/evaluate_background.py','simulate':'backend/inference/training/simulate_v2.py',
 'training_init':'backend/inference/training/__init__.py',
 **{'legacy_'+n.strip('_'):'backend/inference/ml_inference/'+n+'.py'for n in ('__init__','contracts','detector','model')}}


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()


def read(path):
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('duplicate frozen JSON key')
            result[k]=v
        return result
    def invalid(v):raise ValueError('nonfinite frozen JSON')
    return json.loads(Path(path).read_bytes(),object_pairs_hook=pairs,parse_constant=invalid)


def ref(path):
    path=Path(path).resolve();return dict(path=str(path),sha256=digest(path))


def checked(value):
    path=Path(value['path']).resolve()
    if digest(path)!=value['sha256']:raise ValueError('research closure bytes differ')
    return path


def exact(name,value):
    path=checked(value);source=path.read_bytes()
    if hashlib.sha256(source).hexdigest()!=value['sha256']:raise ValueError('checked source changed')
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;exec(compile(source,str(path),'exec'),module.__dict__)
    module.__source_sha256__=value['sha256'];return module


def versions():
    return {'python':platform.python_version(),**{n:importlib.metadata.version(n)for n in ('numpy','scipy','astropy','onnx','onnxruntime')}}


def validate(path,anchor):
    if digest(path)!=anchor:raise ValueError('external research freeze anchor differs')
    v=read(path)
    if v.get('schema_version')!=1 or v.get('status')!='frozen' or v.get('versions')!=versions():raise ValueError('research freeze/environment differs')
    if set(v['sources'])!=set(SOURCES):raise ValueError('research source closure incomplete')
    for value in v['sources'].values():checked(value)
    p=read(checked(v['protocol']));selection=read(checked(v['selection']))
    if (p['threshold']!=4. or p['synthetic']['seed_first']!=4100000 or p['synthetic']['fields']!=1000
            or p['native']['seed_first']!=4110001 or p['native']['planned_injections']!=1620
            or p['native']['direction_ids']!=[0,2,4] or selection['selected_policy']!='learned_pair'
            or selection['selection_was_prospective_before_pilot_results']is not False):raise ValueError('fixed research selection/plan differs')
    if v['model']['artifact']['sha256']!=MODEL_SHA or v['model']['metadata']['sha256']!=META_SHA:raise ValueError('research model differs')
    for item in v['model'].values():checked(item)
    checked(v['calibration']);checked(v['native_plan']);checked(v['native_seed_amendment'])
    for name,sha in [('policies','854c2abf696dfa5094dfb79c0a39eeecdc796f5ac723bbe6f8727eceaccf271d'),('features','8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282'),('prepare','27ef087aa19f394eaf16ee19c0801ed6c7557a79a7ea77b3410445363f4624ec')]:
        if v['sources'][name]['sha256']!=sha:raise ValueError('declared scientific source differs')
    v['_protocol']=p;v['_anchor']=anchor;return v


def build(output):
    path=Path(output).resolve()
    if path.exists():raise ValueError('immutable freeze already exists')
    model=ROOT/'releases/v4/model'
    value=dict(schema_version=1,status='frozen',versions=versions(),protocol=ref(HERE/'protocol.json'),selection=ref(HERE/'selection-record.json'),
       sources={k:ref(ROOT/v)for k,v in SOURCES.items()},
       model=dict(artifact=ref(model/'ranker.onnx'),metadata=ref(model/'metadata.json')),
       calibration=ref(ROOT/'backend/inference/training/calibration/instrument-epsf-bank.npz'),
       native_plan=ref(ROOT/'experiments/v4/data/association_holdout/plan.json'),
       native_seed_amendment=ref(ROOT/'experiments/v4/data/association_holdout/retry-percent20/amendment.json'),
       native_release='Separate root-authorized exact handoff digest required before native reads; pending acquisition is not no-coverage')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    anchor=digest(path);validate(path,anchor);return dict(path=str(path),sha256=anchor)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();print(json.dumps(build(args.output)))
