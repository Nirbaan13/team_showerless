"""Development-only 2x2 physical background/PSF generator ablation.

No final field is read. All models use fixed pilot-selected RF parameters,
identical seed groups and native instrument calibration, retaining all features.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from training.simulate_v2 import load_bank
from training.train import feature_matrix,write_json
from training.train_v2 import field,ranking_report,selection_key
from training.ablate_v2 import fit_ablation,native_diagnostic


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    root=Path(__file__).resolve().parents[1]
    parser.add_argument('--train-fields',type=int,default=300)
    parser.add_argument('--validation-fields',type=int,default=100)
    parser.add_argument('--calibration-bank',default=str(root/'training'/'calibration'/'instrument-epsf-bank.npz'))
    parser.add_argument('--native-development',default=str(root/'models'/'experiments'/'v2-pilot'/'m101-development-evaluation.json'))
    parser.add_argument('--output',default=str(root/'models'/'v2-development-ablation.json'))
    args=parser.parse_args();bank=load_bank(args.calibration_bank)
    native=json.loads(Path(args.native_development).read_text())
    parameters=dict(n_estimators=150,min_samples_leaf=12,max_depth=16,max_features=1.,
                    class_weight='balanced',random_state=42,n_jobs=1)
    report=dict(designation='M101 and synthetic development only, final field unopened',
                fixed_forest_parameters=parameters,train_seeds=[10000,10000+args.train_fields-1],
                validation_seeds=[300000,300000+args.validation_fields-1],
                generator_source_sha256=hashlib.sha256((root/'training'/'simulate_v2.py').read_bytes()).hexdigest(),
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cases={})
    for extended,varying in [(False,False),(True,False),(False,True),(True,True)]:
        started=time.monotonic();name=f'extended{int(extended)}_varypsf{int(varying)}'
        train=[field(seed,bank,extended=extended,varying_psf=varying)for seed in range(10000,10000+args.train_fields)]
        validation=[field(seed,bank,extended=extended,varying_psf=varying)for seed in range(300000,300000+args.validation_fields)]
        x,y=feature_matrix(train);forest=fit_ablation(x,y,parameters,[])
        score=lambda f:forest.predict_proba(np.asarray(f['features'],np.float32))[:,1]
        negative=x[y==0];positive=x[y==1]
        record=dict(extended=extended,varying_psf=varying,training_candidates=len(x),training_positive_candidates=int(y.sum()),
                    negative_epoch4plus=int(np.count_nonzero(negative[:,0]>=4)),
                    negative_epoch4plus_peakratio_below2_5=int(np.count_nonzero((negative[:,0]>=4)&(negative[:,5]<2.5))),
                    positive_epoch4plus=int(np.count_nonzero(positive[:,0]>=4)),
                    positive_epoch4plus_peakratio_below2_5=int(np.count_nonzero((positive[:,0]>=4)&(positive[:,5]<2.5))),
                    validation_key=selection_key(validation,score),validation=ranking_report(validation,score),
                    elapsed_seconds=time.monotonic()-started,**native_diagnostic(forest,native))
        report['cases'][name]=record;write_json(Path(args.output),report)
        print(name,json.dumps({key:record[key]for key in ['training_positive_candidates','negative_epoch4plus',
              'negative_epoch4plus_peakratio_below2_5','m101_development_top1','native_zero_scores','validation_key','elapsed_seconds']}),flush=True)


if __name__=='__main__':main()
