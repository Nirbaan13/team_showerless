"""Fresh-process frozen-graph dependency/numeric/resource probe; never fits."""
from __future__ import annotations
import builtins
import sys
BLOCKED={'sklearn','skl2onnx','joblib','training','tree_ranker','frontier','learning'}
original_import=builtins.__import__

def guarded(name,*args,**kwargs):
    if name.split('.')[0]in BLOCKED or name.startswith('experiments.v4.ranker'):
        raise RuntimeError('Inference attempted forbidden training dependency: '+name)
    return original_import(name,*args,**kwargs)

builtins.__import__=guarded
import argparse,json,os,time,hashlib,importlib.metadata
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--namespace-root',required=True);p.add_argument('--model',required=True);p.add_argument('--reference',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    sys.path.insert(0,args.namespace_root)
    available=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(available)})
    from experiments.v4.detection.runtime_model import load_ranker
    model=Path(args.model);assert hashlib.sha256((model/'ranker.onnx').read_bytes()).hexdigest()=='c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
    reference=Path(args.reference);payload=json.loads(reference.read_text());x=np.asarray(payload['features'],np.float32);expected=np.asarray(payload['scores'],np.float32)
    started=time.perf_counter();ranker=load_ranker(model);load_seconds=time.perf_counter()-started;actual=ranker.score(x);assert np.allclose(actual,expected,rtol=2e-6,atol=2e-6)
    timings=[];rows=x[:1000];ranker.score(rows)
    for _ in range(20):
        start=time.perf_counter();ranker.score(rows);timings.append(time.perf_counter()-start)
    forbidden=[name for name in sys.modules if name.split('.')[0]in BLOCKED or name.startswith('experiments.v4.ranker')];assert forbidden==[],forbidden
    status={line.split(':',1)[0]:int(line.split(':',1)[1].split()[0])for line in Path('/proc/self/status').read_text().splitlines()if line.startswith(('VmHWM:','VmRSS:'))}
    result=dict(model_sha256=ranker.metadata['sha256'],metadata_sha256=hashlib.sha256((model/'metadata.json').read_bytes()).hexdigest(),reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),numeric_rows=len(x),numeric_rtol=2e-6,numeric_atol=2e-6,max_abs_error=float(np.max(abs(actual-expected))),forbidden_training_imports=forbidden,training_import_guard_active=True,inference_only=True,hard_cgroup_memory_limit_enforced=False,one_logical_cpu_affinity=sorted(os.sched_getaffinity(0)),math_thread_environment={k:os.environ.get(k)for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']},onnx_load_seconds=load_seconds,warm_1000rows_repeats=20,warm_1000rows_median_ms=float(np.median(timings)*1000),warm_1000rows_p95_ms=float(np.quantile(timings,.95)*1000),linux_fresh_process_memory_kib=status,memory_scope='FreshLinuxprocessVmHWM, includesruntimepackages+model+3584numericprobes; excludesfeatureextraction/realCLI/VPScontainer',versions={name:importlib.metadata.version(name)for name in ['numpy','scipy','onnx','onnxruntime']},python=sys.version)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);temporary=output.with_suffix('.writing');temporary.write_text(json.dumps(result,indent=2)+'\n');temporary.replace(output);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
