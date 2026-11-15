"""Complete fixed-matrix DEVELOPMENT analysis; never reads final data or refits."""
from pathlib import Path
import gzip
import json
import numpy as np
from .study import digest, atomic, summarize

HERE = Path(__file__).resolve().parent


def paired_interval(values, *, resamples=5000):
    values = np.asarray(values,float)
    if values.ndim!=1 or len(values)<2 or not np.isfinite(values).all():raise ValueError('complete finite whole-field differences required')
    rng = np.random.default_rng(3805099)
    samples = values[rng.integers(0,len(values),(resamples,len(values)))].mean(axis=1)
    return dict(delta_known_objects_per_field=float(values.mean()),interval95=np.quantile(samples,[.025,.975]).tolist(),
        wins=int((values>0).sum()),losses=int((values<0).sum()),ties=int((values==0).sum()),independent_fields=len(values),resamples=resamples,
        interpretation='paired whole synthetic-field bootstrap, exploratory interval; no threshold/model selection')


def resolved_metrics(field, profile, model):
    labels = profile['matches']; scores = profile['scores'][model]
    order = np.argsort(-np.asarray(scores),kind='stable') if scores is not None else []
    spans = []
    for i,label in enumerate(labels):
        if label<0:spans.append(None);continue
        path = np.asarray(field['expected_xy'][label])[profile['candidate_epochs'][i]]
        spans.append(float(np.max(np.linalg.norm(path[:,None]-path[None,:],axis=2))))
    count = lambda ids:len({labels[i] for i in ids if labels[i]>=0 and spans[i]>=3.})
    return dict(detected=count(range(len(labels))),top1=count(order[:1]),top3=count(order[:3]))


def main():
    source = HERE/'results/summary.json'; report = json.loads(source.read_text()); protocol = HERE/'protocol.json'
    if digest(protocol)!=report['protocol_sha256']:raise ValueError('protocol binding differs')
    if any(digest(p)!=h for p,h in report['source_sha256'].items()):raise ValueError('fixed source closure changed')
    if summarize(report['fields'])!=report['summary']:raise ValueError('summary/field counts differ')
    fields = []
    for entry in report['fields']:
        if digest(entry['path'])!=entry['sha256']:raise ValueError('raw field cache differs')
        with gzip.open(entry['path'],'rt') as stream:field = json.load(stream)
        if field['profiles'].keys()!=dict.fromkeys(['3.0','4.0','5.0','6.0']).keys():raise ValueError('missing threshold')
        for profile in field['profiles'].values():
            if profile['errors']:raise ValueError('study has errors; retain raw evidence and report failure')
            n = profile['candidate_rows']
            if n!=len(profile['matches']) or n!=len(profile['candidate_epochs']) or n!=len(profile['candidate_ids']):raise ValueError('candidate identities differ')
            if np.asarray(profile['features_v4']).reshape(-1,30).shape!=(n,30):raise ValueError('full30 rows differ')
            np.testing.assert_array_equal(np.asarray(profile['features_v4']).reshape(-1,30)[:,:6],np.asarray(profile['features']).reshape(-1,6))
            for model in ('C13','C596'):
                if len(profile['scores'][model])!=n:raise ValueError('score vector differs')
        fields.append(field)
    synthetic = [f for f in fields if f['kind']=='synthetic']; native = [f for f in fields if f['kind']=='native'];controls = [f for f in fields if f['kind']=='native_control']
    if {f['seed']for f in synthetic}!=set(range(3805000,3805100)) or len(synthetic)!=100:raise ValueError('all100 independent synthetic fields required')
    expected = {(p,s,d,b)for p in ('v4-train01','v4-train03')for s in (.1,1.,10.)for d in range(3)for b in (3.,12.,48.)}
    actual = [(f['parent_id'],f['speed_px_hour'],f['direction_id'],f['brightness'])for f in native]
    if len(actual)!=54 or set(actual)!=expected or len(controls)!=2:raise ValueError('all54 native derivatives/two controls required')
    intervals = {}; empty = {}; parents = {}; resolved = {}; losses = []
    for threshold in ('3.0','4.0','5.0','6.0'):
        intervals[threshold] = {model:{metric:paired_interval([f['profiles'][threshold]['models'][model][metric]-f['profiles']['4.0']['models'][model][metric]for f in synthetic])for metric in ('detected','top1','top3')}for model in ('C13','C596')}
        empty[threshold] = {mode:dict(independent_fields=sum(f['mode']==mode for f in synthetic),
            proposal_rows=sum(f['profiles'][threshold]['candidate_rows']for f in synthetic if f['mode']==mode),
            fields_with_proposals=sum(f['profiles'][threshold]['candidate_rows']>0 for f in synthetic if f['mode']==mode),
            review_slots_K3=sum(min(3,f['profiles'][threshold]['candidate_rows'])for f in synthetic if f['mode']==mode))for mode in ('noise_only','artifacts_only')}
        resolved[threshold] = {kind:{model:{metric:sum(resolved_metrics(f,f['profiles'][threshold],model)[metric]for f in group)for metric in ('detected','top1','top3')}for model in ('C13','C596')}for kind,group in [('synthetic',synthetic),('native',native)]}
    for parent in ('v4-train01','v4-train03'):
        selected = [e for e in report['fields']if e['field']['parent_id']==parent]
        parents[parent] = summarize(selected)
    for f in native:
        a = f['profiles']['3.0']['models']['C596']['detected'];b = f['profiles']['4.0']['models']['C596']['detected']
        if a!=b:losses.append(dict(parent_id=f['parent_id'],seed=f['seed'],speed=f['speed_px_hour'],direction=f['direction_id'],brightness=f['brightness'],detected_at3=a,detected_at4=b,
            resolved_detected_at3=resolved_metrics(f,f['profiles']['3.0'],'C596')['detected'],resolved_detected_at4=resolved_metrics(f,f['profiles']['4.0'],'C596')['detected']))
    publication = {kind:{t:sum(f['profiles'][t]['candidate_rows']>100 for f in group)for t in ('3.0','4.0','5.0','6.0')}for kind,group in [('synthetic',synthetic),('native',native),('native_control',controls)]}
    output = dict(designation='DEVELOPMENT threshold tradeoffs, fixedC596/C13, no default/gate/model selection',study_sha256=digest(source),protocol_sha256=digest(protocol),analysis_source_sha256=digest(Path(__file__)),
        paired_synthetic_intervals_vs4=intervals,known_empty_synthetic_workload=empty,native_parent_descriptive=parents,
        matched_epoch_truthspan_ge3_diagnostic=resolved,raw_pools_over_publication100=publication,native_nonmonotonic_cases=losses,
        resources=dict(study_wall_seconds=report['elapsed_seconds'],peak_worker_rss_mib=max(f['rss_mib']for f in fields)),
        limitations=['nativeN2 descriptive,no populationCI','unmatched real rows UNKNOWN,not negative labels','no calibrated score/probability comparison across thresholds','raw residual pools,not fullBLOOM publication policy','3px is engineering injection-path-span diagnostic,not fundamental limit/confirmedmotion','allplanned fields retained,bootstrap whole syntheticfields not candidate rows'])
    path = HERE/'results/analysis.json'
    if path.exists():raise ValueError('immutable analysis exists')
    atomic(path,output)
    print(json.dumps(dict(path=str(path),sha256=digest(path),resolved=resolved,nonmonotonic=losses,empty=empty,publication=publication,resources=output['resources'])))


if __name__=='__main__':main()
