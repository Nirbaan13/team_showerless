"""Prospective independent association holdout: metadata and opaque bytes only."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse, datetime, gzip, hashlib, importlib.util, json, math, re, time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OWN = Path(__file__).resolve().parent
DATA = OWN.parent
RAW = Path('/tmp/spaceapps-v4-association-holdout')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def separation(a, b):
    ra, dec, rb, db = map(math.radians, [*a, *b])
    s = math.sin((dec-db)/2)**2 + math.cos(dec)*math.cos(db)*math.sin((ra-rb)/2)**2
    return math.degrees(2*math.asin(min(1., math.sqrt(max(0., s)))))


def physical_id(value):
    return re.sub(r'D[1-6]$', '', value)


def footprint_radius(region, center):
    terms = region.split()
    if terms[:2] != ['POLYGON', 'ICRS']: raise ValueError('Unsupported footprint syntax')
    values = list(map(float, terms[2:]))
    if len(values) < 6 or len(values)%2: raise ValueError('Malformed footprint')
    return max(separation(center, xy) for xy in zip(values[::2], values[1::2]))


def declare():
    if (OWN/'plan.json').exists(): raise ValueError('Plan already exists')
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    known_path = DATA/'known_objects/plan.json'; known = json.loads(known_path.read_text())
    handoff_path = DATA/'known_objects/point-grid-0750/raw-handoff.json'; known_raw = json.loads(handoff_path.read_text())
    excluded = sorted(set(known['excluded_physical_obsids']) | set(known_raw['physical_obsids']))
    centers = known['excluded_parent_centers'] | {'known-ceres':known_raw['center']}
    old_centers = list(centers.values()); groups = []
    grid = []
    for lat in [-8., 8., -35., 35., -60., 60.]:
        for lon in [7.5 + 15*i for i in range(24)]:
            c = SkyCoord(l=lon*u.deg, b=lat*u.deg, frame='galactic').icrs
            grid.append(dict(center=[round(c.ra.deg,8),round(c.dec.deg,8)],galactic_lon_lat_deg=[lon,lat],stratum='low_galactic_latitude' if abs(lat)==8 else 'off_plane'))
    remaining = list(grid)
    for i in range(12):
        stratum = 'low_galactic_latitude' if i%2 == 0 else 'off_plane'
        candidates = [g for g in remaining if g['stratum']==stratum]
        scored = [(min(separation(g['center'], c) for c in old_centers + [r['center'] for r in groups]),g) for g in candidates]
        distance, g = min(scored, key=lambda pair:(-pair[0],pair[1]['galactic_lon_lat_deg']))
        if distance < 8.5: raise ValueError('Insufficient spatially distinct deterministic grid')
        remaining.remove(g)
        groups.append(dict(g,group_id=f'association-holdout-{i+1:02d}',parent_id=f'association-holdout-{i+1:02d}',split='quarantined_association_holdout',preferred_detector=1+i%3,seed=3900001+i,minimum_center_distance_deg=distance))
    plan = dict(schema_version=1,declared_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                purpose='NEXT association research holdout; not V4 release gate; no policy/model selection on these pixels',
                groups=groups,grid=dict(longitudes='7.5+15k,k0..23',latitudes=[-8,8,-35,35,-60,60],algorithm='Alternate low/offplane; farthest minimum spherical distance to prior/new centers; tie lexicographic(l,b); require>=8.5deg; no coverage-informed replacements'),
                excluded_physical_obsids=excluded,excluded_parent_centers=centers,
                pilot_data='Only existing TRAIN01/TRAIN03 physical exposures; detector agent confirmed no additional raw parents',
                query=dict(collection='spherex_dr1',position='CIRCLE center .001deg',limits=[512,4096],max_workers=2,max_attempts=2,timeout_seconds=45,response_cap_bytes=12*1024**2),
                selection='Read-only existing acquire.select: earliest>=3exposures within1.5h plus deterministic temporal spread to8within48h, then168h; prefer>=2h span and declared detector, D1-D3 fallbacks; require EXACT8. No metadata-query field substitutions.',
                footprint_rule='6arcmin science ROIs disjoint by>=8.5deg center separation; selected full-parent s_region vertices additionally required within4deg of own center. Prior full-parent overlap proof limited to available prior s_region metadata; no hidden pixel validation.',
                acquisition=dict(max_files=96,max_bytes=500_000_000,max_file_bytes=5_200_000,max_workers=4,max_attempts=2,timeout_seconds=60,size_deg=.12,region_arcmin=[6,6],pixel_scale_arcsec=6.15,mask_policy='motion',deadline_utc=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=40)).isoformat()),
                quarantine=dict(pixels_opened=False,inference_authorized=False,injections_authorized=False,header_only=True,do_not_handoff_selection_details_to_policy_agent_until_frozen=True),
                no_replacement='Missing/failed fields remain planned missing; no pixel-quality or model filtering',
                sources={str(p.relative_to(DATA)):sha(p) for p in [known_path,handoff_path,DATA/'acquire.py',DATA/'headers.py',DATA/'selected-groups.json']},
                code_sha256=sha(__file__))
    write(OWN/'plan.json',plan);RAW.mkdir(exist_ok=False);write(RAW/'plan.json',plan)
    print(json.dumps(dict(plan_sha256=sha(OWN/'plan.json'),groups=len(groups),excluded_physical=len(excluded),minimum_center_separation=min(g['minimum_center_distance_deg']for g in groups))),flush=True)


def fetch(url, path, cap, timeout, attempts, deadline):
    failures=[]
    for attempt in range(attempts):
        if time.time() >= deadline: raise TimeoutError('Global acquisition deadline reached')
        try:
            path.parent.mkdir(parents=True,exist_ok=True); part=path.with_suffix(path.suffix+'.part')
            with urlopen(Request(url,headers={'User-Agent':'SpaceApps-association-holdout/1.0'}),timeout=min(timeout,max(1.,deadline-time.time()))) as response, part.open('wb') as out:
                count=0
                for block in iter(lambda:response.read(1048576),b''):
                    count+=len(block)
                    if count>cap:raise ValueError('Response exceeds predeclared byte cap')
                    out.write(block)
                headers={k:response.headers.get(k)for k in ['Date','Content-Type','Last-Modified','ETag']}
            part.replace(path)
            return dict(url=url,path=str(path),sha256=sha(path),bytes=count,response_headers=headers,failures=failures)
        except Exception as e:
            failures.append(dict(attempt=attempt+1,error=f'{type(e).__name__}: {e}'))
            path.with_suffix(path.suffix+'.part').unlink(missing_ok=True)
            if attempt+1==attempts:raise RuntimeError(json.dumps(failures)) from e
            time.sleep(1)


def run():
    plan=json.loads((OWN/'plan.json').read_text());assert sha(OWN/'plan.json')==sha(RAW/'plan.json')and sha(__file__)==plan['code_sha256']
    for p,h in plan['sources'].items():assert sha(DATA/p)==h
    old=load_module('verified_v4_acquire',DATA/'acquire.py');headers=load_module('verified_v4_headers',DATA/'headers.py')
    deadline=datetime.datetime.fromisoformat(plan['acquisition']['deadline_utc']).timestamp()
    def discovery(group):
        record=dict(group,attempts=[])
        for limit in plan['query']['limits']:
            url='https://irsa.ipac.caltech.edu/SIA?'+urlencode(dict(POS=f"CIRCLE {group['center'][0]} {group['center'][1]} 0.001",COLLECTION='spherex_dr1',RESPONSEFORMAT='VOTABLE',MAXREC=limit))
            path=RAW/'metadata'/group['group_id']/f'sia-{limit}.xml'
            try:
                info=fetch(url,path,plan['query']['response_cap_bytes'],45,2,deadline);rows,status=old.parse(path);record['attempts'].append(dict(source=info,status=status))
                if any(s.get('value')=='ERROR'for s in status):raise ValueError('IRSA query reports ERROR')
                if any(s.get('value')=='OVERFLOW'for s in status):continue
                record['rows']=rows;break
            except Exception as e:record['error']=f'{type(e).__name__}: {e}';break
        if 'rows'not in record:record.setdefault('error','Query domain incomplete/overflow; not a no-coverage claim')
        write(RAW/'metadata'/group['group_id']/'discovery.json',record)
        return record
    discoveries={}
    with ThreadPoolExecutor(max_workers=2)as pool:
        for future in as_completed([pool.submit(discovery,g)for g in plan['groups']]):
            r=future.result();discoveries[r['group_id']]=r;print('metadata',r['group_id'],len(r.get('rows',[])),r.get('error','ok'),flush=True)
    selected=[];excluded=set(plan['excluded_physical_obsids'])
    for g in plan['groups']:
        d=discoveries[g['group_id']]
        rows=[r for r in d.get('rows',[])if physical_id(r['obs_id'])not in excluded]
        result=old.select(g,rows,excluded)
        if d.get('error'):result['error']=d['error']
        if len(result.get('exposures',[]))!=8:result['error']='Exactly8eligible physical exposures not available in declared metadata domain'
        if not result.get('error'):
            try:
                radii=[footprint_radius(r['s_region'],g['center'])for r in result['exposures']]
                if max(radii)>4:raise ValueError('Full-parent footprint exceeds predeclared4deg engineering bound')
                result['s_region_max_radius_deg']=max(radii)
            except Exception as e:result['error']=f'Footprint eligibility: {e}'
        if not result.get('error'):excluded.update(physical_id(r['obs_id'])for r in result['exposures'])
        result['pixels_opened']=False;selected.append(result)
    write(OWN/'selected-groups.json',selected);write(RAW/'selected-groups.json',selected)
    # Selection is completely sealed before any raw byte download.
    print('selection_sha256',sha(OWN/'selected-groups.json'),flush=True)
    tasks=[(g,r)for g in selected if not g.get('error')for r in g['exposures']]
    if len(tasks)>96:raise ValueError('Planned file budget exceeded')
    downloads=[]
    def download(task):
        g,r=task;url=r['access_url']+'?'+urlencode(dict(center=','.join(map(str,g['center'])),size=.12));path=RAW/'quarantine'/g['group_id']/Path(r['access_url']).name
        try:
            info=fetch(url,path,plan['acquisition']['max_file_bytes'],60,2,deadline)
            info.update(group_id=g['group_id'],obs_id=physical_id(r['obs_id']),detector=g['detector'],t_min_mjd=float(r['t_min']),t_max_mjd=float(r['t_max']))
            info['header']=headers.inspect(path,info['obs_id'],info['detector'])
            if not info['t_min_mjd']-.000002<=info['header']['midpoint_mjd']<=info['t_max_mjd']+.000002:raise ValueError('Header midpoint outside selected physical interval')
            return info
        except Exception as e:return dict(group_id=g['group_id'],obs_id=r['obs_id'],url=url,error=f'{type(e).__name__}: {e}')
    with ThreadPoolExecutor(max_workers=4)as pool:
        for future in as_completed([pool.submit(download,t)for t in tasks]):
            r=future.result();downloads.append(r);write(RAW/'download-progress.json',downloads);print('download',len(downloads),len(tasks),r['group_id'],r.get('error','ok'),flush=True)
    total=sum(r.get('bytes',0)for r in downloads)
    if total>plan['acquisition']['max_bytes']:raise ValueError('Total byte budget exceeded')
    report=dict(status='ACQUIRED_QUARANTINED',plan_sha256=sha(OWN/'plan.json'),selection_sha256=sha(OWN/'selected-groups.json'),groups_planned=12,selected_metadata_groups=sum(not g.get('error')for g in selected),downloaded_files=sum(not r.get('error')for r in downloads),bytes=total,downloads=downloads,missing_groups=[dict(group_id=g['group_id'],error=g['error'])for g in selected if g.get('error')],pixels_opened=False,models_called=False,injections_generated=False)
    write(OWN/'byte-header-audit.json',report);print(json.dumps({k:report[k]for k in ['groups_planned','selected_metadata_groups','downloaded_files','bytes']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['declare','run']);args=parser.parse_args()
    declare()if args.command=='declare'else run()
