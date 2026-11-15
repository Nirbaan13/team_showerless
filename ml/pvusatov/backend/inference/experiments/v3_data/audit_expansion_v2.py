"""Append-only expanded audit; final FITS remain opaque hashed bytes."""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

from audit import development_metadata,separation
from acquire import write_json

ROOT=Path('/tmp/spaceapps-v3-native-data')
EXPANSION=ROOT/'expansion-v2'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--development-pixels',action='store_true')
    args=parser.parse_args()
    plan=json.loads((EXPANSION/'partition-plan.json').read_text())
    for row in plan['original_sources']:
        assert hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256'],f"Original artifact changed: {row['path']}"
    original=json.loads((ROOT/'audit.json').read_text())
    original_plans=json.loads((ROOT/'partition-plan.json').read_text())['groups']+json.loads((ROOT/'crowded-development/partition-plan.json').read_text())['groups']
    new=plan['groups'];pairs=[separation(g['center'],h['center'])for i,g in enumerate(new)for h in original_plans+new[:i]]
    assert min(pairs)>8
    seen={row['obs_id']:g['parent_group_id']for g in original['groups']for row in g.get('downloads',[])}
    selected=json.loads((EXPANSION/'selected-groups.json').read_text())
    groups=[]
    for group in selected:
        parent=group['parent_group_id']
        for row in group.get('exposures',[]):
            previous=seen.setdefault(row['obs_id'],parent)
            assert previous==parent,f"Cross-parent physical OBSID leakage: {row['obs_id']}"
        directory=EXPANSION/('quarantine_final'if group['split']=='final'else'development')/group['group_id']
        path=directory/'downloads.json';rows=json.loads(path.read_text())if path.exists()else[]
        verified=[]
        for row in rows:
            source=Path(row['path']);digest=hashlib.sha256(source.read_bytes()).hexdigest()
            assert digest==row['sha256']
            with source.open('rb')as opaque:
                assert opaque.read(9)==b'SIMPLE  ='
            assert source.stat().st_size%2880==0
            info=dict(row)
            if group['split']!='final'and args.development_pixels:
                info['native_quality']=development_metadata(source)
                assert info['native_quality']['physical_obsid_header']==row['obs_id']
                assert info['native_quality']['detector']==group['detector']
                midpoint=info['native_quality']['time_header']['MJD-AVG']
                assert abs(float(midpoint)-(row['t_min_mjd']+row['t_max_mjd'])/2)<1e-5
            verified.append(info)
        groups.append(dict(group_id=group['group_id'],parent_group_id=parent,split=group['split'],
                           stratum=group['stratum'],center=group['center'],galactic_lon_lat_deg=group['galactic_lon_lat_deg'],
                           detector=group['detector'],downloaded_exposures=len(verified),planned_exposures=len(group['exposures']),
                           metadata_span_hours=group['span_hours'],feasibility_constraints=group['feasibility_constraints'],
                           pixels_opened=bool(group['split']!='final'and args.development_pixels),downloads=verified))
    combined=original['groups']+groups
    counts={}
    for split in ['train','validation','final']:
        subset=[g for g in combined if g['split']==split];downloads=[r for g in subset for r in g.get('downloads',[])]
        counts[split]={'independent_parent_fields':len({g['parent_group_id']for g in subset}),
                       'native_mefs':len(downloads),'bytes':sum(r['bytes']for r in downloads)}
    report={'schema_version':2,'created_utc':datetime.now(timezone.utc).isoformat(),
            'expansion_plan_sha256':hashlib.sha256((EXPANSION/'partition-plan.json').read_bytes()).hexdigest(),
            'expansion_selected_sha256':hashlib.sha256((EXPANSION/'selected-groups.json').read_bytes()).hexdigest(),
            'original_audit_sha256':hashlib.sha256((ROOT/'audit.json').read_bytes()).hexdigest(),
            'source_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'cross_parent_physical_obsid_overlap':0,'final_pixels_opened':False,
            'minimum_new_to_existing_or_new_center_separation_deg':min(pairs),
            'counts':counts,'new_groups':groups,
            'primary_final_variant':'augmented, predeclared by coordinator before final pixels; short secondary; no parent count inflation'}
    write_json(EXPANSION/'audit-expanded-v2.json',report)
    print(json.dumps({k:v for k,v in report.items()if k!='new_groups'},indent=2))
    for g in groups:
        print(g['parent_group_id'],g['split'],g['downloaded_exposures'],g['metadata_span_hours'],'pixels',g['pixels_opened'],flush=True)


if __name__=='__main__':
    main()
