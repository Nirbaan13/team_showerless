"""Development PSF/threshold detector scan; whole-field paired comparisons only."""
import argparse,json,time,resource
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
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
    images,times,truth,mode,details=simulate(seed,_bank,extended=seed%3==0,varying_psf=True)
    row=dict(seed=seed,mode=mode,truth_count=len(truth),metadata=details,times=times.tolist(),methods={})
    for sigma in [.6,.8,1.2,1.6]:
        for snr in [3.,4.]:
            name=f'sigma{sigma}_snr{snr}';started=time.perf_counter();cpu=time.process_time()
            try:tracks=find_candidates(images,times,**{**SETTINGS,'psf_sigma':sigma,'min_snr':snr})
            except DetectionLimitError as e:row['methods'][name]=dict(error=str(e));continue
            scores=_ranker.score(np.asarray([t.features()for t in tracks],np.float32).reshape(-1,6));matches=[]
            for t in tracks:
                ids=[i for i,path in enumerate(truth)if np.all(np.linalg.norm(np.asarray(t.positions_xy)-path[list(t.epochs)],axis=1)<=1.5)]
                matches.append(ids[0]if ids else-1)
            order=np.argsort(-scores,kind='stable')
            row['methods'][name]=dict(candidates=len(tracks),matched_candidates=sum(i>=0 for i in matches),detected_objects=len(set(i for i in matches if i>=0)),objects_at_1=len(set(matches[i]for i in order[:1]if matches[i]>=0)),objects_at_3=len(set(matches[i]for i in order[:3]if matches[i]>=0)),features=[list(map(float,t.features()))for t in tracks],matches=matches,scores=scores.tolist(),wall_seconds=time.perf_counter()-started,cpu_seconds=time.process_time()-cpu,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    return row

def summary(rows):
    out={}
    if not rows:return out
    for name in rows[0]['methods']:
        methods=[r['methods'][name]for r in rows if 'error'not in r['methods'][name]]
        if not methods:out[name]=dict(errors=len(rows));continue
        out[name]=dict(fields=len(rows),errors=len(rows)-len(methods),truth=sum(r['truth_count']for r in rows),**{key:sum(m[key]for m in methods)for key in ['candidates','matched_candidates','detected_objects','objects_at_1','objects_at_3']},wall_p50=float(np.median([m['wall_seconds']for m in methods])),wall_p95=float(np.quantile([m['wall_seconds']for m in methods],.95)),cpu_seconds=sum(m['cpu_seconds']for m in methods),max_rss_mib=max(m['rss_mib']for m in methods))
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--start',type=int,default=1200000);p.add_argument('--fields',type=int,default=100);p.add_argument('--workers',type=int,default=6);p.add_argument('--output',required=True);a=p.parse_args();rows=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=a.workers)as pool:
        for i,row in enumerate(pool.map(one,range(a.start,a.start+a.fields)),1):
            rows.append(row)
            if i%20==0:print(json.dumps(dict(done=i,elapsed=time.monotonic()-started,summary=summary(rows))),flush=True)
    Path(a.output).write_text(json.dumps(dict(designation='v3 detector development only',summary=summary(rows),by_cadence={str(c):summary([r for r in rows if r['metadata']['cadence_family']==c])for c in range(4)},rows=rows),indent=2)+'\n');print(json.dumps(summary(rows),indent=2),flush=True)
if __name__=='__main__':main()
