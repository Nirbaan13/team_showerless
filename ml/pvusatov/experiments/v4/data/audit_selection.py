"""Offline replay of V4 prospective selection from published exact SIA metadata."""
from datetime import datetime,timezone
from pathlib import Path
import gzip,json
from acquire import OWN,digest,select
from declare import separation

def main():
    plan=json.loads((OWN/'partition-plan.json').read_text());index=json.loads((OWN/'query-provenance.json').read_text());actual=json.loads((OWN/'selected-groups.json').read_text())
    discoveries={}
    for query in index['queries']:
        for row in query['files']:
            payload=gzip.decompress(Path(row['published_path']).read_bytes())
            import hashlib
            if hashlib.sha256(payload).hexdigest()!=row['uncompressed_sha256']or digest(row['published_path'])!=row['gzip_sha256']:raise ValueError('Published exact metadata bytes changed')
            if row['original_path'].endswith('discovery.json'):discoveries[query['parent_id']]=json.loads(payload)
    excluded=set(plan['excluded_physical_obsids']);replayed=[];mapping=[]
    for group in plan['groups']:
        selected=select(group,discoveries[group['parent_id']].get('rows',[]),excluded);replayed.append(selected)
        for row in selected.get('exposures',[]):
            if row['obs_id']in excluded:raise ValueError('Physical OBSID cross-parent/split overlap')
            excluded.add(row['obs_id']);mapping.append(dict(parent_id=group['parent_id'],split=group['split'],detector=selected['detector'],physical_obsid=row['obs_id'],t_min_mjd=float(row['t_min']),t_max_mjd=float(row['t_max']),parent_url=row['access_url']))
    if replayed!=actual:raise ValueError('Prospective selection not reproducible from exact published metadata')
    report=dict(schema_version=4,audited_utc=datetime.now(timezone.utc).isoformat(),scope='Offline metadata-only selection replay; no native files/pixels/model accessed',
        plan_sha256=digest(OWN/'partition-plan.json'),query_index_sha256=digest(OWN/'query-provenance.json'),selection_sha256=digest(OWN/'selected-groups.json'),
        source_sha256={p.name:digest(p)for p in [Path(__file__),OWN/'acquire.py',OWN/'declare.py']},
        exact_selection_replayed=True,parent_counts={s:sum(g['split']==s for g in plan['groups'])for s in ['train','validation','final']},
        unique_selected_physical_obsids=len(mapping),excluded_v3_or_legacy_obsids=len(plan['excluded_physical_obsids']),physical_obsid_overlap_with_excluded_or_other_parent=0,
        minimum_new_to_old_separation_deg=min(separation(g['center'],old)for g in plan['groups']for old in plan['excluded_parent_centers'].values()),
        minimum_new_parent_pair_separation_deg=min(separation(g['center'],h['center'])for i,g in enumerate(plan['groups'])for h in plan['groups'][i+1:]),
        selected_physical_observations=mapping)
    path=OWN/'selection-audit.json'
    with path.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in report.items()if k!='selected_physical_observations'},indent=2))
if __name__=='__main__':main()
