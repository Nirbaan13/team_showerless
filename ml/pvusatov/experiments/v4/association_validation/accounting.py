"""Fixed-budget paired research accounting; geometry is descriptive only."""
from collections import defaultdict
import math

ROLES=('legacy','learned_pair')


def policy_counts(labels,scores,kept,spans):
    n=len(labels)
    if (len(scores)!=n or len(spans)!=n or len(set(kept))!=len(kept)
            or any(type(i)is not int or not 0<=i<n for i in kept)
            or any(not math.isfinite(s)or not 0<=s<=1 for s in scores)):
        raise ValueError('invalid aligned policy prediction')
    order=sorted(kept,key=lambda i:-scores[i]);result={'candidate_rows':len(kept)}
    for name,ids in [('top1',order[:1]),('top3',order[:3]),('detected',order)]:
        recovered={labels[i]for i in ids if labels[i]>=0}
        resolved={labels[i]for i in ids if labels[i]>=0 and spans[i]is not None and spans[i]>=3.}
        result[name]=len(recovered);result['resolved_'+name]=len(resolved)
        result['unresolved_'+name]=len(recovered-resolved)
    return result


def common_attribution(control_labels,kept):
    flags={role:any(control_labels[i]>=0 for i in kept[role])for role in ROLES}
    return dict(eligible=not any(flags.values()),preexisting=flags)


def _summary(rows,samples,seed):
    import numpy as np
    groups=defaultdict(lambda:dict(truths=0,**{r:defaultdict(int)for r in ROLES}))
    totals={r:defaultdict(int)for r in ROLES};truths=0
    for row in rows:
        key=row.get('parent_id',row['seed']);g=groups[key];g['truths']+=row['truth_count'];truths+=row['truth_count']
        for role in ROLES:
            for k,v in row['policies'][role].items():totals[role][k]+=v;g[role][k]+=v
    positive=[groups[k]for k in sorted(groups,key=str)if groups[k]['truths']>0]
    report=dict(trials=len(rows),truth_count=truths,independent_groups=len(groups),groups_with_truth=len(positive),
                **{r:dict(totals[r])for r in ROLES})
    rng=np.random.default_rng(seed);draws={k:[]for k in (1,3)}
    for k in (1,3):
        rates={r:np.asarray([g[r]['top'+str(k)]/g['truths']for g in positive])for r in ROLES}
        for r in ROLES:
            report[r]['micro_recall'+str(k)]=totals[r]['top'+str(k)]/truths if truths else None
            report[r]['macro_recall'+str(k)]=float(rates[r].mean())if positive else None
        delta=rates['learned_pair']-rates['legacy']
        report['macro_delta_top'+str(k)]=float(delta.mean())if positive else None
        draws[k]=delta
    intervals={k:[]for k in (1,3)}
    if positive:
        for start in range(0,samples,100):
            ids=rng.integers(0,len(positive),size=(min(100,samples-start),len(positive)))
            for k in (1,3):intervals[k].extend(draws[k][ids].mean(axis=1))
    for k in (1,3):report['paired_group_ci95_top'+str(k)]=np.quantile(intervals[k],[.025,.975]).tolist()if positive else None
    return report


def paired(rows,*,samples=10000,seed=2026111502):
    if type(samples)is not int or samples<1:raise ValueError('positive bootstrap count required')
    errors=sum(row.get('error')is not None for row in rows)
    unknown=sum(type(row.get('truth_count'))is not int or row['truth_count']<0 for row in rows)
    complete=not errors and not unknown
    common=[row for row in rows if row.get('attribution_eligible')is True]
    return dict(complete=complete,planned_trials=len(rows),error_trials=errors,unknown_truth_trials=unknown,
        all_planned=_summary(rows,samples,seed)if complete else None,
        common_attributable=_summary(common,samples,seed)if complete else None,
        attribution_excluded_trials=len(rows)-len(common),bootstrap_samples=samples,bootstrap_seed=seed,
        uncertainty_unit='native parent or synthetic field; truth-positive macro groups; empty workload retained',
        geometry_policy='actual matched-epoch truth span >=3px descriptive; never filters primary truths')
