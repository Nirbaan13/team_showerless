"""Paired whole-field development ablation; truth is consumed only after detection."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib,json,os,resource,time
from pathlib import Path
import numpy as np
from ml_inference.detector import find_candidates, baseline_score, DetectionLimitError
from ml_inference.model import load_ranker
from training.simulate_v2 import load_bank, simulate
from training.evaluate_background import SETTINGS

BASE=Path(__file__).resolve().parents[2]
BANK=BASE/'training/calibration/instrument-epsf-bank.npz'
_bank=None
_ranker=None

def one(seed):
    global _bank,_ranker
    if _bank is None:_bank=load_bank(BANK)
    if _ranker is None:_ranker=load_ranker(BASE/'models')
    images,times,truth,mode,details=simulate(seed,_bank,extended=seed%3==0,varying_psf=True)
    row=dict(seed=seed,mode=mode,truth_count=len(truth),cadence_family=details['cadence_family'],epoch_count=len(times),methods={})
    for threshold in [4.,3.,2.5,2.]:
        started=time.perf_counter(); cpu=time.process_time()
        try:
            tracks=find_candidates(images,times,**{**SETTINGS,'min_snr':threshold})
        except DetectionLimitError as exc:
            row['methods'][str(threshold)]=dict(error=str(exc));continue
        wall=time.perf_counter()-started; cpu=time.process_time()-cpu
        scores=_ranker.score(np.asarray([t.features()for t in tracks],np.float32).reshape(-1,6))
        matches=[]
        for track in tracks:
            ids=[i for i,path in enumerate(truth)if np.all(np.linalg.norm(np.asarray(track.positions_xy)-path[list(track.epochs)],axis=1)<=1.5)]
            matches.append(ids[0]if ids else -1)
        candidate=dict(candidates=len(tracks),matched_candidates=sum(i>=0 for i in matches),
                       detected_objects=len(set(i for i in matches if i>=0)),wall_seconds=wall,cpu_seconds=cpu,
                       rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                       features=[list(map(float,t.features()))for t in tracks],matches=matches,
                       baseline=[float(baseline_score(t))for t in tracks],rf_scores=scores.tolist())
        for name,order in [('baseline',range(len(tracks))),('frozen_v2',np.argsort(-scores,kind='stable'))]:
            for k in [1,3]:candidate[f'{name}_objects_at_{k}']=len(set(matches[i]for i in list(order)[:k]if matches[i]>=0))
        row['methods'][str(threshold)]=candidate
    return row

def summary(rows):
    result={}
    for threshold in ['4.0','3.0','2.5','2.0']:
        valid=[r for r in rows if 'error'not in r['methods'][threshold]]; methods=[r['methods'][threshold]for r in valid]
        result[threshold]=dict(fields=len(rows),complete_fields=len(valid),error_fields=len(rows)-len(valid),truth=sum(r['truth_count']for r in rows),
             candidates=sum(m['candidates']for m in methods),matched_candidates=sum(m['matched_candidates']for m in methods),detected_objects=sum(m['detected_objects']for m in methods),
             wall_p50=float(np.median([m['wall_seconds']for m in methods])),wall_p95=float(np.quantile([m['wall_seconds']for m in methods],.95)),
             cpu_seconds=sum(m['cpu_seconds']for m in methods),max_worker_rss_mib=max(m['rss_mib']for m in methods),
             **{f'{name}_objects_at_{k}':sum(m[f'{name}_objects_at_{k}']for m in methods)for name in ['baseline','frozen_v2']for k in [1,3]})
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--start',type=int,default=1200000);parser.add_argument('--fields',type=int,default=100);parser.add_argument('--workers',type=int,default=6);parser.add_argument('--output',required=True);args=parser.parse_args()
    started=time.monotonic();rows=[]
    with ProcessPoolExecutor(max_workers=args.workers)as pool:
        for i,row in enumerate(pool.map(one,range(args.start,args.start+args.fields)),1):
            rows.append(row)
            if i%10==0:print(json.dumps(dict(done=i,elapsed_seconds=time.monotonic()-started,summary=summary(rows))),flush=True)
    report=dict(designation='v3 development only; paired fresh whole fields; no independent final claim',model_sha256=load_ranker(BASE/'models').metadata['sha256'],source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),generator_configuration=dict(extended_every_nth=3,varying_psf=True),start=args.start,fields=args.fields,workers=args.workers,summary=summary(rows),by_cadence={str(c):summary([r for r in rows if r['cadence_family']==c])for c in range(4)},rows=rows,elapsed_seconds=time.monotonic()-started)
    Path(args.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(report['summary'],indent=2),flush=True)
if __name__=='__main__':main()
