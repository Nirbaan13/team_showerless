"""Generate grouped six-measured-feature caches for the experimental narrow filter."""
import argparse,gzip,hashlib,json,time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from ml_inference.detector import find_candidates,baseline_score,difference_frames,_detect_peaks
from training.simulate_v2 import load_bank,simulate
from training.evaluate_background import SETTINGS
BASE=Path(__file__).resolve().parents[2];_bank=None

def one(seed):
    global _bank
    if _bank is None:_bank=load_bank(BASE/'training/calibration/instrument-epsf-bank.npz')
    images,times,truth,mode,details=simulate(seed,_bank,extended=seed%3==0,varying_psf=True)
    tracks=find_candidates(images,times,**{**SETTINGS,'psf_sigma':.8});matches=[]
    for track in tracks:
        distances=[np.linalg.norm(np.asarray(track.positions_xy)-path[list(track.epochs)],axis=1)for path in truth]
        ids=[i for i,d in enumerate(distances)if np.all(d<=1.5)]
        matches.append(min(ids,key=lambda i:distances[i].mean())if ids else-1)
    peaks=[len(_detect_peaks(d,np.isfinite(d),.8,4.,100,.8))for d in difference_frames(images,True)]
    return dict(seed=seed,mode=mode,features=[list(map(float,t.features()))for t in tracks],matches=matches,truth_count=len(truth),baseline=[float(baseline_score(t))for t in tracks],times_hours=times.tolist(),metadata=details,peaks_per_epoch=peaks,peak_cap_reached=any(p>=100 for p in peaks))

def main():
    p=argparse.ArgumentParser();p.add_argument('--start',type=int,required=True);p.add_argument('--fields',type=int,required=True);p.add_argument('--partition',required=True,choices=['train','validation']);p.add_argument('--workers',type=int,default=4);p.add_argument('--output',required=True);a=p.parse_args();seeds=list(range(a.start,a.start+a.fields));fields=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=a.workers)as pool:
        for i,field in enumerate(pool.map(one,seeds),1):
            fields.append(field)
            if i%100==0:print(json.dumps(dict(partition=a.partition,done=i,elapsed_seconds=time.monotonic()-started)),flush=True)
    report=dict(schema_version=1,designation='v3 synthetic development '+a.partition,partition=a.partition,seeds=seeds,fields=fields,detector_settings={**SETTINGS,'psf_sigma':.8},generator_configuration=dict(extended_every_nth_field=3,varying_psf=True),source_sha256={str(f.relative_to(BASE)):hashlib.sha256(f.read_bytes()).hexdigest()for f in [Path(__file__),BASE/'training/simulate_v2.py',BASE/'ml_inference/detector.py']},elapsed_seconds=time.monotonic()-started)
    with gzip.open(a.output,'wt')as s:json.dump(report,s,allow_nan=False)
    print(json.dumps(dict(output=a.output,sha256=hashlib.sha256(Path(a.output).read_bytes()).hexdigest(),field_count=len(fields),candidates=sum(len(f['matches'])for f in fields),positive_candidates=sum(sum(m>=0 for m in f['matches'])for f in fields))),flush=True)
if __name__=='__main__':main()
