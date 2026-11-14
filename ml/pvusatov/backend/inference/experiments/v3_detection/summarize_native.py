"""Summarize correlated native development derivatives without false-positive labels."""
from pathlib import Path
import argparse,gzip,json
import numpy as np
BASELINE='sigma1.2_snr4.0'

def aggregate(reports):
    all_fields=[f for r in reports for f in r['fields']];configs=list(all_fields[0]['methods']);out={}
    for name in configs:
        eligible=[f for f in all_fields if not f['methods'][name].get('preexisting_control_match',True) and not f['methods'][BASELINE].get('preexisting_control_match',True)]
        comparison={}
        for label,key in [('baseline',BASELINE),('proposed',name)]:
            methods=[f['methods'][key]for f in eligible];all_methods=[f['methods'][key]for f in all_fields]
            comparison[label]=dict(attribution_eligible=len(eligible),**{k:sum(m[k]for m in methods)for k in ['detected','at_1','at_3','candidates']},candidate_rows_all_trials=sum(m['candidates']for m in all_methods),peak_cap_trials=sum(m['peak_cap_reached']for m in all_methods),wall_p50=float(np.median([m['wall_seconds']for m in all_methods])),wall_p95=float(np.quantile([m['wall_seconds']for m in all_methods],.95)),max_rss_mib=max(m['rss_mib']for m in all_methods))
        out[name]=dict(common_attribution_eligible=len(eligible),excluded_preexisting=len(all_fields)-len(eligible),**comparison)
    return dict(independent_parent_fields=len(reports),derived_injection_trials=len(all_fields),geometric_center_coverage_ge3=sum(f['usable_center_epochs']>=3 for f in all_fields),raw_all_planned={name:{**{k:sum(f['methods'][name].get(k,0)for f in all_fields)for k in ['detected','at_1','at_3','candidates']},'preexisting_control_match_trials':sum(f['methods'][name].get('preexisting_control_match',False)for f in all_fields),'errors':sum('error'in f['methods'][name]for f in all_fields)}for name in configs},all_derivatives_correlated=True,unmatched_real_candidates='unknown, never false positives',comparisons=out)

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',action='append',required=True);p.add_argument('--output',required=True);a=p.parse_args();reports=[]
    for path in a.report:
        with gzip.open(path,'rt')as s:reports.append(json.load(s))
    report=dict(designation='v3 native development detector ablation; no final inference',all=aggregate(reports),by_partition={part:aggregate([r for r in reports if r['partition']==part])for part in ['train','validation']if any(r['partition']==part for r in reports)},by_parent={r['parent_id']:aggregate([r])for r in reports})
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(report['all'],indent=2))
if __name__=='__main__':main()
