"""Paired detector development benchmark; all known positions used after search."""
import argparse,json,resource,time,hashlib
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from experiments.v3_detection.digital_tracking import find_joint_candidates
from ml_inference.detector import find_candidates,DetectionLimitError
from ml_inference.model import load_ranker
from training.simulate_v2 import load_bank,simulate
from training.evaluate_background import SETTINGS
BASE=Path(__file__).resolve().parents[2]
_bank=None
_ranker=None

def one(spec):
    seed,statistic=spec if isinstance(spec,tuple)else(spec,"trimmed")
    global _bank,_ranker
    if _bank is None:_bank=load_bank(BASE/'training/calibration/instrument-epsf-bank.npz')
    if _ranker is None:_ranker=load_ranker(BASE/'models')
    images,times,truth,mode,details=simulate(seed,_bank,extended=seed%3==0,varying_psf=True)
    row=dict(seed=seed,truth_count=len(truth),mode=mode,cadence_family=details['cadence_family'],epoch_count=len(times),methods={})
    for name in ['baseline4','joint_full','joint_windows']:
        started=time.perf_counter();cpu=time.process_time();diagnostics=[]
        try:
            if name=='baseline4':
                tracks=find_candidates(images,times,**SETTINGS)
                scores=_ranker.score(np.asarray([t.features()for t in tracks],np.float32).reshape(-1,6))
            else:
                tracks=[]
                windows=[tuple(range(len(images)))]
                if name=='joint_windows'and len(images)>3:
                    windows.extend(tuple(range(i,i+3))for i in range(len(images)-2))
                for window in windows:
                    local,info=find_joint_candidates(images[list(window)],times[list(window)],max_candidates=100,max_displacement_px=48,threshold=6,statistic=statistic)
                    local=[replace(t,epochs=tuple(window))for t in local]
                    tracks.extend(local);diagnostics.append(info)
                scores=np.asarray([t.statistic for t in tracks]);order=np.argsort(-scores,kind='stable');dedup=[]
                for i in order:
                    t=tracks[i]
                    if any(len(set(t.epochs)&set(u.epochs))>=3 and np.median([np.linalg.norm(np.asarray(t.positions_xy)[t.epochs.index(e)]-np.asarray(u.positions_xy)[u.epochs.index(e)])for e in set(t.epochs)&set(u.epochs)])<2 for u in dedup):continue
                    dedup.append(t)
                tracks=dedup[:100];scores=np.asarray([t.statistic for t in tracks])
        except DetectionLimitError as exc:
            row['methods'][name]=dict(error=str(exc));continue
        matches=[]
        for t in tracks:
            ids=[i for i,path in enumerate(truth)if np.all(np.linalg.norm(np.asarray(t.positions_xy)-path[list(t.epochs)],axis=1)<=1.5)]
            matches.append(ids[0]if ids else -1)
        order=np.argsort(-scores,kind='stable')
        row['methods'][name]=dict(candidates=len(tracks),matched_candidates=sum(i>=0 for i in matches),detected_objects=len(set(i for i in matches if i>=0)),objects_at_1=len(set(matches[i]for i in order[:1]if matches[i]>=0)),objects_at_3=len(set(matches[i]for i in order[:3]if matches[i]>=0)),matches=matches,scores=list(map(float,scores)),wall_seconds=time.perf_counter()-started,cpu_seconds=time.process_time()-cpu,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,diagnostics=diagnostics)
    return row

def summary(rows):
    out={}
    for name in ['baseline4','joint_full','joint_windows']:
        methods=[r['methods'][name]for r in rows if 'error'not in r['methods'][name]]
        if not methods:out[name]=dict(errors=len(rows));continue
        out[name]=dict(fields=len(rows),errors=len(rows)-len(methods),truth=sum(r['truth_count']for r in rows),**{key:sum(m[key]for m in methods)for key in ['candidates','matched_candidates','detected_objects','objects_at_1','objects_at_3']},wall_p50=float(np.median([m['wall_seconds']for m in methods])),wall_p95=float(np.quantile([m['wall_seconds']for m in methods],.95)),cpu_seconds=sum(m['cpu_seconds']for m in methods),max_rss_mib=max(m['rss_mib']for m in methods))
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--start',type=int,default=1200200);p.add_argument('--fields',type=int,default=20);p.add_argument('--workers',type=int,default=6);p.add_argument('--output',required=True);p.add_argument('--statistic',choices=['sum','trimmed'],default='trimmed');a=p.parse_args();started=time.monotonic();rows=[]
    with ProcessPoolExecutor(max_workers=a.workers)as pool:
        for i,row in enumerate(pool.map(one,((seed,a.statistic)for seed in range(a.start,a.start+a.fields))),1):
            rows.append(row);print(json.dumps(dict(done=i,elapsed_seconds=time.monotonic()-started,summary=summary(rows))),flush=True)
    Path(a.output).write_text(json.dumps(dict(designation='v3 development only',statistic=a.statistic,source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path(__file__),Path(__file__).with_name('digital_tracking.py'),Path(__file__).with_name('digital_tracking.cpp')]},summary=summary(rows),by_cadence={str(c):summary([r for r in rows if r['cadence_family']==c])for c in range(4)},rows=rows,elapsed_seconds=time.monotonic()-started),indent=2)+'\n')
if __name__=='__main__':main()
