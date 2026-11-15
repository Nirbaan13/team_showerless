"""Version-bound V4 TRAIN/DEV synthetic whole-field measured-feature cache.

No FINAL mode exists here. All truth-derived labels/diagnostics are evaluated
only AFTER the fixed detector, observable-only extractor and C13 scorer run.
"""
from __future__ import annotations
import os
for _key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[_key]='1'
from concurrent.futures import ProcessPoolExecutor
import argparse,gzip,hashlib,json,sys,time,traceback
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(BASE/'backend/inference'),str(BASE/'experiments/v4/detection')]
from training.simulate_v2 import simulate,load_bank
from ml_inference.detector import find_candidates,baseline_score,difference_frames,_detect_peaks
from ml_inference.model import load_ranker
from features import FeatureContext,FEATURE_NAMES,FEATURE_VERSION,FEATURE_CONTRACT_SHA256
BANK=None;RANKER=None;EXPECTED_SOURCES=None;PARTITION=None
PROFILE=dict(min_snr=4.,max_peaks=100,psf_sigma=.8,min_speed=.5,max_speed=60.,match_radius=1.4,min_epochs=3,min_support=.8,leave_one_out=True)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def initialize(bank,sources,partition):
    global BANK,RANKER,EXPECTED_SOURCES,PARTITION
    PARTITION=partition
    BANK=load_bank(bank);RANKER=load_ranker(BASE/'releases/v3/model');EXPECTED_SOURCES=sources
    if any(sha(path)!=expected for path,expected in sources.items()):raise ValueError('source changed before worker initialization')


def generate(seed):
    started=time.monotonic()
    try:
        images,times,truth,mode,metadata=simulate(seed,BANK,extended=seed%3==0,varying_psf=True)
        tracks=find_candidates(images,times,**PROFILE)
        context=FeatureContext(images,times,psf_sigma=.8,outlier=None,bloom=None)
        extracted=context.extract(tracks)
        six=np.asarray([track.features() for track in tracks],np.float64).reshape(-1,6)
        scores=RANKER.score(six)
        residuals=difference_frames(images,True)
        peaks=[len(_detect_peaks(frame,np.isfinite(frame),.8,4.,100,.8)) for frame in residuals]
        # Everything above is observable-only; injected truth enters evaluation now.
        matches=[]
        for track in tracks:
            positions=np.asarray(track.positions_xy)
            distances=[np.linalg.norm(positions-path[list(track.epochs)],axis=1) for path in truth]
            matching=[i for i,d in enumerate(distances) if np.all(d<=1.5)]
            matches.append(min(matching,key=lambda i:float(distances[i].mean())) if matching else -1)
        latent=hashlib.sha256()
        for array in [images,times,*truth]:latent.update(np.asarray(array,dtype='<f8').tobytes())
        return dict(seed=seed,partition=PARTITION,mode=mode,features=six.tolist(),features_v4=extracted['features_v4'].tolist(),candidate_ids=extracted['candidate_ids'],feature_diagnostics=extracted['diagnostics'],candidate_epochs=[list(map(int,t.epochs)) for t in tracks],candidate_positions_xy=[np.asarray(t.positions_xy).tolist() for t in tracks],matches=matches,truth_count=len(truth),baseline=[float(baseline_score(t)) for t in tracks],scores=scores.tolist(),scores_c13=scores.tolist(),times_hours=times.tolist(),metadata=metadata,peaks_per_epoch=peaks,peak_cap_reached=any(p>=100 for p in peaks),truth_positions_xy=[path.tolist() for path in truth],latent_sha256=latent.hexdigest(),wall_seconds=time.monotonic()-started,error=None)
    except Exception as error:
        # A complete planned-field ledger cannot disappear into an empty success.
        return dict(seed=seed,error=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc()),evaluation_complete=False,wall_seconds=time.monotonic()-started)


def run(args):
    allowed=dict(train=(3000000,3005000),validation=(3100000,3101000),development=(3800000,3900000))
    low,high=allowed[args.partition]
    if args.fields<1 or not low<=args.start<args.start+args.fields<=high:raise ValueError('seed range outside registered TRAIN/DEV reservation; FINAL generation forbidden')
    if not 1<=args.workers<=6:raise ValueError('bounded workers must be1..6')
    sources={str(p):sha(p) for p in [Path(__file__),BASE/'experiments/v4/detection/features.py',BASE/'backend/inference/training/simulate_v2.py',BASE/'backend/inference/training/evaluate_background.py',BASE/'backend/inference/ml_inference/detector.py',BASE/'backend/inference/ml_inference/model.py']}
    bank=Path(args.bank);output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise ValueError('output exists; preserve previous cache')
    invocation=dict(schema_version=4,partition=args.partition,seeds=list(range(args.start,args.start+args.fields)),feature_names=list(FEATURE_NAMES),feature_version=FEATURE_VERSION,feature_contract_sha256=FEATURE_CONTRACT_SHA256,detector_settings=PROFILE,source_sha256=sources,bank_sha256=sha(bank),baseline_model_sha256=sha(BASE/'releases/v3/model/ranker.onnx'),synthetic_masks='missionFLAGS unavailable; None honestly supplied, qualityavailability0',generator_configuration=dict(extended_every_nth_field=3,varying_psf=True),truth_access_order='detect -> observablefeatures -> C13score -> labels',output=str(output))
    Path(str(output)+'.invocation.json').write_text(json.dumps(invocation,indent=2)+'\n')
    started=time.monotonic();rows=[]
    with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(str(bank),sources,args.partition)) as pool:
        for row in pool.map(generate,invocation['seeds'],chunksize=4):
            rows.append(row)
            if len(rows)%100==0 or len(rows)==args.fields:
                print(json.dumps(dict(completed=len(rows),planned=args.fields,errors=sum(r['error'] is not None for r in rows),candidates=sum(len(r.get('features',[])) for r in rows),seconds=round(time.monotonic()-started,1))),flush=True)
    changed={path:dict(expected=expected,actual=sha(path)) for path,expected in sources.items() if sha(path)!=expected}
    complete=not changed and all(r['error'] is None for r in rows)
    payload=dict(invocation,fields=rows,elapsed_seconds=time.monotonic()-started,evaluation_complete=complete,source_changes_during_generation=changed,planned_field_count=args.fields,completed_field_count=len(rows))
    temporary=Path(str(output)+'.tmp')
    with gzip.open(temporary,'wt') as handle:json.dump(payload,handle,allow_nan=False)
    temporary.replace(output)
    record=dict(path=str(output),sha256=sha(output),bytes=output.stat().st_size,evaluation_complete=complete,planned=args.fields,error_fields=sum(r['error'] is not None for r in rows),source_changes=changed)
    Path(str(output)+'.manifest.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
    if not complete:raise RuntimeError('incomplete or source-mutated cache retained as failure evidence')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--partition',choices=['train','validation','development'],required=True);p.add_argument('--start',type=int,required=True);p.add_argument('--fields',type=int,required=True);p.add_argument('--workers',type=int,default=4);p.add_argument('--bank',default=str(BASE/'backend/inference/training/calibration/instrument-epsf-bank.npz'));p.add_argument('--output',required=True);run(p.parse_args())
