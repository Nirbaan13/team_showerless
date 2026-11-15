"""All36 real cached estimators' branch-neighbor ONNX stress; no fitting."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,json,sys,time
import numpy as np
import joblib
from threshold_probes import threshold_probes
from datasets import BASE,sha
from validate_frontier import atomic_json,score_runtime
sys.path.insert(0,str(BASE))
from experiments.v4.detection import runtime_model
from code_binding import verify_module
import threshold_probes as probes_module


def run(args):
    source=Path(args.frontier);report=json.loads((source/'all-outcomes.json').read_text());assert report['complete']and len(report['experiments'])==36
    output=Path(args.output);output.mkdir(exist_ok=False,parents=True)
    code_checks=[verify_module(m)for m in [sys.modules[__name__],probes_module,runtime_model]]
    atomic_json(output/'invocation.json',dict(scope=__doc__,all_outcomes_sha256=sha(source/'all-outcomes.json'),source_checks=code_checks,numeric_only=True,original_science_denominators_unchanged=True))
    for c in code_checks:(output/(c['source_sha256']+'.source')).write_bytes(Path(c['path']).read_bytes())
    def one(record):
        start=time.monotonic();identifier=record['id']
        if record.get('error'):return dict(id=identifier,passes=False,error='prior export failure')
        try:
            fitted=Path('/tmp/spaceapps-v4-ranker/frontier-v1')/(identifier+'.json');fitting=json.loads(fitted.read_text());assert sha(fitting['estimator_path'])==fitting['estimator_sha256'];model=joblib.load(fitting['estimator_path']);ranker=runtime_model.load_ranker(record['model_directory']);indices=record['config']['selected_feature_indices']
            matrix,diagnostics=threshold_probes(model,indices,np.zeros(30,np.float32));reference=model.predict_proba(matrix[:,indices])[:,1];actual=score_runtime(ranker,matrix);close=bool(np.allclose(reference,actual,rtol=2e-6,atol=2e-6));result=dict(id=identifier,config=record['config'],passes=close,diagnostics=diagnostics,max_abs_error=float(np.max(abs(reference-actual))),score_rtol=2e-6,score_atol=2e-6,model_sha256=ranker.metadata['sha256'],probe_matrix_sha256=__import__('hashlib').sha256(matrix.tobytes()).hexdigest(),reference_sha256=__import__('hashlib').sha256(reference.tobytes()).hexdigest(),actual_sha256=__import__('hashlib').sha256(actual.tobytes()).hexdigest(),error=None,seconds=time.monotonic()-start)
        except Exception as error:
            import traceback
            result=dict(id=identifier,config=record['config'],passes=False,error=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc()),seconds=time.monotonic()-start)
        atomic_json(output/(identifier+'.json'),result);return result
    records=[]
    with ThreadPoolExecutor(max_workers=args.workers)as pool:
        for task in as_completed([pool.submit(one,r)for r in report['experiments']]):
            result=task.result();records.append(result);atomic_json(output/'progress.json',dict(experiments=records,expected=36));print(json.dumps(dict(completed=len(records),id=result['id'],passes=result['passes'],rows=result.get('diagnostics',{}).get('probe_rows'),error=result.get('error'))),flush=True)
    atomic_json(output/'all-threshold-results.json',dict(complete=len(records)==36,source_checks=code_checks,experiments=records,science_recovery_metrics_unchanged=True,selection_performed=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--frontier',default='/tmp/spaceapps-v4-ranker/frontier-onnx-v1');p.add_argument('--output',default='/tmp/spaceapps-v4-ranker/threshold-parity-v1');p.add_argument('--workers',type=int,default=4);args=p.parse_args()
    if not 1<=args.workers<=4:p.error('workers1..4')
    run(args)
