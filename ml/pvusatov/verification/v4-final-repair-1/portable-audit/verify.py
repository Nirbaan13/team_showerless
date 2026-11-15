"""Portable independent score-cache accounting; no external scientific inputs."""
from pathlib import Path
from collections import defaultdict, Counter
import argparse
import gzip
import hashlib
import json
import math
import os
import sys
import numpy as np

ANCHOR='1225e2de97c38381818d9ccb3676c1d132701b02b8bc19dc09e0d1785c3e38e4'
REPORT_SHA='15cabb840cb8af95771f3534f2b5adfb18caaff5f0e8b57ed678f858525f7e56'
MODEL_SHA='c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
META_SHA='472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13'
PAYLOAD_SHA='d2f2766935acc92c169de02b0959882186560b6aacdbf34f3dcddd0965f9e50c'
ROLES={'baseline':'scores_c13','candidate':'scores_v4'}
BUDGETS=('top1','top3','detected')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def read(path):
    return json.loads(Path(path).read_text())


def check(condition,message):
    if not condition:
        raise ValueError(message)


def read_bundle(folder):
    folder=Path(folder).resolve()
    manifest=read(folder/'manifest.json')
    check(manifest['canonical_report_sha256']==REPORT_SHA and manifest['freeze_sha256']==ANCHOR,'wrong canonical anchors')
    check(manifest['candidate_model_sha256']==MODEL_SHA and manifest['candidate_metadata_sha256']==META_SHA,'wrong frozen model references')
    for name,expected in manifest['files'].items():
        path=(folder/name).resolve()
        check(path.is_relative_to(folder),'capsule path escapes bundle')
        check(path.is_file() and sha(path)==expected['sha256'] and path.stat().st_size==expected['bytes'],'capsule file hash mismatch: '+name)
    check(sha(folder/'canonical-report.json')==REPORT_SHA,'canonical report digest differs')
    check(sha(folder/'freeze.json')==ANCHOR,'freeze digest differs')
    # The manifest may be resealed locally. Only these reviewed payload bytes
    # are authorized, independently of that mutable inventory and row hashes.
    check(sha(folder/'scored-fields.json.gz')==PAYLOAD_SHA,'scored payload anchor differs')
    with gzip.open(folder/'scored-fields.json.gz','rt')as stream:
        payload=json.load(stream)
    check(payload['schema_version']==1,'wrong projection schema')
    native=payload['native'];synthetic=payload['synthetic']
    check(len(native)==12 and len(synthetic)==1,'missing or extra parent cache')
    check(sum(len(c['fields'])for c in native)==3240,'missing native trial')
    check(len(synthetic[0]['fields'])==3000,'missing synthetic trial')
    check({c['parent_id']for c in native}=={f'v4-final{i:02d}'for i in range(1,13)},'native parent identities differ')
    check({f['seed']for f in synthetic[0]['fields']}==set(range(3900000,3903000)),'synthetic seed plan differs')
    expected={(s,d,b)for s in [.01,.03,.1,.3,1.,4.,10.,25.,50.]for d in range(6)for b in [3.,6.,12.,24.,48.]}
    for cache in native:
        check(len(cache['fields'])==270,'missing native matrix derivative')
        check({(f['speed_px_hour'],f['direction_id'],f['brightness'])for f in cache['fields']}==expected,'native matrix differs')
    for domain in [native,synthetic]:
        for cache in domain:
            check(cache['source_cache_sha256']in manifest['original_cache_sha256'],'unknown original cache binding')
            for field in cache['fields']:
                value={k:v for k,v in field.items()if k!='projection_sha256'}
                check(hashlib.sha256(canonical(value)).hexdigest()==field['projection_sha256'],'field projection digest differs')
                check(field['source_cache_sha256']==cache['source_cache_sha256'],'field source-cache binding differs')
                check(set(field['feature_matrix_sha256'])=={'features','features_v4'},'missing feature-matrix provenance')
    return manifest,payload,read(folder/'canonical-report.json')

def span(points):
    points = np.asarray(points, float)
    return float(np.max(np.linalg.norm(points[:, None] - points[None, :], axis=2))) if len(points) else 0.

def ordered(scores):
    assert all(type(s) in (int, float) and math.isfinite(s) and 0 <= s <= 1 for s in scores)
    # Python sorting is stable, independent of the report's NumPy sorting call.
    return sorted(range(len(scores)), key=lambda i: -scores[i])

def unique(labels, indices):
    return len({labels[i] for i in indices if labels[i] >= 0})

