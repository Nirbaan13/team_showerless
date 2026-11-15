"""Refine only failed metadata interval and retry two exact fixed artifacts; headers only."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import argparse,datetime,email.utils,hashlib,json,math,time,types,xml.etree.ElementTree as ET
OWN=Path(__file__).resolve().parent;BASE=OWN.parent;R5=BASE/'recovery-5';RAW=Path('/tmp/spaceapps-association-native-recovery2/recovery-6')

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def ref(p):return dict(path=str(p.resolve()),sha256=sha(p))
def read(p):return json.loads(Path(p).read_text())
def write(p,v):
    if p.exists():raise ValueError('Immutable evidence exists: '+str(p))
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def checked(v):p=Path(v['path']);assert sha(p)==v['sha256'],str(p);return p
def exact(name,v):
    p=checked(v);m=types.ModuleType(name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def context():
    plan=read(OWN/'transport-plan.json');checked(plan['wrapper']);assert sha(OWN/'transport-plan.json')==sha(RAW/'transport-plan.json')
    for key in ['R5_amendment','previous_handoff','previous_selection','previous_publication','same_eligibility_engine']:checked(plan[key])
    oldplan=read(plan['R5_amendment']['path']);modules={k:exact('r6_'+k,v)for k,v in plan['sources'].items()};engine=exact('unchanged_R5_criteria',plan['same_eligibility_engine'])
    return plan,oldplan,modules,engine

def declare():
    if (OWN/'transport-plan.json').exists()or RAW.exists():raise ValueError('New evidence paths required')
    oldplan=read(R5/'amendment-plan.json');previous=read(R5/'guarded-handoff.json');audit=read(R5/'byte-header-audit.json');missing=[r for r in audit['downloads']if r.get('error')]
    assert previous['counts']['physical_exposures']==86 and len(missing)==2 and{r['obs_id']for r in missing}=={'2025W38_2C_0439_2','2025W38_2C_0439_4'}
    start=datetime.datetime.now(datetime.timezone.utc);plan=dict(schema_version=1,declared_utc=start.isoformat(),deadline_utc=(start+datetime.timedelta(minutes=20)).isoformat(),wrapper=ref(Path(__file__)),
        root_authorization='Root authorized same R5 eligibility, failed05interval subdivision only, exact09artifact retries, conditional <=5.2MB same-full-artifact transport amendment; native inference unauthorized.',
        R5_amendment=ref(R5/'amendment-plan.json'),previous_handoff=ref(R5/'guarded-handoff.json'),previous_selection=ref(R5/'selection.json'),previous_publication=ref(R5/'publication-manifest.json'),same_eligibility_engine=ref(R5/'acquire_recovery.py'),sources=oldplan['sources'],
        cached_05_right=ref(R5/'query-evidence/association-holdout-05-from-boundary.json'),cached_09_parts=[ref(R5/'query-evidence'/f'association-holdout-09-{name}.json')for name in ['through-boundary','from-boundary']],
        unchanged='ALL12originalcoordinates,411seedmap,438exclusions,R5finite-valid-timeeligibility,4degreeprefilter,exacttemporal/detectorselection/ROI. All11sealedmetadata8IDs and86oldfilebytes retained; no replacements/qualityselection.',
        query=dict(group_id='association-holdout-05',partitions=[dict(name='before-june',TIME='-Inf 60827.0'),dict(name='june-through-october',TIME='60827.0 60949.0')],boundaries_utc=['2025-06-01T00:00:00+00:00','2025-10-01T00:00:00+00:00'],boundary_mjd=[60827.,60949.],
            equivalence='Refines ONLY failed[-Inf,60949] into[-Inf,60827]U[60827,60949], keepscached[60949,+Inf].Inclusivefinite-valid-timeeligibledomainunchanged; no unrestrictednullcatalogclaim.',max_workers=2,max_requests_per_partition=2,max_total_requests=4,timeout_seconds=90,limits=[512,4096],response_cap_bytes=12*1024**2,complete_only=True),
        missing_09_products=missing,diagnostic=dict(method='HEAD exactfailedcutoutURLs; captureHTTPerrorheaders/textbody<=2048bytesonly; compareexistinggoodmanualHDUdimensions/processingandSIAaccess_estsize.No FITS science payload inspection.',max_head_attempts=1),
        fixed_product_retry=dict(max_attempts=2,timeout_seconds=90,backoff_seconds=10,respect_retry_after=True),
        conditional_full_MEF=dict(role='TRANSPORT AMENDMENT for SAME original selected artifact URL without cutoutquery, not identity/ROI substitution or failedcutoutbyteparity.',
            prerequisite='OnlyafterbothfixedcutoutGETattemptsfail, HEADorRangeheadersprovefullobjectlength<=5200000bytes. UnknownoroversizeSTOP. SamephysicalID/D3/MJD/processingmustverify; analysisROI6arcmin/6.15/motion/recenterfalseunchanged.',
            transfer_gate='Writeconcretefallback-amendmentSHAwithURL/sizeproofBEFOREanyfullGET; returnproposalforrootnotificationbeforeseparateauthorizedtransfercommand. No fullGETifsize>cap/unknown.',max_file_bytes=5200000),
        acquisition=dict(max_new_files=10,max_total_files=96,max_total_bytes=500000000,max_file_bytes=5200000,max_workers=4,max_attempts=2,timeout_seconds=90,size_deg=.12),roi=oldplan['roi'],raw_root=str(RAW),pixels_opened=False,models_called=False,inference_authorized=False)
    RAW.mkdir()
    for p in [OWN/'transport-plan.json',RAW/'transport-plan.json']:write(p,plan)
    print(json.dumps(dict(plan_sha256=sha(OWN/'transport-plan.json'),source_sha256=sha(Path(__file__)),deadline_utc=plan['deadline_utc'],preserved_files=86,new_metadata_partitions=2,max_metadata_requests=4)),flush=True)

def rows_from_evidence(item,old):
    evidence=read(checked(item));record=read(checked(evidence['raw_record_ref']));assert record['complete'];last=record['attempts'][-1];parsed,status=old.parse(checked(last['source']));assert parsed==record['rows'];values=[s.get('value')for s in status if s.get('name')=='QUERY_STATUS'];assert values and all(v=='OK'for v in values);return parsed

def union(parts,helper):
    out={};duplicate=0
    for rows in parts:
        for row in rows:
            key=(row['access_url'],helper.physical_id(row['obs_id']),row.get('energy_bandpassname'))
            if key in out:assert out[key]==row,'Conflicting duplicate artifact metadata';duplicate+=1
            else:out[key]=row
    return list(out.values()),duplicate

def probe(url,method,deadline,range_header=False):
    record=dict(url=url,method=method,started_utc=utc());h={'User-Agent':'SpaceApps-association-recovery6/1.0','Cache-Control':'no-cache'}
    if range_header:h['Range']='bytes=0-0'
    try:
        with urlopen(Request(url,headers=h,method=method),timeout=min(90,max(1,deadline-time.time())))as response:
            record.update(status=response.status,response_headers=dict(response.headers),body_read=False)
    except HTTPError as error:
        record.update(status=error.code,response_headers=dict(error.headers))
        if 'text'in error.headers.get('Content-Type','')or'xml'in error.headers.get('Content-Type',''):
            record['error_body_text']=error.read(2048).decode('utf-8','replace');record['error_body_limit_bytes']=2048
        else:record['body_read']=False
    except Exception as error:record['error']=f'{type(error).__name__}: {error}'
    return record

def retry_after(headers):return next((v for k,v in headers.items()if k.lower()=='retry-after'),None)

def retry_delay(value):
    if not value:return 10.
    try:return max(10.,float(value))
    except ValueError:
        try:return max(10.,email.utils.parsedate_to_datetime(value).timestamp()-time.time())
        except Exception:return 10.

def run():
    plan,oldplan,modules,engine=context();helper=modules['holdout'];old=modules['acquire'];headers=modules['headers'];deadline=datetime.datetime.fromisoformat(plan['deadline_utc']).timestamp();original=read(oldplan['original_plan']['path']);previous=read(plan['previous_handoff']['path']);oldselection=read(plan['previous_selection']['path']);oldbyid={g['group_id']:g for g in oldselection}
    existing=[r for g in previous['planned_groups']for r in g['images']];assert len(existing)==86
    for item in existing:checked(item)
    rows=engine.cached_rows(oldplan,modules);rows['association-holdout-09'],_=union([rows_from_evidence(p,old)for p in plan['cached_09_parts']],helper)
    right=rows_from_evidence(plan['cached_05_right'],old);assert len(right)==141
    # Source/cache parity is established before any new request.
    excluded=set(original['excluded_physical_obsids']);parity=[]
    for group in original['groups']:
        identity=group['group_id']
        if identity not in rows:continue
        result=engine.selected(group,rows[identity],excluded,oldplan,modules);assert not result.get('error')and[r['obs_id']for r in result['exposures']]==[r['obs_id']for r in oldbyid[identity]['exposures']]
        excluded.update(helper.physical_id(r['obs_id'])for r in result['exposures']);parity.append(dict(group_id=identity,same_ordered8_ids=True))
    write(OWN/'cached11-parity.json',dict(status='PASS_ALL11_SAME_ORDERED8_IDENTITIES',groups=parity,old_files=86,network_requests_before_parity=0));assert len(parity)==11
    real_request=helper.Request;helper.Request=lambda url,headers=None,**kwargs:real_request(url,headers=dict(headers or {},**{'Cache-Control':'no-cache'}),**kwargs)
    # Mission/header engineering comparison; no science arrays.
    good=next(r for r in existing if r['group_id']=='association-holdout-09')
    with Path(good['path']).open('rb')as f:hdus=headers.scan(f,Path(good['path']).stat().st_size)
    comparison=dict(good_reference={k:good[k]for k in ['path','sha256','obs_id','detector','bytes']},manual_hdus=[dict(name=h['name'],dimensions=[h['header'].get('NAXIS1'),h['header'].get('NAXIS2')],data_bytes=h['data_bytes'],engineering={k:v for k,v in h['header'].items()if any(t in k for t in ['VERS','PIPE','PROC','FILE'])or k in ['VERSION','OBSID','DETECTOR','MJD-AVG']})for h in hdus],fixed_targets=[dict(obs_id=r['obs_id'],access_url=r['access_url'],access_estsize_kbyte=r.get('access_estsize'))for r in oldbyid['association-holdout-09']['exposures']if r['obs_id']in{m['obs_id']for m in plan['missing_09_products']}])
    write(OWN/'header-size-comparison.json',comparison)
    def retry09(original_item):
        item=dict(original_item);item.pop('error');item.pop('status');item['path']=str(RAW/'quarantine'/item['group_id']/Path(item['path']).name);diagnostic=probe(item['url'],'HEAD',deadline);attempts=[];wait=retry_delay(retry_after(diagnostic.get('response_headers',{})))
        for number in range(2):
            if time.time()+wait>=deadline:
                item.update(error='Globaldeadline/boundedbackoffpreventsnextfixedattempt',status='PLANNED_MISSING_PRODUCT');break
            time.sleep(wait);attempt=dict(number=number+1,backoff_seconds=wait,url=item['url'],started_utc=utc());attempts.append(attempt)
            try:
                item.update(helper.fetch(item['url'],Path(item['path']),5200000,90,1,deadline));item['header']=headers.inspect(item['path'],item['obs_id'],3);mid=item['header']['midpoint_mjd'];assert item['t_min_mjd']-.000002<=mid<=item['t_max_mjd']+.000002
                item.pop('error',None);item.update(midpoint_mjd=mid,midpoint_utc=engine.midpoint_utc(mid),status='HEADER_VERIFIED_QUARANTINED',transfer_method='EXACT_FIXED_CUTOUT_GET');attempt['status']='HEADER_VERIFIED';break
            except Exception as error:
                cause=error
                while cause.__cause__ is not None:cause=cause.__cause__
                attempt.update(error=f'{type(error).__name__}: {error}',response_headers=dict(cause.headers)if isinstance(cause,HTTPError)else{})
                if isinstance(cause,HTTPError)and('text'in cause.headers.get('Content-Type','')or'xml'in cause.headers.get('Content-Type','')):attempt['error_body_text']=cause.read(2048).decode('utf-8','replace')
                wait=retry_delay(retry_after(attempt['response_headers']));item.update(error=attempt['error'],status='PLANNED_MISSING_PRODUCT')
        fallback=None
        if item.get('error'):
            row=next(r for r in oldbyid['association-holdout-09']['exposures']if r['obs_id']==item['obs_id']);full=row['access_url'];sizeprobe=probe(full,'HEAD',deadline);hs={k.lower():v for k,v in sizeprobe.get('response_headers',{}).items()};size=None
            if sizeprobe.get('status')==200 and hs.get('content-length','').isdigit():size=int(hs['content-length'])
            if size is None:
                rangeprobe=probe(full,'GET',deadline,True);hs2={k.lower():v for k,v in rangeprobe.get('response_headers',{}).items()};sizeprobe['range_probe']=rangeprobe
                try:size=int(hs2['content-range'].rsplit('/',1)[1])if rangeprobe.get('status')==206 else int(hs2['content-length'])if rangeprobe.get('status')==200 else None
                except (KeyError,ValueError):size=None
            fallback=dict(full_source_url=full,size_proof=sizeprobe,proven_full_bytes=size,byte_cap=5200000,eligible=size is not None and size<=5200000,status='PENDING_DECLARED_TRANSFER_AMENDMENT'if size is not None and size<=5200000 else'STOP_OVERSIZE_OR_UNKNOWN_NO_FULL_TRANSFER')
            if fallback['eligible']:
                proposal=dict(declared_utc=utc(),original_plan_ref=ref(OWN/'transport-plan.json'),fixed_obs_id=item['obs_id'],detector=3,full_source_url=full,proven_bytes=size,size_proof=sizeprobe,analysis_roi=plan['roi'],byte_parity_to_failed_cutout_claim=False,inference_authorized=False)
                path=OWN/f"full-mef-proposal-{item['obs_id']}.json";write(path,proposal);fallback['proposal_ref']=ref(path);print('PENDING_FULL_MEF_PROPOSAL',str(path),sha(path),flush=True)
        return dict(obs_id=item['obs_id'],diagnostic=diagnostic,cutout_attempts=attempts,product=item,full_MEF_fallback=fallback)
    with ThreadPoolExecutor(max_workers=2)as pool:retry_results=list(pool.map(retry09,plan['missing_09_products']))
    write(OWN/'fixed09-retry.json',retry_results)
    def partition(part):
        group=next(g for g in original['groups']if g['group_id']=='association-holdout-05');record=dict(group_id=group['group_id'],center=group['center'],partition=part,complete=False,attempts=[]);limit=512
        for number in range(2):
            url='https://irsa.ipac.caltech.edu/SIA?'+urlencode(dict(POS=f"CIRCLE {group['center'][0]} {group['center'][1]} 0.001",COLLECTION='spherex_dr1',RESPONSEFORMAT='VOTABLE',MAXREC=limit,TIME=part['TIME']));attempt=dict(number=number+1,url=url,limit=limit);record['attempts'].append(attempt)
            try:
                source=helper.fetch(url,RAW/'metadata'/f"{part['name']}-{number+1}.xml",12*1024**2,90,1,deadline);parsed,status=old.parse(source['path']);attempt.update(source=source,status=status,row_count=len(parsed));xml=ET.parse(source['path']).getroot();fields=xml.findall('.//{*}TABLE/{*}FIELD');assert all(len(r)==len(fields)for r in xml.findall('.//{*}TABLEDATA/{*}TR'))
                values=[s.get('value')for s in status if s.get('name')=='QUERY_STATUS']
                if'ERROR'in values:record['error']='SIA QUERY_STATUS ERROR';break
                if'OVERFLOW'in values:limit=4096;record['error']='Incomplete overflow';continue
                assert values and all(v=='OK'for v in values)
                for row in parsed:
                    try:low=float(row['t_min']);high=float(row['t_max']);valid=math.isfinite(low)and math.isfinite(high)and high>=low
                    except(ValueError,TypeError,KeyError):valid=False
                    if valid:assert low<=60827. if part['name']=='before-june'else low<=60949. and high>=60827.
                record.update(complete=True,rows=parsed);record.pop('error',None);break
            except Exception as error:attempt['error']=f'{type(error).__name__}: {error}';record['error']=attempt['error']
        path=RAW/'metadata'/f"{part['name']}.json";write(path,record);compact={k:v for k,v in record.items()if k!='rows'};compact['raw_record_ref']=ref(path);write(OWN/'query-evidence'/f"{part['name']}.json",compact);return record
    with ThreadPoolExecutor(max_workers=2)as pool:parts=list(pool.map(partition,plan['query']['partitions']))
    complete=all(p['complete']for p in parts);domain=dict(complete=complete,parts=[ref(OWN/'query-evidence'/f"{p['partition']['name']}.json")for p in parts],cached_right_ref=plan['cached_05_right'],metadata_requests=sum(len(p['attempts'])for p in parts),finite_valid_domain_only=True)
    if complete:rows['association-holdout-05'],duplicate=union([p['rows']for p in parts]+[right],helper);domain.update(union_rows=len(rows['association-holdout-05']),identical_boundary_duplicates=duplicate)
    else:domain['error']='Refined finite-valid-time union incomplete; no selection from partial domain'
    write(OWN/'metadata-domain05.json',domain);selection=[];excluded=set(original['excluded_physical_obsids'])
    for group in original['groups']:
        identity=group['group_id'];result=engine.selected(group,rows.get(identity,[]),excluded,oldplan,modules)
        if identity=='association-holdout-05'and not complete:result['error']=domain['error']
        if identity!='association-holdout-05':assert not result.get('error')and[r['obs_id']for r in result['exposures']]==[r['obs_id']for r in oldbyid[identity]['exposures']]
        if not result.get('error'):excluded.update(helper.physical_id(r['obs_id'])for r in result['exposures'])
        selection.append(result)
    write(OWN/'selection.json',selection);print('selection',sha(OWN/'selection.json'),'complete05domain',complete,flush=True)
    tasks=[(g,r)for g in selection if g['group_id']=='association-holdout-05'and not g.get('error')for r in g['exposures']]
    def download05(task):
        group,row=task;obsid=helper.physical_id(row['obs_id']);url=row['access_url']+'?'+urlencode(dict(center=','.join(map(str,group['center'])),size=.12));path=RAW/'quarantine'/group['group_id']/Path(row['access_url']).name;item=dict(group_id=group['group_id'],obs_id=obsid,physical_obsid=obsid,detector=group['detector'],url=url,source_url=url,path=str(path),metadata_obs_id=row['obs_id'],t_min_mjd=float(row['t_min']),t_max_mjd=float(row['t_max']),roi=plan['roi'],transfer_method='FIXED_SELECTED_CUTOUT_GET')
        try:
            item.update(helper.fetch(url,path,5200000,90,2,deadline));item['header']=headers.inspect(path,obsid,group['detector']);mid=item['header']['midpoint_mjd'];assert item['t_min_mjd']-.000002<=mid<=item['t_max_mjd']+.000002;item.update(midpoint_mjd=mid,midpoint_utc=engine.midpoint_utc(mid),status='HEADER_VERIFIED_QUARANTINED')
        except Exception as error:item.update(error=f'{type(error).__name__}: {error}',status='PLANNED_MISSING_PRODUCT')
        return item
    with ThreadPoolExecutor(max_workers=4)as pool:new05=list(pool.map(download05,tasks))
    additions=[r['product']for r in retry_results]+new05;downloads=sorted(existing+additions,key=lambda r:(r['group_id'],r['t_min_mjd'],r['obs_id']))
    write(OWN/'byte-header-audit.json',dict(downloads=downloads,reused_existing_files=86,new_product_tasks=len(additions),pixels_opened=False,models_called=False,inference_authorized=False));write(OWN/'execution-state.json',dict(status='FINISHED_QUARANTINED',metadata_requests=domain['metadata_requests'],new_product_tasks=len(additions),new_verified_products=sum(not r.get('error')for r in additions),pending_full_MEF_proposals=[r['full_MEF_fallback']['proposal_ref']for r in retry_results if r['full_MEF_fallback']and r['full_MEF_fallback'].get('eligible')],pixels_opened=False,models_called=False,inference_authorized=False));print(json.dumps(read(OWN/'execution-state.json')),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['declare','run']);args=p.parse_args();globals()[args.command]()
