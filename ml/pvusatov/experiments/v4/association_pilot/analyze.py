"""Descriptive paired-field summaries; no policy selection/default changes."""
from pathlib import Path
import json
import numpy as np
from ml.pvusatov.experiments.v4.operating_points.study import atomic,digest
HERE=Path(__file__).resolve().parent
POLICIES=('legacy','learned_pair','near_duplicate')


def summarize(run):
    fields=[e['field']for e in run['entries']];result={}
    for kind in ('synthetic','native','native_control'):
        rows=[r for r in fields if r['kind']==kind];profiles={}
        for threshold in ('3.0','4.0'):
            available=[r for r in rows if threshold in r['profiles']];policies={}
            for name in POLICIES:
                ps=[r['profiles'][threshold]['policies'][name]for r in available]
                common=[r for r in available if r['profiles'][threshold]['policies'][name]['attribution_eligible']and r['profiles'][threshold]['policies']['legacy']['attribution_eligible']and not r['profiles'][threshold]['policies'][name]['error']and not r['profiles'][threshold]['policies']['legacy']['error']]
                policies[name]=dict(candidate_rows=sum(p['candidate_rows']for p in ps),publication100_exceeded=sum(p['candidate_rows']>100 for p in ps),policy_errors=sum(bool(p['error'])for p in ps),attribution_eligible=sum(p['attribution_eligible']for p in ps),common_attributable_vs_legacy=len(common),
                    models={m:{k:sum(p['models'][m][k]for p in ps)for k in ('detected','top1','top3')}for m in ('C13','C596')},
                    common_models={m:{k:sum(r['profiles'][threshold]['policies'][name]['models'][m][k]for r in common)for k in ('detected','top1','top3')}for m in ('C13','C596')},
                    common_legacy_models={m:{k:sum(r['profiles'][threshold]['policies']['legacy']['models'][m][k]for r in common)for k in ('detected','top1','top3')}for m in ('C13','C596')},
                    policy_cpu_seconds=sum(p['cpu_seconds']for p in ps),unknown_rows=sum(p['unknown_rows']or 0 for p in ps),
                    pair_operations=sum(p['accounting'].get('budgeted_pair_keys',0)for p in ps),index_operations=sum(p['accounting'].get('index_operations',0)for p in ps),exact_comparisons=sum(p['accounting'].get('exact_comparisons',0)for p in ps))
                if kind=='synthetic'and len(available)==100:
                    delta=np.asarray([r['profiles'][threshold]['policies'][name]['models']['C596']['top3']-r['profiles'][threshold]['policies']['legacy']['models']['C596']['top3']for r in available],float)
                    rng=np.random.default_rng(3806099);boots=delta[rng.integers(0,len(delta),(5000,len(delta)))].mean(axis=1)
                    policies[name]['paired_C596_top3_objects_per_field_delta']=dict(point=float(delta.mean()),percentile95=np.quantile(boots,[.025,.975]).tolist(),resamples=5000,unit='independent whole synthetic field',seed=3806099)
            profiles[threshold]=dict(completed_fields=len(available),task_errors=len(rows)-len(available),hypotheses=sum(r['profiles'][threshold]['hypotheses']for r in available),max_field_hypotheses=max([r['profiles'][threshold]['hypotheses']for r in available],default=0),full_pool_detected=sum(r['profiles'][threshold]['full_pool_detected']for r in available),
                peak_caps=sum(r['profiles'][threshold]['peak_cap_reached']for r in available),baseline_parity_fields=sum(r['profiles'][threshold]['baseline_exact_parity']for r in available),
                cpu_seconds={key:sum(r['profiles'][threshold][key]for r in available)for key in ('peak_cpu_seconds','actual_baseline_cpu_seconds','pool_generation_cpu_seconds','full_pool_feature_score_cpu_seconds')},policies=policies)
        result[kind]=dict(allplanned=len(rows),independent_parents=len({r['parent_id']for r in rows}),truth_count=sum(r['truth_count']or 0 for r in rows),unknown_truth_fields=sum(r['truth_count']is None for r in rows),profiles=profiles)
    # Split the synthetic no-mover workload using producer mode, never interpreted as native precision.
    modes={}
    for mode in sorted({r.get('mode','')for r in fields if r['kind']=='synthetic'}):
        rows=[r for r in fields if r['kind']=='synthetic'and r.get('mode')==mode]
        modes[mode]=dict(fields=len(rows),truths=sum(r['truth_count']or 0 for r in rows),profiles={t:{name:dict(rows=sum(r['profiles'].get(t,{}).get('policies',{}).get(name,{}).get('candidate_rows',0)for r in rows),nonempty_fields=sum(r['profiles'].get(t,{}).get('policies',{}).get(name,{}).get('candidate_rows',0)>0 for r in rows))for name in POLICIES}for t in ('3.0','4.0')})
    return dict(protocol_sha256=run['protocol_sha256'],run_sha256=digest(HERE/'results/run.json'),analysis_source_sha256=digest(__file__),wall_seconds=run['wall_seconds'],task_errors=[r.get('task_error')for r in fields if 'task_error'in r],max_worker_rss_mib=max(r['rss_mib']for r in fields),cohorts=result,synthetic_modes=modes,
        interpretation='Exploratory fixed-model DEV association retention and ranking; N=2 native parents descriptive. UNKNOWN controls are workload, not negative truth. Full-pool availability is not a reviewed detector metric. No policy/default/model selected.')

if __name__=='__main__':
    run=json.loads((HERE/'results/run.json').read_text());out=summarize(run);atomic(HERE/'results/summary.json',out)
    for kind,c in out['cohorts'].items():
        print(kind,c['allplanned'],'truths',c['truth_count'])
        for t,p in c['profiles'].items():
            print(t,'pool',p['hypotheses'],'oracle',p['full_pool_detected'],'CPU',p['cpu_seconds'])
            for name,q in p['policies'].items():print(name,'rows',q['candidate_rows'],'errors',q['policy_errors'],'C13',q['models']['C13'],'C596',q['models']['C596'])