def statistics(rows):
    group = defaultdict(lambda: {'truths': 0, 'baseline': Counter(), 'candidate': Counter()})
    totals = {role: Counter() for role in ROLES}
    for row in rows:
        item = group[row['group']]; item['truths'] += row['truths']
        for role in ROLES:
            item[role].update({k: row[role][k] for k in ('top1', 'top3')})
            totals[role].update(row[role])
    positive_groups = [group[k] for k in sorted(group) if group[k]['truths'] > 0]
    truth = sum(r['truths'] for r in rows)
    result = dict(trials=len(rows), truth_count=truth, independent_groups=len(group),
                  groups_with_truth=len(positive_groups), **{role: dict(totals[role]) for role in ROLES})
    deltas = {}
    for k in (1, 3):
        rates = {}
        for role in ROLES:
            rates[role] = np.asarray([r[role]['top'+str(k)] / r['truths'] for r in positive_groups])
            result[role]['micro_recall'+str(k)] = totals[role]['top'+str(k)] / truth
            result[role]['macro_recall'+str(k)] = float(rates[role].mean())
        deltas[k] = rates['candidate'] - rates['baseline']
        result['macro_delta_top'+str(k)] = float(deltas[k].mean())
    # Same prospective seed/unit/count, independently implemented in small batches.
    rng = np.random.default_rng(20261115)
    draws = {k: [] for k in (1, 3)}
    for start in range(0, 10000, 100):
        indices = rng.integers(0, len(positive_groups), size=(min(100, 10000-start), len(positive_groups)))
        for k in (1, 3):
            draws[k].extend(deltas[k][indices].mean(axis=1).tolist())
    for k in (1, 3):
        result['paired_parent_ci95_top'+str(k)] = np.quantile(draws[k], [.025, .975]).tolist()
    return result

def assert_metrics(actual, expected):
    for key, value in actual.items():
        if isinstance(value, dict):
            assert_metrics(value, expected[key])
        elif isinstance(value, list):
            assert np.allclose(value, expected[key], rtol=0, atol=2e-15), (key, value, expected[key])
        elif isinstance(value, float):
            assert math.isclose(value, expected[key], rel_tol=0, abs_tol=2e-15), (key, value, expected[key])
        else:
            assert value == expected[key], (key, value, expected[key])


