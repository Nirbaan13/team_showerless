"""Portable metadata-only audit. Never imports a FITS or inference reader."""
from pathlib import Path
import argparse, hashlib, json, math


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def separation(a,b):
    ra,da,rb,db=map(math.radians,[*a,*b]);v=math.sin((da-db)/2)**2+math.cos(da)*math.cos(db)*math.sin((ra-rb)/2)**2
    return math.degrees(2*math.asin(min(1.,math.sqrt(max(0.,v)))))


def audit(root):
    root=Path(root);plan=json.loads((root/'plan.json').read_text())
    if sha(root/'acquire_holdout.py')!=plan['code_sha256']:raise ValueError('Acquisition source changed')
    if len(plan['groups'])!=12:raise ValueError('Exactly12prospective parent slots required')
    groups={g['group_id']:g for g in plan['groups']}
    if len(groups)!=12:raise ValueError('Repeated parent ID')
    if len(set(plan['excluded_physical_obsids']))!=438:raise ValueError('Physical exclusions changed')
    for name,h in plan['sources'].items():
        if sha(root.parent/name)!=h:raise ValueError('Source provenance changed: '+name)
    known=json.loads((root.parent/'known_objects/plan.json').read_text());ceres=json.loads((root.parent/'known_objects/point-grid-0750/raw-handoff.json').read_text())
    if set(plan['excluded_physical_obsids'])!=set(known['excluded_physical_obsids'])|set(ceres['physical_obsids']):raise ValueError('Missing prior physical OBSID')
    minimum=180.
    for i,g in enumerate(plan['groups']):
        d=min(separation(g['center'],c)for c in list(plan['excluded_parent_centers'].values())+[x['center']for x in plan['groups'][:i]])
        if d<8.5:raise ValueError('Spatial parent/ROI reuse')
        minimum=min(minimum,d)
    if sorted(g['preferred_detector']for g in groups.values())!=[1]*4+[2]*4+[3]*4:raise ValueError('Detector balance changed')
    if sum(g['stratum']=='low_galactic_latitude'for g in groups.values())!=6:raise ValueError('Latitude balance changed')
    amendment=json.loads((root/'retry-percent20/amendment.json').read_text())
    if [amendment['native_seed_reservation'][g['group_id']]for g in plan['groups']]!=list(range(4110001,4110013)):raise ValueError('Reserved native seeds changed')
    query_counts={};failed_urls=0
    for attempt in ['initial','percent20','time-window','final-exact-retry']:
        paths=sorted((root/'query-evidence'/attempt).glob('*.json'))
        if len(paths)!=12:raise ValueError('Incomplete recorded query batch: '+attempt)
        seen=set()
        for path in paths:
            row=json.loads(path.read_text());identity=row['group_id']
            if identity not in groups or identity in seen:raise ValueError('Query parent alignment changed')
            seen.add(identity)
            if row['center']!=groups[identity]['center']:raise ValueError('Query coordinate changed')
            if row.get('rows')or not row.get('error'):raise ValueError('This incomplete capsule unexpectedly contains selectable metadata')
            if '502'not in row['error']:raise ValueError('Unexpected failure class requires explicit review')
            failed_urls+=1
        query_counts[attempt]=len(paths)
    for attempt in ['','retry-percent20','time-window','final-exact-retry']:
        report=json.loads((root/attempt/'byte-header-audit.json').read_text())
        if any(report[k]!=0 for k in ['selected_metadata_groups','downloaded_files','bytes']):raise ValueError('Nonzero data requires separate raw audit')
        if report['pixels_opened']or report['models_called']or report['injections_generated']:raise ValueError('Quarantine breached')
    return dict(status='PASS_INCOMPLETE_METADATA_CAPSULE',planned_parents=12,acquired_parents=0,raw_files=0,
                excluded_physical_obsids=438,minimum_prior_or_new_center_distance_deg=minimum,query_batches=query_counts,
                failed_query_urls=failed_urls,no_coverage_claim=False,pixels_opened=False,
                scope='Source, reservation, metadata-domain and failure-accounting audit ONLY; no data/coverage/recovery available')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);args=p.parse_args()
    print(json.dumps(audit(args.root),indent=2))
