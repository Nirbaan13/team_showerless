"""All-planned and common-attributable summaries of the predeclared slow probe."""
import argparse,gzip,hashlib,json
from pathlib import Path
import numpy as np

def summary(fields):
    complete=[f for f in fields if all('error'not in f['methods'][k]for k in ['1.2','0.8'])]
    eligible=[f for f in complete if all(not f['methods'][k]['preexisting_control_match']for k in ['1.2','0.8'])]
    report=dict(planned_trials=len(fields),both_searches_complete=len(complete),coverage_ge3=sum(f['usable_center_epochs']>=3 for f in fields),common_attribution_eligible=len(eligible),excluded_preexisting=len(complete)-len(eligible),methods={})
    for key in ['1.2','0.8']:
        methods=[f['methods'][key]for f in complete];attributable=[f['methods'][key]for f in eligible];att=[v for f in fields for v in f['isolated_source_filtered_attenuation'][key]if v is not None]
        report['methods'][key]=dict(raw={k:sum(m[k]for m in methods)for k in ['detected','at_1','at_3','candidates']},common_attributable={k:sum(m[k]for m in attributable)for k in ['detected','at_1','at_3','candidates']},preexisting_control_match=sum(m['preexisting_control_match']for m in methods),wall_p50=float(np.median([m['wall_seconds']for m in methods]))if methods else None,wall_p95=float(np.quantile([m['wall_seconds']for m in methods],.95))if methods else None,max_rss_mib=max((m['rss_mib']for m in methods),default=None),isolated_response_attenuation_median=float(np.median(att))if att else None)
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,action='append');p.add_argument('--output',required=True);a=p.parse_args();reports=[]
    for path in a.report:
        with gzip.open(path,'rt')as s:reports.append(json.load(s))
    fields=[f for r in reports for f in r['fields']]
    report=dict(designation='slow-profile engineering diagnostic, no confirmed motion or distant-body completeness claim',independent_parent_fields=len(reports),derivatives_correlated=True,all=summary(fields),by_speed={str(speed):summary([f for f in fields if f['speed_px_hour']==speed])for speed in [.01,.03,.1,.3,1.]},by_parent={r['parent_id']:summary(r['fields'])for r in reports},physical_time_spans_hours={r['parent_id']:r['times_hours'][-1]-r['times_hours'][0]for r in reports},control_candidates={r['parent_id']:r['control_candidates']for r in reports},source_reports_sha256={path:hashlib.sha256(Path(path).read_bytes()).hexdigest()for path in a.report})
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(report['all'],indent=2))
if __name__=='__main__':main()
