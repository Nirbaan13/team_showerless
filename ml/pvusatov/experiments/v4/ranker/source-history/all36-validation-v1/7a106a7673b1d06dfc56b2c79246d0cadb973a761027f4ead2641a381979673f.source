"""Lean, checked development cache loading and fixed-budget recovery accounting."""
from pathlib import Path
import gzip,hashlib,json,re,sys
import numpy as np
BASE=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(BASE/'experiments/v4/detection'))
from features import FEATURE_NAMES,FEATURE_VERSION,FEATURE_CONTRACT_SHA256


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_cache(path,partition):
    path=Path(path)
    if re.search(r'(^|[/_.-])(final|quarantine)([/_.-]|$)',str(path),re.I):raise ValueError('FINAL or quarantine path forbidden before opening')
    if partition not in {'train','validation'}:raise ValueError('only training or development validation is allowed')
    with gzip.open(path,'rt') as f:payload=json.load(f)
    if payload.get('partition')!=partition:raise ValueError('cache partition mismatch')
    claims=[payload['evaluation_complete']] if 'evaluation_complete' in payload else []
    if 'evaluation_complete' in payload.get('summary',{}):claims.append(payload['summary']['evaluation_complete'])
    if not claims or any(value is not True for value in claims):raise ValueError('incomplete or conflicting completion claims')
    if payload.get('baseline_model_sha256')!='c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204':raise ValueError('baseline C13 model binding mismatch')
    if payload.get('feature_names')!=list(FEATURE_NAMES)or payload.get('feature_version')!=FEATURE_VERSION or payload.get('feature_contract_sha256')!=FEATURE_CONTRACT_SHA256:raise ValueError('feature order/version/contract mismatch')
    if payload['detector_settings']['psf_sigma']!=.8 or payload['detector_settings']['min_speed']!=.5:raise ValueError('mixed candidate profile forbidden')
    source=sha(BASE/'experiments/v4/detection/features.py')
    recorded=payload.get('feature_source_sha256')or next((v for k,v in payload.get('source_sha256',{}).items() if k.endswith('/features.py')),None)
    if recorded!=source:raise ValueError('feature source changed or unbound')
    fields=[]
    retained=['seed','mode','matches','truth_count','baseline','scores_c13','scores','metadata','times_hours','parent_id','partition','trajectory_id','brightness','speed_px_hour','attribution_eligible','usable_center_epochs','peak_cap_reached','preexisting_control_match','candidate_ids','latent_sha256','truth_kind','stationary_sky_truth','matched_geometry','expected_xy','center_usable_flags']
    for original in payload['fields']:
        if original.get('error'):raise ValueError('failed field in complete cache')
        rich=np.asarray(original['features_v4'],np.float32).reshape(-1,30)
        six=np.asarray(original['features'],np.float32).reshape(-1,6)
        n=len(rich)
        if n!=len(six)or not np.array_equal(six,rich[:,:6])or not np.isfinite(rich).all()or len(original['matches'])!=n:raise ValueError('candidate/feature prefix mismatch')
        if len(original['candidate_ids'])!=n or len(set(original['candidate_ids']))!=n:raise ValueError('candidate identity mismatch')
        field={k:original[k] for k in retained if k in original};field['features_v4']=rich;field['features']=rich[:,:6]
        if 'candidate_epochs' in original:
            field['known_candidate_epochs']={i:original['candidate_epochs'][i]for i,m in enumerate(original['matches'])if m>=0}
        field['matches']=np.asarray(original['matches'],np.int32)
        field['baseline']=np.asarray(original['baseline'],np.float32)
        score=np.asarray(field.get('scores_c13',field.get('scores',[])),np.float32)
        if score.shape!=(n,)or not np.isfinite(score).all()or np.any((score<0)|(score>1)):raise ValueError('C13 score binding or shape invalid')
        field['scores_c13']=score
        field.pop('scores',None)
        fields.append(field)
    header={k:v for k,v in payload.items() if k!='fields'}
    return header,fields


def field_counts(field,score,k):
    matches=np.asarray(field['matches'],int);order=np.argsort(-np.asarray(score),kind='stable')
    recovered=len(set(int(i) for i in matches[order[:k]] if i>=0));detected=len(set(int(i)for i in matches if i>=0))
    return dict(truth=int(field['truth_count']),recovered=recovered,detected=detected,candidates=len(matches))


def recovery_report(fields,scores,synthetic=False):
    if len(fields)!=len(scores):raise ValueError('field/score count mismatch')
    result={}
    for cohort in ['all_planned','common_attributable']:
        indices=[i for i,f in enumerate(fields) if cohort=='all_planned' or f.get('attribution_eligible',True)]
        report=dict(planned_fields=len(fields),cohort_fields=len(indices),candidate_rows=sum(len(fields[i]['matches'])for i in indices),unknown_real_controls_unlabeled=True)
        if not synthetic:report['independent_parents']=len({fields[i]['parent_id']for i in indices})
        for k in [1,3]:
            rows=[(fields[i],field_counts(fields[i],scores[i],k))for i in indices]
            report['top'+str(k)]=sum(r['recovered']for _,r in rows)
            report['truth_count']=sum(r['truth']for _,r in rows)
            report['detected']=sum(r['detected']for _,r in rows)
            report['micro_recall'+str(k)]=report['top'+str(k)]/report['truth_count'] if report['truth_count'] else None
            if synthetic:
                report['macro_field_recall'+str(k)]=float(np.mean([r['recovered']/r['truth']for _,r in rows if r['truth']])) if any(r['truth']for _,r in rows)else None
                cadence=[]
                for c in range(4):
                    subset=[r for f,r in rows if f['metadata']['cadence_family']==c];den=sum(r['truth']for r in subset)
                    if den:cadence.append(sum(r['recovered']for r in subset)/den)
                report['macro_cadence_recall'+str(k)]=float(np.mean(cadence)) if cadence else None
            else:
                parents={f['parent_id']for f,_ in rows};by_parent={}
                for parent in parents:
                    subset=[r for f,r in rows if f['parent_id']==parent];den=sum(r['truth']for r in subset)
                    by_parent[parent]=dict(truth_count=den,recovered=sum(r['recovered']for r in subset),recall=sum(r['recovered']for r in subset)/den if den else None)
                report['macro_parent_recall'+str(k)]=float(np.mean([r['recall']for r in by_parent.values()if r['recall']is not None])) if by_parent else None
                report['per_parent_K'+str(k)]=by_parent
        result[cohort]=report
    return result


def native_moving_validation(fields,expected_parents=8,expected_trials=270):
    parents={f['parent_id']for f in fields}
    if len(parents)!=expected_parents:raise ValueError('all planned native validation parents required')
    allowed={'moving_injection','stationary_injected_artifact'}
    if any(f.get('truth_kind')not in allowed for f in fields):raise ValueError('unknown native truth provenance')
    moving=[f for f in fields if f['truth_kind']=='moving_injection']
    if any(sum(f['parent_id']==parent for f in moving)!=expected_trials for parent in parents):raise ValueError('all planned moving validation derivatives required')
    if any(f['truth_count']!=1 for f in moving):raise ValueError('moving validation has wrong truth denominator')
    if any(f['truth_count']!=0 for f in fields if f['truth_kind']=='stationary_injected_artifact'):raise ValueError('stationary truth must not become moving positives')
    return moving
