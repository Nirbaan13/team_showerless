"""Evaluate an already frozen v2 model on reserved independent synthetic fields."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from ml_inference.model import load_ranker
from training.simulate_v2 import load_bank
from training.train_v2 import field,ranking_report,nuisance_summary
from training.train import write_json
from training.statistics import paired_bootstrap


def check_reserved_seeds(partitions,seeds):
    used={seed for values in partitions.values()for seed in values}
    if used.intersection(seeds):raise ValueError('reserved test fields overlap development')


def run(model_dir,calibration_bank,start,count):
    directory=Path(model_dir);ranker=load_ranker(directory)
    manifest=json.loads((directory/'training-manifest.json').read_text())
    seeds=list(range(start,start+count))
    check_reserved_seeds(manifest['partitions'],seeds)
    if hashlib.sha256(Path(calibration_bank).read_bytes()).hexdigest()!=manifest['calibration_bank_sha256']:
        raise ValueError('test calibration differs from frozen instrument knowledge')
    cfg=manifest['generator_configuration'];bank=load_bank(calibration_bank);started=time.monotonic()
    fields=[]
    for index,seed in enumerate(seeds):
        fields.append(field(seed,bank,extended=cfg['extended_backgrounds']and seed%cfg['extended_every_nth_field']==0,
                            varying_psf=cfg['varying_psf']))
        if index%50==0:print(f'final synthetic {index+1}/{count}, elapsed {time.monotonic()-started:.1f}s',flush=True)
    score=lambda f:ranker.score(np.asarray(f['features'],np.float32))
    report=dict(schema_version=1,designation='reserved independent synthetic field test after model freeze',
                model_sha256=ranker.metadata['sha256'],source_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                parent_field_seeds=seeds,configuration=cfg,baseline=ranking_report(fields,lambda f:np.asarray(f['baseline'])),
                random_forest=ranking_report(fields,score),nuisance_summary=nuisance_summary(fields),
                paired_field_bootstrap={str(k):paired_bootstrap(fields,score,k)for k in [1,3]},
                elapsed_seconds=time.monotonic()-started)
    write_json(directory/'final-synthetic-evaluation.json',report)
    write_json(directory/'final-field-candidates.json',fields)
    print(json.dumps({k:report[k]for k in ['baseline','random_forest']},indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir',required=True)
    parser.add_argument('--calibration-bank',default=str(Path(__file__).resolve().parent/'calibration'/'instrument-epsf-bank.npz'))
    parser.add_argument('--start',type=int,default=500000)
    parser.add_argument('--fields',type=int,default=400)
    args=parser.parse_args();run(args.model_dir,args.calibration_bank,args.start,args.fields)


if __name__=='__main__':main()
