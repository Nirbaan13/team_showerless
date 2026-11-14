"""Development confirmation of preselected sigma0.8 vs v2 sigma1.2, both SNR4.

Fresh whole fields; no model fitting or parameter selection in this script.
"""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import argparse,hashlib,json,resource,time
import numpy as np
from ml_inference.detector import find_candidates,DetectionLimitError
from ml_inference.model import load_ranker
from training.simulate_v2 import load_bank,simulate
from training.evaluate_background import SETTINGS
BASE=Path(__file__).resolve().parents[2];_bank=None;_ranker=None

def one(seed):
    global _bank,_ranker
    if _bank is None:_bank=load_bank(BASE/'training/calibration/instrument-epsf-bank.npz')
    if _ranker is None:_ranker=load_ranker(BASE/'models')
    images,times,truth,mode,details=simulate(seed,_bank,extended=seed%3==0,varying_psf=True);methods={}
    for sigma in [1.2,.8]:
        name=str(sigma);started=time.perf_counter();cpu=time.process_time()
        try:tracks=find_candidates(images,times,**{**SETTINGS,'psf_sigma':sigma})
        except DetectionLimitError as e:methods[name]=dict(error=str(e));continue
        features=[list(map(float,t.features()))for t in tracks];scores=_ranker.score(np.asarray(features,np.float32).reshape(-1,6));matches=[]
        for t in tracks:
            ids=[i for i,path in enumerate(truth)if np.all(np.linalg.norm(np.asarray(t.positions_xy)-path[list(t.epochs)],axis=1)<=1.5)]
            matches.append(ids[0]if ids else-1)
        order=np.argsort(-scores,kind='stable');methods[name]=dict(features=features,matches=matches,scores=scores.tolist(),candidates=len(tracks),matched_candidates=sum(i>=0 for i in matches),detected_objects=len(set(i for i in matches if i>=0)),objects_at_1=len(set(matches[i]for i in order[:1]if matches[i]>=0)),objects_at_3=len(set(matches[i]for i in order[:3]if matches[i]>=0)),wall_seconds=time.perf_counter()-started,cpu_seconds=time.process_time()-cpu,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    return dict(seed=seed,mode=mode,truth_count=len(truth),metadata=details,times_hours=times.tolist(),methods=methods)

def summary(rows):
    out={}
    for name in ['1.2','0.8']:
        methods=[r['methods'][name]for r in rows if 'error'not in r['methods'][name]]
        if not methods:out[name]=dict(errors=len(rows));continue
        out[name]=dict(fields=len(rows),errors=len(rows)-len(methods),truth=sum(r['truth_count']for r in rows),**{k:sum(m[k]for m in methods)for k in ['candidates','matched_candidates','detected_objects','objects_at_1','objects_at_3']},wall_p50=float(np.median([m['wall_seconds']for m in methods])),wall_p95=float(np.quantile([m['wall_seconds']for m in methods],.95)),max_rss_mib=max(m['rss_mib']for m in methods))
    return out

def paired(rows,repetitions=5000):
    valid=[r for r in rows if all('error'not in r['methods'][k]for k in ['1.2','0.8'])];rng=np.random.default_rng(8081201);out={}
    truth=np.array([r['truth_count']for r in valid])
    for key in ['detected_objects','objects_at_1','objects_at_3']:
        delta=np.array([r['methods']['0.8'][key]-r['methods']['1.2'][key]for r in valid]);samples=[]
        for _ in range(repetitions):
            ids=rng.integers(0,len(valid),len(valid));den=truth[ids].sum();samples.append(delta[ids].sum()/den if den else 0)
        out[key]=dict(paired_delta_objects=int(delta.sum()),delta_recall=float(delta.sum()/truth.sum()),field_bootstrap_95_percentile=np.quantile(samples,[.025,.975]).tolist(),resampling_unit='whole independent synthetic parent field')
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--start',type=int,default=1201000);p.add_argument('--fields',type=int,default=1000);p.add_argument('--workers',type=int,default=6);p.add_argument('--output',required=True);a=p.parse_args();rows=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=a.workers)as pool:
        for i,row in enumerate(pool.map(one,range(a.start,a.start+a.fields)),1):
            rows.append(row)
            if i%100==0:print(json.dumps(dict(done=i,elapsed_seconds=time.monotonic()-started,summary=summary(rows))),flush=True)
    report=dict(designation='v3 fresh-field development confirmation, not final',selection='sigma0.8 SNR4 chosen before these fields from 100-field pilot; compare fixed v2 sigma1.2 SNR4',source_sha256={str(f.relative_to(BASE)):hashlib.sha256(f.read_bytes()).hexdigest()for f in [Path(__file__),BASE/'training/simulate_v2.py',BASE/'ml_inference/detector.py']},model_sha256=load_ranker(BASE/'models').metadata['sha256'],summary=summary(rows),paired_field_bootstrap=paired(rows),by_cadence={str(c):summary([r for r in rows if r['metadata']['cadence_family']==c])for c in range(4)},rows=rows,elapsed_seconds=time.monotonic()-started)
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps({k:v for k,v in report.items()if k in ['summary','paired_field_bootstrap']},indent=2),flush=True)
if __name__=='__main__':main()