def verify(folder):
    manifest,payload,report=read_bundle(folder)
    output={};control_count=0;diagnostics={};caps={};strata_output={}
    for domain in ['native','synthetic']:
        rows=[];seen=set();geometry=Counter();resolved_counts={r:Counter()for r in ROLES};strata={};cap_count=0
        for cache in payload[domain]:
            check(cache['freeze_sha256']==ANCHOR,'cache freeze differs')
            check(cache['summary']['evaluation_complete']is True and cache['summary']['error_trials']==0,'cache incomplete')
            check(cache['models']['candidate']['sha256']==MODEL_SHA,'wrong candidate reference')
            if domain=='native':
                control=cache['control'];check(control['error']is None,'failed control')
                check(all(m==-2 for m in control['matches']),'UNKNOWN control relabeled')
                check(len(control['matches'])==len(control['candidate_ids'])==len(control['scores_c13'])==len(control['scores_v4']),'unaligned control')
                control_count+=len(control['matches'])
            for f in cache['fields']:
                identity=(f['parent_id'],f['seed'],f['trajectory_id'],f['brightness'])if domain=='native'else(f['seed'],)
                check(identity not in seen,'duplicate field identity');seen.add(identity)
                check(f['error']is None,'failed field')
                labels=f['matches'];truths=[f['expected_xy']]if domain=='native'else f['expected_xy']
                check(len(truths)==f['truth_count'],'truth denominator differs')
                check(len(labels)==len(f['candidate_ids'])==len(set(f['candidate_ids']))==len(f['candidate_epochs'])==len(f['candidate_positions_xy']),'candidate identity alignment differs')
                resolved=set()
                for i,(epochs,xy)in enumerate(zip(f['candidate_epochs'],f['candidate_positions_xy'])):
                    check(len(epochs)>=3 and len(set(epochs))==len(epochs),'candidate epochs differ')
                    distance=[np.linalg.norm(np.asarray(xy)-np.asarray(t)[epochs],axis=1)for t in truths]
                    matching=[j for j,v in enumerate(distance)if np.all(v<=1.5)]
                    label=min(matching,key=lambda j:float(distance[j].mean()))if matching else(-2 if domain=='native'else-1)
                    check(label==labels[i],'cached spatial truth identity differs')
                    if label>=0 and span(np.asarray(truths[label])[epochs])>=3:resolved.add(i)
                check(resolved=={r['candidate_index']for r in f['matched_geometry']if r['true_displacement_px']>=3},'matched-span geometry differs')
                capabilities=[f['geometric_capability']]if domain=='native'else f['geometric_capabilities']
                for t,c in zip(truths,capabilities):
                    flags=f['center_usable_flags']if domain=='native'else c['center_usable_flags']
                    n=sum(flags);s=span(np.asarray(t)[flags])
                    check(n==c['finite_center_epochs']and math.isclose(s,c['covered_truth_span_px'],abs_tol=1e-12),'coverage geometry differs')
                    geometry['planned_truths']+=1;geometry['finite_centers_ge3']+=int(n>=3)
                    geometry['resolved_covered_truth_span_ge3px']+=int(s>=3);geometry['geometrically_testable']+=int(n>=3 and s>=3)
                row=dict(group=f['parent_id']if domain=='native'else f['seed'],truths=len(truths),eligible=f['attribution_eligible'],finite=f.get('usable_center_epochs',3)>=3)
                check(type(row['eligible'])is bool and row['eligible']!=f['preexisting_control_match'],'attribution flags differ')
                for role,key in ROLES.items():
                    scores=f[key];check(len(scores)==len(labels),'score vector alignment differs')
                    order=ordered(scores);indices={'top1':order[:1],'top3':order[:3],'detected':order}
                    row[role]={b:unique(labels,idx)for b,idx in indices.items()};row[role]['candidate_rows']=len(labels)
                    for b,idx in indices.items():resolved_counts[role][b]+=unique(labels,[i for i in idx if i in resolved])
                rows.append(row);cap_count+=int(f['peak_cap_reached'])
                keys=[('parent',f['parent_id']),('speed_px_hour',str(f['speed_px_hour'])),('brightness',str(f['brightness']))]if domain=='native'else[('mode',f['mode'])]
                for key in keys:
                    item=strata.setdefault(key,dict(trials=0,truths=0,baseline=Counter(),candidate=Counter()));item['trials']+=1;item['truths']+=len(truths)
                    for role in ROLES:item[role].update({b:row[role][b]for b in BUDGETS})
        output[domain]={}
        for cohort,selected in [('all_planned',rows),('common_attributable',[r for r in rows if r['eligible']]),('common_finite_center_ge3',[r for r in rows if r['eligible']and r['finite']])]:
            result=statistics(selected);assert_metrics(result,report['reports'][domain][cohort]);output[domain][cohort]=result
        check(dict(geometry)==report['diagnostics'][domain]['geometry'],'geometry totals differ')
        check({r:dict(v)for r,v in resolved_counts.items()}==report['diagnostics'][domain]['actual_matched_epoch_truth_span_ge3px_recoveries'],'resolved recovery totals differ')
        for expected in report['diagnostics'][domain]['strata']:
            actual=strata[expected['kind'],expected['value']]
            check(actual['trials']==expected['planned_trials']and actual['truths']==expected['truth_count'],'stratum denominator differs')
            for role in ROLES:check(dict(actual[role])==expected[role],'stratum recovery differs')
        strata_output[domain]=len(strata);diagnostics[domain]=dict(geometry);caps[domain]=cap_count
    check(control_count==824,'control workload differs');check(caps=={'native':0,'synthetic':0},'search cap differs')
    return dict(status='PASS',fields=6240,native_fields=3240,synthetic_fields=3000,
        reports=output,geometry=diagnostics,strata_checked=strata_output,unknown_control_rows=control_count,
        peak_cap_trials=caps,canonical_report_sha256=REPORT_SHA,freeze_sha256=ANCHOR,
        no_scoring_or_model_or_pixel_reads=True,
        limitation='Feature matrices are omitted and hash-bound; this is score/geometry accounting, not recomputation of features or model outputs.')


def deny_external_inputs(folder):
    root=Path(folder).resolve();denied=[]
    # Interpreter/numeric-library initialization is complete before installing the hook.
    np.random.default_rng(0);np.quantile(np.arange(3),[.25,.75])
    def hook(event,args):
        if event in ('open','os.listdir','os.scandir')and args:
            path=args[0]
            if isinstance(path,(str,bytes,os.PathLike)):
                resolved=Path(os.fsdecode(path)).resolve()
                if not resolved.is_relative_to(root):
                    denied.append(dict(event=event,path=str(resolved)))
                    raise PermissionError('external input forbidden by portable audit')
    sys.addaudithook(hook)
    return denied


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--deny-external-inputs',action='store_true')
    parser.add_argument('--probe-denial',action='store_true')
    args=parser.parse_args();denied=deny_external_inputs(args.bundle)if args.deny_external_inputs else None
    if args.probe_denial:
        check(denied is not None,'denial probe requires input guard')
        try:Path('/etc/passwd').read_bytes()
        except PermissionError:pass
        else:raise ValueError('external input guard did not reject the probe')
    result=verify(args.bundle)
    result['external_input_guard']=dict(active=denied is not None,expected_probe_rejections=len(denied or []),
        unexpected_external_attempts=0,scope='Python audit-hook file opens/listing after interpreter and NumPy initialization')
    print(json.dumps(result,sort_keys=True,allow_nan=False))


if __name__=='__main__':main()
