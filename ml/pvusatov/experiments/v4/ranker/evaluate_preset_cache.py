"""Development-only preset eligibility; labels are never fitting inputs."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
import joblib
from datasets import BASE,sha,FEATURE_NAMES,FEATURE_CONTRACT_SHA256
from frontier import configurations,resolved_configurations


def run(args):
    cache=BASE/'experiments/v4/detection/results/preset-feature-cache.json'
    if sha(cache)!='0acd2fff5d0427cc2179641606db9d918c78725af3c6ae127940b08410dabf3d':raise ValueError('preset source cache changed')
    payload=json.loads(cache.read_text());assert payload['fitting_forbidden'] is True
    assert payload['feature_names']==list(FEATURE_NAMES)and payload['feature_contract_sha256']==FEATURE_CONTRACT_SHA256
    estimator_root=Path(args.estimator_root);reports=[]
    for config in configurations()+resolved_configurations():
        path=estimator_root/(config['id']+'.json')
        if not path.exists():reports.append(dict(id=config['id'],config=config,status='waiting_for_fit'));continue
        fitting=json.loads(path.read_text())
        if fitting['error']:reports.append(dict(id=config['id'],config=config,status='fit_failed',error=fitting['error']));continue
        model_path=Path(fitting['estimator_path'])
        if sha(model_path)!=fitting['estimator_sha256']:raise ValueError('estimator bytes changed')
        model=joblib.load(model_path);cases={}
        for name,field in payload['cases'].items():
            full=np.asarray(field['features_v4'],np.float32).reshape(-1,30)
            score=model.predict_proba(full[:,config['selected_feature_indices']])[:,1] if len(full)else np.empty(0)
            order=np.argsort(-score,kind='stable');known=np.flatnonzero(np.asarray(field['matches'])>=0)
            ranks=[int(np.flatnonzero(order==i)[0]+1)for i in known]
            bloom=field['bloom_tracks'];quota=max(3,100-len(bloom));published_bloom=bloom[:max(0,100-min(len(full),quota))]
            cases[name]=dict(known_residual_ranks=ranks,residual_candidates=len(full),known_bloom_retained=any(b.get('known_target_match')for b in published_bloom),bloom_unscored=all(b['score']is None and b['ml_ranked']is False and b['photometry']is False for b in bloom),all_unmatched_residual_identities='UNKNOWN; never negatives')
        d2=cases['comet-d2']['known_residual_ranks'];d6=cases['comet-d6']['known_residual_ranks']
        checks=dict(d2_rank1=bool(d2)and min(d2)<=1,d6_rank_le4=bool(d6)and min(d6)<=4,vesta_known_bloom_retained=all(cases[name]['known_bloom_retained']for name in ['vesta-d3','vesta-d6']),bloom_always_unscored=all(c['bloom_unscored']for c in cases.values()))
        reports.append(dict(id=config['id'],config=config,status='scored_sklearn_development_only',cases=cases,eligibility_checks=checks,passes_preset_gate=all(checks.values()),d6_preferred_rank_le3=bool(d6)and min(d6)<=3,actual_onnx_preset_parity_still_required=True))
    output=dict(scope='Existing four DEVELOPMENT views/two known objects, not independent survey evidence',fitting_performed=False,preset_cache_sha256=sha(cache),estimator_root=str(estimator_root),expected_configurations=36,complete=all(r['status']!='waiting_for_fit'for r in reports),model_selection_performed=False,experiments=reports)
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(output,indent=2)+'\n')
    for r in reports:
        if r['status'].startswith('scored'):print(json.dumps(dict(id=r['id'],family=r['config']['family'],subset=r['config']['subset'],native_mass=r['config']['native_mass'],pointwise=r['config']['pointwise_fraction'],passes=r['passes_preset_gate'],d2=r['cases']['comet-d2']['known_residual_ranks'],d6=r['cases']['comet-d6']['known_residual_ranks'])),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--estimator-root',default='/tmp/spaceapps-v4-ranker/frontier-v1');p.add_argument('--output',default='/tmp/spaceapps-v4-ranker/preset-eligibility-stageA.json');run(p.parse_args())
