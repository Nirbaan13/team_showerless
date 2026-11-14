"""Reproduce development-only RF feature ablations; never train on real labels."""
import argparse
import json
from pathlib import Path
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from training.train import feature_matrix,write_json
from training.train_v2 import ranking_report,selection_key


def fit_ablation(features,labels,parameters,ignored):
    values=np.asarray(features,np.float32).copy();values[:,ignored]=0
    return RandomForestClassifier(**parameters).fit(values,labels)


def native_diagnostic(forest,native):
    top1=top3=zeros=0;positive_scores=[]
    for trial in native['trials']:
        x=np.asarray(trial['detection']['feature_rows'],np.float32).reshape(-1,6)
        if not len(x):continue
        scores=forest.predict_proba(x)[:,1];order=np.argsort(-scores,kind='stable')
        ids=[m['baseline_rank']-1 for m in trial['recovery']['matches']]
        top1+=any(i in order[:1]for i in ids);top3+=any(i in order[:3]for i in ids)
        positive_scores.extend(scores[ids].tolist());zeros+=int(np.count_nonzero(scores[ids]==0))
    control=np.asarray(native['unmodified_control']['detection']['feature_rows'],np.float32).reshape(-1,6)
    return dict(known_detected=len(positive_scores),m101_development_top1=top1,m101_development_top3=top3,
                native_zero_scores=zeros,native_median_score=float(np.median(positive_scores)),
                control_scores=forest.predict_proba(control)[:,1].tolist()if len(control)else[])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-dir',required=True)
    args=parser.parse_args();directory=Path(args.experiment_dir)
    fields=json.loads((directory/'field-candidates.json').read_text())
    manifest=json.loads((directory/'training-manifest.json').read_text())
    native=json.loads((directory/'m101-development-evaluation.json').read_text())
    x,y=feature_matrix(fields['train']);report={}
    for name,ignored in [('full',[]),('ignore_epoch',[0]),('ignore_shape',[5]),
                         ('ignore_epoch_and_shape',[0,5]),('baseline_features_only',[3,4,5])]:
        forest=fit_ablation(x,y,manifest['selected_parameters'],ignored)
        score=lambda f:forest.predict_proba(np.asarray(f['features'],np.float32))[:,1]
        record=dict(ignored_features=ignored,validation_key=selection_key(fields['validation'],score),
                    validation=ranking_report(fields['validation'],score),**native_diagnostic(forest,native))
        report[name]=record;print(name,record['m101_development_top1'],record['native_zero_scores'],flush=True)
    write_json(directory/'feature-ablation.json',report)


if __name__=='__main__':main()
