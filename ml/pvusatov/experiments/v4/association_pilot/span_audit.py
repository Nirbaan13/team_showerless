"""Offline actual matched-epoch 3px diagnostic, never a detectability ceiling."""
from pathlib import Path
import gzip,json
import numpy as np
from ml.pvusatov.experiments.v4.operating_points.study import atomic,digest
HERE=Path(__file__).resolve().parent

def main():
    run=json.loads((HERE/'results/run.json').read_text());cohorts={};field_rows=[]
    for entry in run['entries']:
        if digest(entry['path'])!=entry['sha256']:raise ValueError('derivedcache changed')
        with gzip.open(entry['path'],'rt')as stream:r=json.load(stream)
        if 'task_error'in r:continue
        row=dict(case_id=r['case_id'],kind=r['kind'],parent_id=r['parent_id'],profiles={})
        for t,p in r['profiles'].items():
            spans={}
            for i,label in enumerate(p['matches']):
                if label<0:continue
                xy=np.asarray(r['expected_xy'][label])[p['candidate_epochs'][i]];spans[i]=float(np.max(np.linalg.norm(xy[:,None]-xy[None,:],axis=2)))
            ps={}
            for name,q in p['policies'].items():
                ids=q['indices'];order=np.argsort(-np.asarray(p['scores']['C596'])[ids],kind='stable')[:3]
                resolved=lambda indexes:len({p['matches'][i]for i in indexes if i in spans and spans[i]>=3})
                ps[name]=dict(resolved_detected=resolved(ids),resolved_top3=resolved([ids[int(i)]for i in order]),attribution_eligible=q['attribution_eligible'])
                key=f'{r["kind"]}/{t}/{name}';c=cohorts.setdefault(key,dict(allplanned=0,resolved_detected=0,resolved_top3=0,full_pool_resolved_available=0))
                c['allplanned']+=1;c['resolved_detected']+=ps[name]['resolved_detected'];c['resolved_top3']+=ps[name]['resolved_top3'];c['full_pool_resolved_available']+=resolved(range(p['hypotheses']))
            row['profiles'][t]=ps
        field_rows.append(row)
    atomic(HERE/'results/matched-span-audit.json',dict(source_sha256=digest(__file__),run_sha256=digest(HERE/'results/run.json'),definition='max pairwise truth displacement over ACTUAL matched epochs >=3 pixels; diagnostic only, not fundamental detection condition or confirmed motion',cohorts=cohorts,fields=field_rows))
    for k,v in cohorts.items():print(k,v)
if __name__=='__main__':main()
