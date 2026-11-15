"""Diagnostic feature counterfactuals, never an inference-time correction.

M101 is development data after the first frozen-v1 evaluation. These edits
are applied to every candidate and only diagnose model dependence. They do
not change observed feature rows, retrain a model or label unknown real tracks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from ml_inference.model import load_ranker

MODES=('original','peak_ratio_to_training_positive_median','snr_cap_at_training_positive_max',
       'epoch_count_to_six','snr_cv_to_training_positive_median','shape_median_and_snr_cap')


def counterfactual(observed, mode, reference):
    values=np.asarray(observed,np.float32).copy()
    if mode not in MODES:raise ValueError('unknown diagnostic mode')
    if mode in ('peak_ratio_to_training_positive_median','shape_median_and_snr_cap'):
        values[:,5]=np.median(reference[:,5])
    if mode in ('snr_cap_at_training_positive_max','shape_median_and_snr_cap'):
        values[:,2:4]=np.minimum(values[:,2:4],reference[:,2:4].max(axis=0))
    if mode=='epoch_count_to_six':values[:,0]=6
    if mode=='snr_cv_to_training_positive_median':values[:,4]=np.median(reference[:,4])
    return values


def run(model_dir, background_path, field_cache, output):
    ranker=load_ranker(model_dir)
    background=json.loads(Path(background_path).read_text())
    if ranker.metadata['sha256']!=background['model_sha256']:raise ValueError('model/evaluation mismatch')
    train=json.loads(Path(field_cache).read_text())['train']
    reference=np.asarray([x for f in train for x,m in zip(f['features'],f['matches'])if m>=0])
    observed=np.asarray([m['features']for t in background['trials']for m in t['recovery']['matches']])
    report=dict(model_sha256=ranker.metadata['sha256'],
                designation='development-only diagnostic feature counterfactuals, never model correction',
                note='Unknown real candidates remain unlabeled. Stable score ties inherit heuristic order.',
                reference_positive_rows=len(reference),
                training_positive_feature_median=np.median(reference,axis=0).tolist(),
                training_positive_feature_min=reference.min(axis=0).tolist(),
                training_positive_feature_max=reference.max(axis=0).tolist(),
                injected_match_feature_median=np.median(observed,axis=0).tolist(),
                injected_match_feature_min=observed.min(axis=0).tolist(),
                injected_match_feature_max=observed.max(axis=0).tolist(),
                source_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cases={})
    for mode in MODES:
        top1=top3=known=ties=0;positive_scores=[]
        control=np.asarray(background['unmodified_control']['detection']['feature_rows'],np.float32).reshape(-1,6)
        control_scores=ranker.score(counterfactual(control,mode,reference))
        for trial in background['trials']:
            x=np.asarray(trial['detection']['feature_rows'],np.float32).reshape(-1,6)
            scores=ranker.score(counterfactual(x,mode,reference))
            order=np.argsort(-scores,kind='stable').tolist()
            ids=[m['baseline_rank']-1 for m in trial['recovery']['matches']]
            known+=bool(ids);top1+=any(i in order[:1]for i in ids);top3+=any(i in order[:3]for i in ids)
            if len(scores)>1:ties+=int(np.count_nonzero(np.isclose(scores,scores.max(),atol=1e-8,rtol=0))>1)
            positive_scores.extend(float(scores[i])for i in ids)
        report['cases'][mode]=dict(known_detected=known,known_in_top1=top1,known_in_top3=top3,
                                   matched_score_median=float(np.median(positive_scores)),matched_score_max=max(positive_scores),
                                   unmodified_control_scores=control_scores.tolist(),trials_with_tied_top_score=ties)
    Path(output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    base=Path(__file__).resolve().parents[1]/'models'
    parser.add_argument('--model-dir',default=str(base/'archive'/'v1'))
    parser.add_argument('--background-evaluation',default=str(base/'archive'/'v1'/'real-background-evaluation.json'))
    parser.add_argument('--field-cache',default=str(base/'field-candidates.json'))
    parser.add_argument('--output',default=str(base/'v1-domain-ablation.json'))
    args=parser.parse_args();run(args.model_dir,args.background_evaluation,args.field_cache,args.output)


if __name__=='__main__':main()
