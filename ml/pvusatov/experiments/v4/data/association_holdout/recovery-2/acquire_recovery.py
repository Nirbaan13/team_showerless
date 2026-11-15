"""Append-only prospective transport recovery; metadata and manual FITS headers only."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode
import argparse, datetime, hashlib, json, time, types

OWN = Path(__file__).resolve().parent
PARENT = OWN.parent
DATA = PARENT.parent
RAW = Path('/tmp/spaceapps-association-native-recovery2')
FREEZE = DATA.parent/'association_validation/engineering-repair-1/freeze.json'

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''): digest.update(block)
    return digest.hexdigest()

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)

def exact(name, ref):
    path = Path(ref['path'])
    if sha(path) != ref['sha256']: raise ValueError('Verified source hash differs: '+str(path))
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def utc(mjd): return datetime.datetime.fromtimestamp((mjd-40587)*86400, datetime.timezone.utc).isoformat()
def ref(path): return dict(path=str(path.resolve()), sha256=sha(path))

def declare():
    if (OWN/'transport-plan.json').exists() or RAW.exists(): raise ValueError('Recovery evidence paths must be new')
    frozen = json.loads(FREEZE.read_text()); original = json.loads((PARENT/'plan.json').read_text())
    amendment = json.loads((PARENT/'retry-percent20/amendment.json').read_text())
    assert sha(PARENT/'plan.json') == frozen['native_plan']['sha256']
    assert sha(PARENT/'retry-percent20/amendment.json') == frozen['native_seed_amendment']['sha256']
    assert amendment['original_plan_sha256'] == frozen['native_plan']['sha256']
    assert len(original['groups']) == 12 and len(set(original['excluded_physical_obsids'])) == 438
    assert list(amendment['native_seed_reservation'].values()) == list(range(4110001,4110013))
    for relative, digest in original['sources'].items():
        assert sha(DATA/relative) == digest
    assert sha(PARENT/'acquire_holdout.py') == original['code_sha256']
    sources = {name:ref(path) for name,path in [('holdout', PARENT/'acquire_holdout.py'), ('acquire', DATA/'acquire.py'), ('headers', DATA/'headers.py')]}
    start = datetime.datetime.now(datetime.timezone.utc)
    plan = dict(schema_version=1, declared_utc=start.isoformat(), deadline_utc=(start+datetime.timedelta(minutes=45)).isoformat(),
        authorization='Root instructed new bounded transport-only recovery after user said continue; supersedes expired acquisition wall deadline only.',
        original_plan=frozen['native_plan'], native_seed_amendment=frozen['native_seed_amendment'], association_freeze=ref(FREEZE),
        original_closed_handoff=ref(PARENT/'quarantined-handoff.json'), sources=sources, wrapper=ref(Path(__file__)),
        group_ids=[g['group_id'] for g in original['groups']], native_seed_reservation=amendment['native_seed_reservation'],
        query=dict(endpoint='https://irsa.ipac.caltech.edu/SIA', collection='spherex_dr1', position='CIRCLE original_RA original_DEC 0.001', response_format='VOTABLE', limits=[512,4096], max_workers=2,max_attempts=2,timeout_seconds=90,response_cap_bytes=12*1024**2,
            completeness='Require QUERY_STATUS OK and no ERROR/OVERFLOW; upgrade512 to4096 only on overflow. Never select truncated rows. No TIME restriction, changed centers, MAXREC1 diagnostic selection, or added query domain.'),
        selection='Exact unchanged acquire.select after original physical-OBSID exclusions; original group order/detector preference/cadence/temporal spread; exactly8 unique physical exposures and original4degree full-footprint engineering bound. Seal all selections before products.',
        acquisition=dict(max_files=96,max_bytes=500000000,max_file_bytes=5200000,max_workers=4,max_attempts=2,timeout_seconds=90,size_deg=.12),
        roi=dict(region_arcmin=[6,6],pixel_scale_arcsec=6.15,mask_policy='motion',recenter=False),
        missing_policy='Any unavailable planned field remains planned missing with reason; no field replacement or quality/model filtering. Partial handoff cannot authorize native inference.',
        quarantine=dict(raw_root=str(RAW),header_only=True,pixels_opened=False,models_called=False,injections_generated=False,inference_authorized=False),
        handoff_schema=dict(groups='Only complete8-file header-verified parents; parent_id/group_id/seed/center/split/detector/images',
            planned_groups='All12original identities with status/missing reasons and actual images',
            image='source_url/path/sha256/bytes/obs_id/physical_obsid/detector/midpoint_mjd/midpoint_utc/t_min_mjd/t_max_mjd/header/ROI',
            bindings='original plan, seed amendment, recovery plan, sealed selection, source code, metadata provenance SHA256',
            counts='planned12/acquired/physical exposures/bytes; physical exclusion and spatial distances proof'))
    RAW.mkdir()
    for path in [OWN/'transport-plan.json', RAW/'transport-plan.json']: write(path,plan)
    print(json.dumps(dict(plan_sha256=sha(OWN/'transport-plan.json'),planned_parents=12,excluded_physical_obsids=438,deadline_utc=plan['deadline_utc'],schema=plan['handoff_schema'])),flush=True)

def context():
    retry=json.loads((OWN/'transport-plan.json').read_text());assert sha(__file__)==retry['wrapper']['sha256']
    assert sha(OWN/'transport-plan.json')==sha(RAW/'transport-plan.json')
    for key in ['original_plan','native_seed_amendment','association_freeze','original_closed_handoff']:
        item=retry[key];assert sha(item['path'])==item['sha256']
    original=json.loads(Path(retry['original_plan']['path']).read_text())
    for relative,digest in original['sources'].items():assert sha(DATA/relative)==digest
    modules={name:exact('recovery_'+name,item)for name,item in retry['sources'].items()}
    return retry,original,modules

def run():
    retry,original,modules=context(); h=modules['holdout']; old=modules['acquire']; headers=modules['headers']
    if (OWN/'selection.json').exists():raise ValueError('Refusing to overwrite sealed recovery selection')
    deadline=datetime.datetime.fromisoformat(retry['deadline_utc']).timestamp()
    query=retry['query']; started=now()
    def discover(group):
        record=dict(group_id=group['group_id'],center=group['center'],created_utc=now(),attempts=[],complete=False)
        for limit in query['limits']:
            url=query['endpoint']+'?'+urlencode(dict(POS=f"CIRCLE {group['center'][0]} {group['center'][1]} 0.001",COLLECTION='spherex_dr1',RESPONSEFORMAT='VOTABLE',MAXREC=limit))
            path=RAW/'metadata'/group['group_id']/f'sia-{limit}.xml'
            attempt=dict(url=url,limit=limit)
            try:
                info=h.fetch(url,path,query['response_cap_bytes'],query['timeout_seconds'],query['max_attempts'],deadline)
                rows,status=old.parse(path);attempt.update(source=info,status=status,row_count=len(rows));record['attempts'].append(attempt)
                states=[s.get('value') for s in status if s.get('name')=='QUERY_STATUS']
                if 'ERROR' in states:raise ValueError('SIA QUERY_STATUS ERROR')
                if 'OVERFLOW' in states:
                    if limit==query['limits'][-1]:raise ValueError('Metadata domain incomplete: OVERFLOW at original maximum4096; no selection')
                    continue
                if not states or any(s!='OK' for s in states):raise ValueError('No unambiguous complete QUERY_STATUS OK')
                if any(len(r)<len(rows[0]) for r in rows):raise ValueError('Incomplete metadata cells')
                record.update(rows=rows,complete=True,query_url=url);break
            except Exception as error:
                if attempt not in record['attempts']:record['attempts'].append(dict(attempt,error=f'{type(error).__name__}: {error}'))
                record['error']=f'{type(error).__name__}: {error}';break
        if not record['complete']:record.setdefault('error','Metadata domain incomplete; archive coverage unresolved')
        write(RAW/'metadata'/group['group_id']/'discovery.json',record)
        compact={k:v for k,v in record.items() if k!='rows'}
        compact['rows_ref']=ref(RAW/'metadata'/group['group_id']/'discovery.json')
        write(OWN/'query-evidence'/f"{group['group_id']}.json",compact)
        return record
    discoveries={}
    with ThreadPoolExecutor(max_workers=query['max_workers']) as pool:
        for future in as_completed([pool.submit(discover,g)for g in original['groups']]):
            item=future.result();discoveries[item['group_id']]=item
            print('metadata',item['group_id'],len(item.get('rows',[])),item.get('error','complete'),flush=True)
    selected=[];excluded=set(original['excluded_physical_obsids'])
    for group in original['groups']:
        declaration=dict(group,seed=retry['native_seed_reservation'][group['group_id']])
        d=discoveries[group['group_id']]
        eligible=[r for r in d.get('rows',[]) if h.physical_id(r['obs_id'])not in excluded] if d['complete'] else []
        result=old.select(declaration,eligible,excluded)
        if d.get('error'):result['error']=d['error']
        if not result.get('error'):
            try:
                observations=[h.physical_id(r['obs_id'])for r in result['exposures']]
                if len(observations)!=8 or len(set(observations))!=8 or set(observations)&excluded:raise ValueError('Exactly8unique unexcluded physical observations required')
                radii=[h.footprint_radius(r['s_region'],group['center'])for r in result['exposures']]
                if max(radii)>4:raise ValueError('Original full-parent footprint4degree engineering bound exceeded')
                result['s_region_max_radius_deg']=max(radii);excluded.update(observations)
            except Exception as error:result['error']=f'Original eligibility engineering check: {error}'
        result['metadata_complete']=d['complete'];result['pixels_opened']=False;selected.append(result)
    for path in [OWN/'selection.json',RAW/'selection.json']:write(path,selected)
    print('selection_sha256',sha(OWN/'selection.json'),'selected_parents',sum(not g.get('error')for g in selected),flush=True)
    tasks=[(g,r)for g in selected if not g.get('error')for r in g['exposures']]
    assert len(tasks)<=96
    def download(task):
        group,row=task;obsid=h.physical_id(row['obs_id']);url=row['access_url']+'?'+urlencode(dict(center=','.join(map(str,group['center'])),size=.12))
        path=RAW/'quarantine'/group['group_id']/Path(row['access_url']).name
        info=dict(group_id=group['group_id'],obs_id=obsid,physical_obsid=obsid,detector=group['detector'],url=url,source_url=url,path=str(path),metadata_obs_id=row['obs_id'],t_min_mjd=float(row['t_min']),t_max_mjd=float(row['t_max']),roi=retry['roi'])
        try:
            info.update(h.fetch(url,path,retry['acquisition']['max_file_bytes'],90,2,deadline))
            info['header']=headers.inspect(path,obsid,group['detector']);midpoint=info['header']['midpoint_mjd']
            if not info['t_min_mjd']-.000002<=midpoint<=info['t_max_mjd']+.000002:raise ValueError('Header midpoint outside selected physical interval')
            info.update(midpoint_mjd=midpoint,midpoint_utc=utc(midpoint),status='HEADER_VERIFIED_QUARANTINED')
        except Exception as error:info.update(error=f'{type(error).__name__}: {error}',status='PLANNED_MISSING_PRODUCT')
        return info
    downloads=[]
    with ThreadPoolExecutor(max_workers=4)as pool:
        for future in as_completed([pool.submit(download,t)for t in tasks]):
            item=future.result();downloads.append(item);write(RAW/'download-progress.json',downloads)
            print('download',len(downloads),len(tasks),item['group_id'],item.get('error','header verified'),flush=True)
    downloads.sort(key=lambda r:(r['group_id'],r['t_min_mjd'],r['obs_id']))
    write(OWN/'byte-header-audit.json',dict(downloads=downloads,pixels_opened=False,models_called=False,injections_generated=False))
    available=[];planned=[]
    for group in selected:
        images=[r for r in downloads if r['group_id']==group['group_id'] and not r.get('error')]
        complete=len(images)==8 and not group.get('error')
        entry={k:group[k]for k in ['group_id','parent_id','center','split','preferred_detector','stratum','seed']}
        entry.update(images=images,available=complete,status='COMPLETE_HEADER_VERIFIED_QUARANTINED'if complete else'PLANNED_MISSING')
        if 'detector'in group:entry['detector']=group['detector']
        if complete:
            entry.update(metadata_span_hours=group['metadata_span_hours'],metadata_window_hours=group['metadata_window_hours'],selection_tier=group['selection_tier'],s_region_max_radius_deg=group['s_region_max_radius_deg']);available.append(entry)
        else:entry['reason']=group.get('error','One or more planned product transfers/header engineering checks failed')
        planned.append(entry)
    total=sum(r.get('bytes',0)for r in downloads);assert total<=retry['acquisition']['max_bytes']
    identifiers=[r['obs_id']for r in downloads if not r.get('error')]
    assert len(set(identifiers))==len(identifiers) and not set(identifiers)&set(original['excluded_physical_obsids'])
    distances=[]
    for i,g in enumerate(original['groups']):
        distances.append(dict(group_id=g['group_id'],minimum_prior_or_new_center_distance_deg=min(h.separation(g['center'],c)for c in list(original['excluded_parent_centers'].values())+[x['center']for x in original['groups'][:i]])))
    proof=dict(excluded_physical_obsid_count=438,acquired_unique_physical_obsids=len(identifiers),intersection_with_exclusions=[],distances=distances,minimum_distance_deg=min(d['minimum_prior_or_new_center_distance_deg']for d in distances),
        full_native_parent_footprint_overlap_verified=False,footprint_scope='Original own-center4degree s_region bound and center separation; no unavailable prior full-parent footprint assertion')
    ready=len(available)==12 and len(identifiers)==96
    handoff=dict(schema_version=2,status='COMPLETE_HEADER_VERIFIED_QUARANTINED'if ready else'INCOMPLETE_PLANNED_MISSING',created_utc=now(),started_utc=started,
        evaluation_ready=ready,inference_authorized=False,injections_authorized=False,pixels_opened=False,models_called=False,groups=available,planned_groups=planned,
        counts=dict(planned_parents=12,acquired_parents=len(available),physical_exposures=len(identifiers),bytes=total),region_arcmin=[6,6],pixel_scale_arcsec=6.15,mask_policy='motion',
        excluded_physical_obsids=original['excluded_physical_obsids'],physical_and_spatial_proof=proof,plan_ref=retry['original_plan'],seed_amendment_ref=retry['native_seed_amendment'],
        recovery_plan_ref=ref(OWN/'transport-plan.json'),selection_ref=ref(OWN/'selection.json'),byte_header_audit_ref=ref(OWN/'byte-header-audit.json'),source_refs=retry['sources'],raw_root=str(RAW),
        quarantine='Raw products remain quarantined; root must explicitly release this exact digest after strict guard pass. No inference/injections authorized.',no_coverage_claim=False)
    write(OWN/'quarantined-handoff.json',handoff);write(RAW/'quarantined-handoff.json',handoff)
    print(json.dumps(dict(handoff_sha256=sha(OWN/'quarantined-handoff.json'),status=handoff['status'],counts=handoff['counts'])),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['declare','run']);args=parser.parse_args()
    declare()if args.command=='declare'else run()
