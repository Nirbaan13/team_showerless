"""Append-only native-field expansion; no fitting and no final FITS opening."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path

from acquire import discover,download_group,write_json

ROOT=Path('/tmp/spaceapps-v3-native-data')
EXPANSION=ROOT/'expansion-v2'
FIELDS=[
    ('validation06','validation','crowded_low_galactic_latitude',45.,0.,288.4275759,10.7237033,1),
    ('validation07','validation','crowded_low_galactic_latitude',90.,0.,318.0043815,48.3296372,2),
    ('validation08','validation','crowded_low_galactic_latitude',140.,0.,46.8132814,58.2977051,3),
    ('validation09','validation','off_plane',50.,50.,238.7463378,31.1454092,1),
    ('validation10','validation','off_plane',160.,-50.,35.7948783,6.1519051,2),
    ('validation11','validation','off_plane',280.,50.,178.1156476,-10.2275287,3),
    ('final05','final','crowded_low_galactic_latitude',10.,0.,271.9404223,-20.2900295,1),
    ('final06','final','crowded_low_galactic_latitude',70.,0.,301.8661880,32.4424569,2),
    ('final07','final','crowded_low_galactic_latitude',190.,0.,91.9404223,20.2900295,3),
    ('final08','final','off_plane',0.,50.,225.5362254,2.1950040,1),
    ('final09','final','off_plane',120.,50.,197.6899661,67.0181134,2),
    ('final10','final','off_plane',280.,-50.,44.1650668,-61.1831929,3),
]


def declare():
    destination=EXPANSION/'partition-plan.json'
    if destination.exists():
        raise SystemExit('Refusing to overwrite append-only declaration')
    sources=[ROOT/'partition-plan.json',ROOT/'cadence-supplement-plan.json',ROOT/'crowded-development/partition-plan.json',ROOT/'audit.json',ROOT/'data-handoff.json']
    plan={'schema_version':2,'declared_utc':datetime.now(timezone.utc).isoformat(),
          'groups':[dict(group_id=name,split=split,stratum=stratum,galactic_lon_lat_deg=[lon,lat],center=[ra,dec],preferred_detector=det)
                    for name,split,stratum,lon,lat,ra,dec,det in FIELDS],
          'coordinate_selection':'Fixed Galactic longitudes/latitudes transformed to ICRS, checked geometrically against all original17 parents and all new parents; no archive query, pixel or model score used.',
          'minimum_center_separation_deg':8.,
          'selection':'Per detector, inspect metadata windows starting at an exposure with >=3 unique OBSIDs in the first1.5h; retain earliest up-to4 short-cluster epochs, add uniformly spanning metadata followups to at most8total. Priority tiers:8epochs spanning>=2h within48h;6–7epochs spanning>=2h within48h;8epochs spanning>=2h within168h;6–7epochs spanning>=2h within168h; otherwise explicitly constrained earliest short group. Prefer declared balanced detector within the best feasible tier, then earliest physical date. No model/pixel filter.',
          'primary_final':'Original4 final augmented8epoch variants plus new6 augmented variants; metadata-only primary selection declared by coordinator before any final pixel access. Short clusters secondary, never additional independent units.',
          'quarantine':'Final bytes, primary FITS signature and hash metadata only; no FITS reader, pixels, injections, detector, features or model score until coordinator freezes model and evaluation source/protocol.',
          'parent_unit':'Every crop, version, detector, epoch and short/augmented variant of the same physical OBSID stays in one sky parent and split.',
          'source_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'original_sources':[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())for p in sources]}
    write_json(destination,plan)
    print('plan_sha256',hashlib.sha256(destination.read_bytes()).hexdigest(),flush=True)


def unique_rows(discovery,detector):
    rows=[r for r in discovery.get('rows',[])if r.get('energy_bandpassname')==f'SPHEREx-D{detector}'and'/dr1/'in r.get('access_url','')]
    rows.sort(key=lambda r:(float(r['t_min']),r['obs_id'],r['access_url']))
    seen=set();unique=[]
    for row in rows:
        if row['obs_id']not in seen:
            seen.add(row['obs_id']);unique.append(row)
    return unique


def selected_group(declared,discovery):
    choices=[]
    for detector in [1,2,3]:
        rows=unique_rows(discovery,detector)
        for i,start in enumerate(rows):
            t0=float(start['t_min'])
            short=[r for r in rows[i:]if(float(r['t_min'])-t0)*24<=1.5][:4]
            if len(short)<3:
                continue
            short_ids={r['obs_id']for r in short}
            for hours in [48.,168.]:
                available=[r for r in rows[i:]if(float(r['t_min'])-t0)*24<=hours and r['obs_id']not in short_ids]
                n=min(8-len(short),len(available))
                extra=([available[round(j*(len(available)-1)/(n-1))]for j in range(n)]if n>1 else available[:n])
                chosen=sorted(short+extra,key=lambda r:float(r['t_min']))
                span=(float(chosen[-1]['t_max'])-float(chosen[0]['t_min']))*24
                if len(chosen)>=8 and span>=2:
                    tier=0 if hours==48 else 2
                elif len(chosen)>=6 and span>=2:
                    tier=1 if hours==48 else 3
                else:
                    tier=4
                choices.append(((tier,detector!=declared['preferred_detector'],t0,hours),detector,chosen,short,span,hours))
    if not choices:
        return dict(declared,error='No metadata-supported SWIR native cluster with at least3 unique physical exposures')
    priority,detector,chosen,short,span,hours=min(choices,key=lambda x:x[0])
    return dict(declared,group_id=declared['group_id']+'-augmented',parent_group_id=declared['group_id'],
                detector=detector,exposures=chosen,short_exposures=short,span_hours=span,
                metadata_window_hours=hours,selection_tier=priority[0],primary_variant='augmented',
                feasibility_constraints=[]if len(chosen)>=6 and span>=2 else['Archive metadata did not supply >=6 epochs spanning>=2h in the declared windows; constrained field retained without performance filtering.'])


def prior_obsids():
    audit=json.loads((ROOT/'audit.json').read_text())
    return {r['obs_id']for g in audit['groups']for r in g.get('downloads',[])}


def select(plan):
    selected=[];seen={oid:'original17'for oid in prior_obsids()}
    for group in plan['groups']:
        discovery=json.loads((EXPANSION/'metadata'/group['group_id']/'discovery.json').read_text())
        result=selected_group(group,discovery)
        for row in result.get('exposures',[]):
            if row['obs_id']in seen:
                raise ValueError(f"Physical OBSID overlaps another parent: {row['obs_id']} / {seen[row['obs_id']]}")
            seen[row['obs_id']]=group['group_id']
        selected.append(result)
        print(group['group_id'],result.get('detector'),len(result.get('exposures',[])),result.get('span_hours'),result.get('selection_tier'),result.get('error','ok'),flush=True)
    destination=EXPANSION/'selected-groups.json'
    if destination.exists():
        raise SystemExit('Refusing to overwrite selected metadata; append a new protocol version if needed')
    write_json(destination,selected)
    print('selected_sha256',hashlib.sha256(destination.read_bytes()).hexdigest(),flush=True)


def materialize_short(group):
    if group.get('error'):
        return
    base=EXPANSION/('quarantine_final'if group['split']=='final'else'development')
    source=base/group['group_id'];destination=base/'variants'/(group['parent_group_id']+'-short')
    destination.mkdir(parents=True,exist_ok=True)
    short_ids={r['obs_id']for r in group['short_exposures']}
    rows=[]
    for row in json.loads((source/'downloads.json').read_text()):
        if row['obs_id']not in short_ids:
            continue
        path=Path(row['path']).resolve();link=destination/path.name
        if link.is_symlink():
            assert link.resolve()==path
        elif not link.exists():
            link.symlink_to(path)
        else:
            raise ValueError(f'Refusing to replace {link}')
        rows.append(dict(row,path=str(link),source_path=str(path)))
    write_json(destination/'downloads.json',rows)
    write_json(destination/'group.json',dict(parent_group_id=group['parent_group_id'],split=group['split'],center=group['center'],detector=group['detector'],variant='secondary_short',independent_parent_fields=1,pixels_opened=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['declare','discover','select','download','materialize-short'])
    parser.add_argument('--groups',nargs='*')
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    if not 1<=args.workers<=4:
        parser.error('network workers must be1–4')
    if args.command=='declare':
        declare();return
    plan=json.loads((EXPANSION/'partition-plan.json').read_text())
    if args.command=='select':
        select(plan);return
    groups=plan['groups']if args.command=='discover'else json.loads((EXPANSION/'selected-groups.json').read_text())
    groups=[g for g in groups if not args.groups or g.get('parent_group_id',g['group_id'])in args.groups]
    if args.command=='materialize-short':
        for group in groups:
            materialize_short(group)
        return
    function=discover if args.command=='discover'else download_group
    with ThreadPoolExecutor(max_workers=args.workers)as executor:
        for future in as_completed([executor.submit(function,g,EXPANSION)for g in groups]):
            result=future.result();print(result['group_id'],len(result.get('rows',[]))if args.command=='discover'else result.get('downloaded_exposures',0),result.get('error','ok'),flush=True)


if __name__=='__main__':
    main()
