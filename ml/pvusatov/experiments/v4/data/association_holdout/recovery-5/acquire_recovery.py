"""Prospective finite-valid-time eligibility amendment; fixed all-time union transport."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import urlencode
import argparse,copy,datetime,hashlib,json,math,time,types,xml.etree.ElementTree as ET

OWN=Path(__file__).resolve().parent
BASE=OWN.parent
R3=BASE/'recovery-3'
R4=BASE/'recovery-4'
RAW=Path('/tmp/spaceapps-association-native-recovery2/recovery-5')

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def ref(path):return dict(path=str(path.resolve()),sha256=sha(path))
def read(path):return json.loads(Path(path).read_text())
def write(path,value):
    if path.exists():raise ValueError('Immutable evidence exists: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def checked(item):
    p=Path(item['path']);assert sha(p)==item['sha256'],str(p);return p
def exact(name,item):
    p=checked(item);m=types.ModuleType(name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def midpoint_utc(mjd):return datetime.datetime.fromtimestamp((mjd-40587)*86400,datetime.timezone.utc).isoformat()

def eligible(group,rows,excluded,helper):
    output=[];counts=dict(input_rows=len(rows),unsupported=0,excluded=0,invalid_time=0,footprint=0,eligible=0)
    for row in rows:
        if row.get('energy_bandpassname')not in ['SPHEREx-D1','SPHEREx-D2','SPHEREx-D3']or'/dr1/'not in row.get('access_url',''):
            counts['unsupported']+=1;continue
        if helper.physical_id(row['obs_id'])in excluded:counts['excluded']+=1;continue
        try:
            low=float(row['t_min']);high=float(row['t_max'])
            valid=math.isfinite(low)and math.isfinite(high)and high>=low
        except (ValueError,TypeError,KeyError):valid=False
        if not valid:counts['invalid_time']+=1;continue
        if helper.footprint_radius(row['s_region'],group['center'])>4.:counts['footprint']+=1;continue
        output.append(row)
    counts['eligible']=len(output);return output,counts

def context():
    plan=read(OWN/'amendment-plan.json');checked(plan['wrapper'])
    assert sha(OWN/'amendment-plan.json')==sha(RAW/'amendment-plan.json')
    for key in ['original_plan','native_seed_amendment','scientific_amendment_R3','previous_handoff','previous_selection','previous_publication']:checked(plan[key])
    original=read(plan['original_plan']['path']);previous=read(plan['previous_handoff']['path'])
    modules={name:exact('r5_'+name,item)for name,item in plan['sources'].items()}
    return plan,original,previous,modules

def declare():
    if (OWN/'amendment-plan.json').exists()or RAW.exists():raise ValueError('New evidence paths required')
    previous=read(R4/'transport-plan.json');handoff=read(R4/'guarded-handoff.json');selection=read(R3/'selection.json')
    assert handoff['counts']['physical_exposures']==80 and handoff['counts']['acquired_parents']==10
    caches={}
    for g in selection:
        if not g['metadata_complete']:continue
        evidence_path=R3/'query-evidence'/f"{g['group_id']}.json";evidence=read(evidence_path);discovery=read(checked(evidence['rows_ref']))
        assert discovery['complete'];source=discovery['attempts'][-1]['source'];checked(source)
        caches[g['group_id']]=dict(evidence=ref(evidence_path),discovery=evidence['rows_ref'],source=source)
    assert len(caches)==10
    start=datetime.datetime.now(datetime.timezone.utc)
    plan=dict(schema_version=1,declared_utc=start.isoformat(),deadline_utc=(start+datetime.timedelta(minutes=20)).isoformat(),wrapper=ref(Path(__file__)),
        root_authorization='Root explicitly authorized new uniform finite-valid-time eligibility amendment before queries, conditional on all10cached8-identity parity. Separate root review and external handoff release required before ANY native inference.',
        original_plan=previous['original_plan'],native_seed_amendment=previous['native_seed_amendment'],scientific_amendment_R3=previous['scientific_amendment'],previous_handoff=ref(R4/'guarded-handoff.json'),previous_selection=ref(R3/'selection.json'),previous_publication=ref(R4/'publication-manifest.json'),sources=previous['sources'],
        scientific_amendment=dict(eligibility_order='For ALL12parents: original supported D1-D3 DR1 artifacts and physical exclusions; BOTH t_min/t_max numeric finite with t_max>=t_min; SAME4degree footprint prefilter; exact unchanged acquire.select detector/temporal rules; exactly8uniquephysicalepochs and samepostchecks.',
            changed_behavior='Null/nonfinite/non-numeric/reversed-time rows explicitly ineligible. Original selector could abort entire field on null and has no finite-time validation; this is a new criteria amendment, NOT old-code/catalog equivalence.',
            disclosure='Prospective before new queries and native pixels/features/scores, AFTER synthetic unblinding, cachedmetadata inspection, and80manual native header reads. No actual native pixel/quality/scorer outcome informed this amendment.',
            uniformity='Replay all10cached complete fields under this rule and require SAME sealed ordered8metadata/physicalIDs before queries AND again after integrating05/09. Any changed cached identity stops acquisition; no silent cohort change.',
            domain_claim='Complete union covers finite-valid-time ELIGIBLE observations only; no unrestricted/null-time catalog exhaustiveness or previous-rule equivalence claim.'),
        cached_metadata=caches,retry_group_ids=['association-holdout-05','association-holdout-09'],boundary_utc='2025-10-01T00:00:00+00:00',boundary_mjd=60949.,partitions=[dict(name='through-boundary',TIME='-Inf 60949.0'),dict(name='from-boundary',TIME='60949.0 +Inf')],
        query=dict(endpoint='https://irsa.ipac.caltech.edu/SIA',collection='spherex_dr1',radius_deg=.001,limits=[512,4096],max_workers=2,max_requests_per_partition=2,max_total_requests=8,timeout_seconds=90,response_cap_bytes=12*1024**2,cache_control='no-cache',
            attempts='At most2HTTPrequests TOTAL perpartition including retries/overflow upgrade. Start512; upgrade4096only onOVERFLOW if secondrequest remains; if incompletefailclosed.',
            union='Both inclusive partitions complete QUERY_STATUS OK, no ERROR/OVERFLOW. Check finite-valid rows overlap requested interval. Deduplicate by(access_url,physical_OBSID,detector band); conflicting duplicate metadata aborts. No window restriction or alternate positions.',
            sources=['https://www.ivoa.net/documents/SIA/20151223/REC-SIA-2.0-20151223.html','https://irsa.ipac.caltech.edu/ibe/sia.html']),
        acquisition=dict(max_new_files=16,max_total_files=96,max_total_bytes=500000000,max_file_bytes=5200000,max_workers=4,max_attempts=2,timeout_seconds=90,size_deg=.12),
        roi=dict(region_arcmin=[6,6],pixel_scale_arcsec=6.15,mask_policy='motion',recenter=False),raw_root=str(RAW),pixels_opened=False,models_called=False,injections_generated=False,inference_authorized=False)
    RAW.mkdir()
    for path in [OWN/'amendment-plan.json',RAW/'amendment-plan.json']:write(path,plan)
    print(json.dumps(dict(amendment_sha256=sha(OWN/'amendment-plan.json'),deadline_utc=plan['deadline_utc'],cached_parents=10,metadata_retry_parents=2,max_metadata_requests=8)),flush=True)

def selected(group,rows,excluded,plan,modules):
    helper=modules['holdout'];old=modules['acquire'];reservation=read(plan['native_seed_amendment']['path'])['native_seed_reservation'];declaration=dict(group,seed=reservation[group['group_id']])
    filtered,counts=eligible(group,rows,excluded,helper);result=old.select(declaration,filtered,excluded);result['eligibility_counts']=counts
    if not result.get('error'):
        ids=[helper.physical_id(r['obs_id'])for r in result['exposures']]
        if len(ids)!=8 or len(set(ids))!=8 or set(ids)&excluded:result['error']='Exactly8unique eligible unexcluded physical observations required'
        else:
            radii=[helper.footprint_radius(r['s_region'],group['center'])for r in result['exposures']];assert max(radii)<=4.;result['s_region_max_radius_deg']=max(radii)
    return result

def cached_rows(plan,modules):
    rows={}
    for identity,cached in plan['cached_metadata'].items():
        checked(cached['evidence']);discovery=read(checked(cached['discovery']));source=checked(cached['source']);parsed,status=modules['acquire'].parse(source)
        assert parsed==discovery['rows']and discovery['complete']
        values=[s.get('value')for s in status if s.get('name')=='QUERY_STATUS'];assert values and all(s=='OK'for s in values)
        rows[identity]=parsed
    return rows

def parity():
    plan,original,previous,modules=context();rows=cached_rows(plan,modules);old={g['group_id']:g for g in read(plan['previous_selection']['path'])};excluded=set(original['excluded_physical_obsids']);records=[]
    for group in original['groups']:
        identity=group['group_id']
        if identity not in rows:continue
        result=selected(group,rows[identity],excluded,plan,modules);assert not result.get('error'),identity
        before=[r['obs_id']for r in old[identity]['exposures']];after=[r['obs_id']for r in result['exposures']]
        assert before==after,'Cached10identity changed; STOP: '+identity
        assert result['detector']==old[identity]['detector']
        excluded.update(modules['holdout'].physical_id(r['obs_id'])for r in result['exposures'])
        records.append(dict(group_id=identity,same_ordered8_metadata_ids=True,obs_ids=after,detector=result['detector'],eligibility_counts=result['eligibility_counts']))
    assert len(records)==10
    proof=dict(status='PASS_ALL10_SAME_ORDERED8_IDENTITIES',amendment_ref=ref(OWN/'amendment-plan.json'),previous_selection=plan['previous_selection'],groups=records,network_queries_before_parity=0,pixels_opened=False,models_called=False)
    write(OWN/'cached-parity.json',proof);print(json.dumps(dict(parity=proof['status'],parents=10,physical_exposures=80,parity_sha256=sha(OWN/'cached-parity.json'),amendment_sha256=sha(OWN/'amendment-plan.json'))),flush=True)

def run():
    plan,original,previous,modules=context();parity=read(OWN/'cached-parity.json');assert parity['status']=='PASS_ALL10_SAME_ORDERED8_IDENTITIES'and parity['amendment_ref']['sha256']==sha(OWN/'amendment-plan.json')
    if (OWN/'selection.json').exists():raise ValueError('Selection already sealed')
    helper=modules['holdout'];old=modules['acquire'];headers=modules['headers'];deadline=datetime.datetime.fromisoformat(plan['deadline_utc']).timestamp()
    real_request=helper.Request
    helper.Request=lambda url,headers=None,**kwargs:real_request(url,headers=dict(headers or {},**{'Cache-Control':'no-cache'}),**kwargs)
    rows=cached_rows(plan,modules);original_by_id={g['group_id']:g for g in original['groups']}
    def partition(task):
        identity,part=task;group=original_by_id[identity];record=dict(group_id=identity,center=group['center'],partition=part,complete=False,attempts=[]);limit=512
        for number in range(2):
            url=plan['query']['endpoint']+'?'+urlencode(dict(POS=f"CIRCLE {group['center'][0]} {group['center'][1]} 0.001",COLLECTION='spherex_dr1',RESPONSEFORMAT='VOTABLE',MAXREC=limit,TIME=part['TIME']))
            attempt=dict(number=number+1,url=url,limit=limit,started_utc=utc());record['attempts'].append(attempt)
            try:
                source=helper.fetch(url,RAW/'metadata'/identity/f"{part['name']}-{number+1}.xml",plan['query']['response_cap_bytes'],90,1,deadline);parsed,status=old.parse(source['path']);attempt.update(source=source,status=status,row_count=len(parsed))
                xml=ET.parse(source['path']).getroot();names=xml.findall('.//{*}TABLE/{*}FIELD');assert all(len(row)==len(names)for row in xml.findall('.//{*}TABLEDATA/{*}TR'))
                values=[s.get('value')for s in status if s.get('name')=='QUERY_STATUS']
                if 'ERROR'in values:record['error']='SIA QUERY_STATUS ERROR; partition unsupported/incomplete';break
                if 'OVERFLOW'in values:
                    limit=4096;record['error']='Overflow; incomplete partition';continue
                assert values and all(v=='OK'for v in values),'Complete QUERY_STATUS OK required'
                for row in parsed:
                    try:low=float(row['t_min']);high=float(row['t_max']);valid=math.isfinite(low)and math.isfinite(high)and high>=low
                    except (ValueError,TypeError,KeyError):valid=False
                    if valid:assert low<=60949. if part['name']=='through-boundary'else high>=60949.,'Returned finite-valid interval violates TIME constraint'
                record.update(complete=True,rows=parsed);record.pop('error',None);break
            except Exception as error:
                attempt['error']=f'{type(error).__name__}: {error}';record['error']=attempt['error']
        path=RAW/'metadata'/identity/f"{part['name']}.json";write(path,record)
        compact={k:v for k,v in record.items()if k!='rows'};compact['raw_record_ref']=ref(path);write(OWN/'query-evidence'/f"{identity}-{part['name']}.json",compact)
        return record
    results={}
    tasks=[(identity,part)for identity in plan['retry_group_ids']for part in plan['partitions']]
    with ThreadPoolExecutor(max_workers=2)as pool:
        for future in as_completed([pool.submit(partition,task)for task in tasks]):
            record=future.result();results[(record['group_id'],record['partition']['name'])]=record;print('partition',record['group_id'],record['partition']['name'],len(record.get('rows',[])),record.get('error','complete'),flush=True)
    assert sum(len(r['attempts'])for r in results.values())<=8
    domains={}
    for identity in plan['retry_group_ids']:
        parts=[results[(identity,p['name'])]for p in plan['partitions']];domain=dict(group_id=identity,complete=all(p['complete']for p in parts),partition_evidence=[ref(OWN/'query-evidence'/f"{identity}-{p['partition']['name']}.json")for p in parts],scope='Finite-valid-time eligible domain only; inclusive union, no unrestricted null-time catalog claim')
        if domain['complete']:
            unique={};duplicates=0
            for part in parts:
                for row in part['rows']:
                    key=(row['access_url'],helper.physical_id(row['obs_id']),row.get('energy_bandpassname'))
                    if key in unique:
                        assert unique[key]==row,'Conflicting duplicate artifact metadata; STOP';duplicates+=1
                    else:unique[key]=row
            rows[identity]=list(unique.values());domain.update(union_rows=len(unique),identical_boundary_duplicates=duplicates)
        else:domain['error']='One or both complete finite-valid-time domain partitions unavailable; planned missing, no coverage claim'
        domains[identity]=domain
    write(OWN/'metadata-domains.json',domains)
    oldsealed={g['group_id']:g for g in read(plan['previous_selection']['path'])};excluded=set(original['excluded_physical_obsids']);selection=[]
    for group in original['groups']:
        identity=group['group_id'];result=selected(group,rows.get(identity,[]),excluded,plan,modules)
        if identity in domains and not domains[identity]['complete']:result['error']=domains[identity]['error']
        if identity in plan['cached_metadata']:
            assert not result.get('error')and[r['obs_id']for r in result['exposures']]==[r['obs_id']for r in oldsealed[identity]['exposures']],'Cached identity changed after union; STOP'
        if not result.get('error'):excluded.update(helper.physical_id(r['obs_id'])for r in result['exposures'])
        result['pixels_opened']=False;selection.append(result)
    write(OWN/'selection.json',selection);print('selection_sha256',sha(OWN/'selection.json'),'eligibleparents',sum(not g.get('error')for g in selection),flush=True)
    existing=[r for g in previous['planned_groups']for r in g['images']];assert len(existing)==80
    for item in existing:checked(item)
    tasks=[(g,r)for g in selection if g['group_id']in plan['retry_group_ids']and not g.get('error')for r in g['exposures']];assert len(tasks)<=16
    def download(task):
        group,row=task;obsid=helper.physical_id(row['obs_id']);url=row['access_url']+'?'+urlencode(dict(center=','.join(map(str,group['center'])),size=.12));path=RAW/'quarantine'/group['group_id']/Path(row['access_url']).name
        item=dict(group_id=group['group_id'],obs_id=obsid,physical_obsid=obsid,detector=group['detector'],url=url,source_url=url,path=str(path),metadata_obs_id=row['obs_id'],t_min_mjd=float(row['t_min']),t_max_mjd=float(row['t_max']),roi=plan['roi'])
        try:
            item.update(helper.fetch(url,path,5200000,90,2,deadline));item['header']=headers.inspect(path,obsid,group['detector']);mid=item['header']['midpoint_mjd'];assert item['t_min_mjd']-.000002<=mid<=item['t_max_mjd']+.000002
            item.update(midpoint_mjd=mid,midpoint_utc=midpoint_utc(mid),status='HEADER_VERIFIED_QUARANTINED')
        except Exception as error:item.update(error=f'{type(error).__name__}: {error}',status='PLANNED_MISSING_PRODUCT')
        return item
    acquired=[]
    with ThreadPoolExecutor(max_workers=4)as pool:
        for future in as_completed([pool.submit(download,t)for t in tasks]):
            item=future.result();acquired.append(item);print('newproduct',len(acquired),len(tasks),item['group_id'],item.get('error','header verified'),flush=True)
    downloads=sorted(existing+acquired,key=lambda r:(r['group_id'],r['t_min_mjd'],r['obs_id']));write(OWN/'byte-header-audit.json',dict(downloads=downloads,reused_existing_files=80,new_product_tasks=len(tasks),pixels_opened=False,models_called=False,injections_generated=False,inference_authorized=False))
    write(OWN/'execution-state.json',dict(status='ACQUISITION_FINISHED_QUARANTINED',amendment_ref=ref(OWN/'amendment-plan.json'),parity_ref=ref(OWN/'cached-parity.json'),selection_ref=ref(OWN/'selection.json'),metadata_requests=sum(len(r['attempts'])for r in results.values()),new_product_tasks=len(tasks),new_verified_products=sum(not r.get('error')for r in acquired),existing_verified_products=80,pixels_opened=False,models_called=False,inference_authorized=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['declare','parity','run']);args=parser.parse_args();globals()[args.command]()
