"""Offline v3 grouped synthetic-feature cache; does not read reserved pixels."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import time
from training.train_v2 import field
from training.simulate_v2 import load_bank

BANK = None

def initialize(path):
    global BANK
    BANK = load_bank(path)

def generate(seed):
    return field(seed, BANK, extended=seed % 3 == 0, varying_psf=True)

def run(args):
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    seeds = list(range(args.start, args.start + args.fields))
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers, initializer=initialize, initargs=(args.bank,)) as pool:
        rows = []
        for row in pool.map(generate, seeds, chunksize=4):
            rows.append(row)
            if len(rows) % 50 == 0 or len(rows) == len(seeds):
                print(json.dumps(dict(fields=len(rows),total=len(seeds),elapsed_seconds=round(time.monotonic()-started,1), candidates=sum(len(r['features']) for r in rows), positives=sum(sum(m>=0 for m in r['matches']) for r in rows))),flush=True)
    payload = dict(schema_version=1,designation=args.partition,group_unit='independent synthetic field',fields=rows,
                   seeds=seeds,source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path('backend/inference/training/simulate_v2.py'),Path('backend/inference/training/train_v2.py'),Path('backend/inference/ml_inference/detector.py')]},
                   bank_sha256=hashlib.sha256(Path(args.bank).read_bytes()).hexdigest(),elapsed_seconds=time.monotonic()-started)
    with gzip.open(output,'wt') as handle:json.dump(payload,handle,allow_nan=False)
    print('CACHE '+str(output)+' '+hashlib.sha256(output.read_bytes()).hexdigest(),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bank',default='backend/inference/training/calibration/instrument-epsf-bank.npz')
    p.add_argument('--partition',choices=['train','validation','development'],required=True)
    p.add_argument('--start',type=int,required=True)
    p.add_argument('--fields',type=int,required=True)
    p.add_argument('--workers',type=int,default=10)
    p.add_argument('--output',required=True)
    run(p.parse_args())
