"""Single-system validation selection across frozen sigma1.2 and sigma0.8 grids.

No model fitting, final pixels or final synthetic generation. Legacy score-only
same-detector ablations remain separate from deployed-system comparison.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import joblib
import numpy as np
import train_grid as grid
from select_cached import qualifies,key,write
from selection_integrity import validate_hashes,validate_relocated_source_hashes,normalize_native_pair,paired_native_report
from experiments.v3_evaluation.paired import paired_report
from ml_inference.model import load_ranker

V2_SHA='dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9'


def scores(fields,model):
    scorer=grid.scorer(fields,model)
    return [scorer(f) for f in fields]


def native_view(report,side):
    primary=report['common_attributable'];raw=report['all_planned'];r=primary[side]
    return dict(planned_injections=raw['truth_count'],eligible_injections=primary['truth_count'],detected=r['detected'],top1=r['top1'],top3=r['top3'],
                macro_parent_recall1=r['macro_recall1'],macro_parent_recall3=r['macro_recall3'],independent_groups=primary['independent_groups'],
                all_planned=raw[side],common_attributable=r,finite_center_ge3=report['common_finite_center_ge3'][side],
                attribution_excluded_trials=report['attribution_excluded_trials'],native_unknowns_unlabeled=True)


def make_report(baseline_fields,candidate_fields,baseline_values,candidate_values,synthetic,bootstrap_samples=10000):
    paired=paired_native_report(baseline_fields,candidate_fields,baseline_values,candidate_values,bootstrap_samples)
    return dict(native=native_view(paired,'candidate'),synthetic=synthetic,paired_native_system=paired)


def load_profiles(baseline_paths,candidate_dir):
    baseline=[];narrow=[];provenance=[]
    for path in baseline_paths:
        left=grid.read(path)
        if left['partition']!='validation' or left['detector_settings']['min_speed']!=.5 or left['detector_settings']['psf_sigma']!=1.2:raise ValueError('primary baseline must be validation sigma1.2/minspeed0.5')
        other=Path(candidate_dir)/(Path(path).name.removesuffix('.json.gz')+'-sigma08.json.gz')
        right=grid.read(other)
        if right['detector_settings']['psf_sigma']!=.8:raise ValueError('candidate profile must be sigma0.8')
        a,b=normalize_native_pair(left,right)
        baseline.extend(a['fields']);narrow.extend(b['fields'])
        provenance.append(dict(baseline_cache=path,baseline_sha256=grid.sha(path),candidate_cache=str(other),candidate_sha256=grid.sha(other),metadata_restoration=b.get('metadata_restoration')))
    if len({f['parent_id'] for f in baseline})!=11:raise ValueError('complete eleven-parent primary validation required')
    return baseline,narrow,provenance


def run(args):
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    baseline_native,narrow_native,native_provenance=load_profiles(args.baseline_native,args.candidate_native_dir)
    baseline_synthetic=grid.read(args.baseline_synthetic)['fields']
    v2ranker=load_ranker(args.baseline_model)
    if v2ranker.metadata['sha256']!=V2_SHA:raise ValueError('deployed frozen v2 comparator changed')
    v2=grid.v2adapter(v2ranker)
    baseline_native_v2=scores(baseline_native,v2)
    baseline_native_heuristic=[np.asarray(f['baseline']) for f in baseline_native]
    baseline_synthetic_v2=scores(baseline_synthetic,v2)
    baseline_synthetic_heuristic=[np.asarray(f['baseline']) for f in baseline_synthetic]
    bsynthetic=grid.synthetic_report(baseline_synthetic,grid.scorer(baseline_synthetic,v2))
    asynthetic=grid.synthetic_report(baseline_synthetic,lambda f:np.asarray(f['baseline']))
    all_outcomes=[];profile_reports={};fit_manifests={};resolved_sources={}
    for cache_arg in args.candidate_cache:
        cache=Path(cache_arg);inputs=json.loads((cache/'inputs.json').read_text())
        validate_hashes(inputs['input_sha256'])
        resolved_sources[str(cache)]=validate_relocated_source_hashes(inputs['source_sha256'])
        fitting=inputs['inputs'];fit_manifests[str(cache)]=inputs
        candidate_synthetic=grid.read(fitting['synthetic_validation'])['fields']
        settings=inputs.get('detector_settings',grid.read(fitting['native_train'][0])['detector_settings'])
        sigma=settings['psf_sigma']
        if settings['min_speed']!=.5 or sigma not in [1.2,.8]:raise ValueError('unregistered primary profile')
        candidate_native=baseline_native if sigma==1.2 else narrow_native
        candidate_native_heuristic=[np.asarray(f['baseline']) for f in candidate_native]
        # Baseline/candidate options and full latent identities are validated even
        # for zero-candidate trials before any candidate eligibility is computed.
        reference=paired_native_report(baseline_native,candidate_native,baseline_native_v2,candidate_native_heuristic)
        href=paired_native_report(baseline_native,candidate_native,baseline_native_heuristic,candidate_native_heuristic)
        v2_reference=dict(native=native_view(reference,'baseline'),synthetic=bsynthetic)
        old_heuristic=dict(native=native_view(href,'baseline'),synthetic=asynthetic)
        candidate_heuristic=dict(native=native_view(reference,'candidate'),synthetic=grid.synthetic_report(candidate_synthetic,lambda f:np.asarray(f['baseline'])))
        same_v2_native=scores(candidate_native,v2)
        same_v2_synthetic=scores(candidate_synthetic,v2)
        records=[json.loads(p.read_text()) for p in sorted(cache.glob('*.json')) if p.name not in ['inputs.json','grid-progress.json']]
        expected=inputs.get('planned_configurations',48)
        if len(records)!=expected:raise ValueError('incomplete primary forest grid')
        profile_label='sigma'+str(sigma)
        profile_reports[profile_label]=dict(detector_settings=settings,baseline_v2=v2_reference,deployed_heuristic=old_heuristic,candidate_profile_heuristic=candidate_heuristic,
            same_detector_v2=dict(native=grid.native_report(candidate_native,grid.scorer(candidate_native,v2)),synthetic=grid.synthetic_report(candidate_synthetic,grid.scorer(candidate_synthetic,v2))))
        for i,record in enumerate(records,1):
            validate_hashes({record['estimator_cache_path']:record['estimator_cache_sha256']})
            forest=joblib.load(record['estimator_cache_path'])
            nv=scores(candidate_native,forest);sv=scores(candidate_synthetic,forest)
            native_paired=paired_native_report(baseline_native,candidate_native,baseline_native_v2,nv)
            synthetic_paired=paired_report(baseline_synthetic,candidate_synthetic,baseline_synthetic_v2,sv)
            score_lookup={id(f):values for f,values in zip(candidate_synthetic,sv)}
            result=dict(native=native_view(native_paired,'candidate'),synthetic=grid.synthetic_report(candidate_synthetic,lambda f:score_lookup[id(f)]))
            eligible=qualifies(result,old_heuristic,v2_reference) and qualifies(result,candidate_heuristic,v2_reference)
            row=dict(id=record['id'],profile=profile_label,cache=str(cache),config=record['config'],training=record['training'],validation=result,
                selection_key=key(result),eligible=eligible,paired_system=dict(native=native_paired,synthetic=synthetic_paired),
                estimator_cache_path=record['estimator_cache_path'],estimator_cache_sha256=record['estimator_cache_sha256'])
            all_outcomes.append(row)
            print(json.dumps(dict(profile=profile_label,index=i,total=len(records),id=row['id'],eligible=eligible,key=row['selection_key'],native=result['native'],synthetic_counts=[result['synthetic'][str(k)]['recovered_in_top_k'] for k in [1,3]])),flush=True)
            write(output/'selection-progress.json',dict(final_fields_opened=False,outcomes=all_outcomes))
    eligible=[r for r in all_outcomes if r['eligible']]
    selected=max(eligible,key=lambda r:r['selection_key']) if eligible else None
    report=dict(schema_version=1,designation='eleven-parent primary validation DEVELOPMENT; no final access',generated_utc=datetime.now(timezone.utc).isoformat(),
        final_fields_opened=False,expected_configurations=132,completed_configurations=len(all_outcomes),profiles=profile_reports,outcomes=all_outcomes,selected=selected,
        eligibility='Both native common-attributable macro-parent K1/K3 and synthetic macro-cadence K1/K3 must reach deployed sigma1.2/v2, deployed sigma1.2 heuristic and candidate-profile heuristic; then nativeK1,K3,syntheticK1,K3,AP',
        eligibility_amendment='Explicit development amendment approved before expanded eleven-parent model scoring; final gate unchanged',
        native_cache_provenance=native_provenance,training_manifests=fit_manifests,resolved_fitting_source_locations=resolved_sources,
        baseline_model_sha256=V2_SHA,baseline_synthetic_cache=args.baseline_synthetic,baseline_synthetic_sha256=grid.sha(args.baseline_synthetic),
        source_snapshot='/tmp/spaceapps-v3-ranker/pre-selection-audit-source-snapshot/snapshot-manifest.json')
    if len(all_outcomes)!=132:raise ValueError('all132 configurations must be published before final selection')
    write(output/'system-validation-evaluation.json',report)
    print('VALIDATION_SELECTED '+json.dumps(None if selected is None else dict(id=selected['id'],profile=selected['profile'],config=selected['config'],key=selected['selection_key'])),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate-cache',action='append',required=True)
    p.add_argument('--baseline-native',nargs='+',required=True)
    p.add_argument('--baseline-synthetic',default='/tmp/spaceapps-v3-ranker/synthetic-validation.json.gz')
    p.add_argument('--candidate-native-dir',default='/tmp/spaceapps-v3-detection')
    p.add_argument('--baseline-model',default='backend/inference/models')
    p.add_argument('--output',required=True)
    run(p.parse_args())
