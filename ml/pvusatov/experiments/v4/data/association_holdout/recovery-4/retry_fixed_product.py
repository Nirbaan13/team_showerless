"""Narrow prospective retry of one immutable failed URL; metadata equivalence fails closed."""
from pathlib import Path
import argparse, datetime, email.utils, hashlib, json, time, types
from urllib.error import HTTPError

OWN=Path(__file__).resolve().parent
PREVIOUS=OWN.parent/'recovery-3'
RAW=Path('/tmp/spaceapps-association-native-recovery2/recovery-4')

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()
def ref(path):return dict(path=str(path.resolve()),sha256=sha(path))
def read(path):return json.loads(Path(path).read_text())
def write(path,value):
    if path.exists():raise ValueError('Evidence already exists: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def checked(item):
    p=Path(item['path']);assert sha(p)==item['sha256'],str(p);return p
def exact(name,item):
    p=checked(item);m=types.ModuleType(name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def declare():
    if (OWN/'transport-plan.json').exists()or RAW.exists():raise ValueError('New paths required')
    previous=read(PREVIOUS/'transport-plan.json');handoff=read(PREVIOUS/'guarded-handoff.json');audit=read(PREVIOUS/'byte-header-audit.json')
    failures=[r for r in audit['downloads']if r.get('error')];assert len(failures)==1
    item=failures[0];assert item['group_id']=='association-holdout-08'and item['obs_id']=='2025W47_1A_0738_4'and item['detector']==2
    assert handoff['counts']['physical_exposures']==79 and handoff['counts']['acquired_parents']==9
    start=datetime.datetime.now(datetime.timezone.utc)
    plan=dict(schema_version=1,declared_utc=start.isoformat(),deadline_utc=(start+datetime.timedelta(minutes=15)).isoformat(),wrapper=ref(Path(__file__)),
        root_authorization='Root authorized narrowly bounded15min continuation for exact failed08product and equivalent all-time05/09partitions only. Native inference unauthorized.',
        previous_handoff=ref(PREVIOUS/'guarded-handoff.json'),previous_audit=ref(PREVIOUS/'byte-header-audit.json'),previous_selection=ref(PREVIOUS/'selection.json'),previous_publication=ref(PREVIOUS/'publication-manifest.json'),
        original_plan=previous['original_plan'],native_seed_amendment=previous['native_seed_amendment'],scientific_amendment=ref(PREVIOUS/'transport-plan.json'),sources=previous['sources'],
        unchanged='Reuse all79existing source paths/hash/headers without requests; same12centers,411seedmap,438exclusions,R3footprint<=4degree prefilter and unchangeddetector/temporalalgorithm; no replacement; total96x5.2MB<500MB.',
        product=dict(failed_record=item,group_id=item['group_id'],obs_id=item['obs_id'],detector=2,url=item['url'],max_attempts=3,timeout_seconds=90,max_file_bytes=5200000,minimum_retry_backoff_seconds=10,respect_retry_after=True),
        metadata=dict(status='BLOCKED_EXACT_DOMAIN_EQUIVALENCE_UNPROVEN',network_requests_authorized_in_this_plan=0,
            requested_partition_boundary_utc='2025-10-01T00:00:00+00:00',requested_partition_boundary_mjd=60949.,requested_partitions=['-Inf 60949.0','60949.0 +Inf'],
            reason='SIA2section2.1 excludes null-time records when TIME is constrained, whereas unconstrained queries can return them. Original acquire.select sorts supported usable rows using float(t_min) with no null-time eligibility filter; a null t_min raises and rejects the field, rather than being ignored. Recovery3 only adds footprint prefilter. Therefore equivalence even of original field-selection behavior is unproven when TIME omits null rows; root conditional direction permits only exact08retry. No partition requests.',
            references=['https://www.ivoa.net/documents/SIA/20151223/REC-SIA-2.0-20151223.html','https://irsa.ipac.caltech.edu/ibe/sia.html']),
        raw_root=str(RAW),pixels_opened=False,models_called=False,injections_generated=False,inference_authorized=False)
    RAW.mkdir()
    for path in [OWN/'transport-plan.json',RAW/'transport-plan.json']:write(path,plan)
    print(json.dumps(dict(plan_sha256=sha(OWN/'transport-plan.json'),deadline_utc=plan['deadline_utc'],metadata_requests=0,product_urls=1,max_product_attempts=3)),flush=True)

def run():
    plan=read(OWN/'transport-plan.json');checked(plan['wrapper']);assert sha(OWN/'transport-plan.json')==sha(RAW/'transport-plan.json')
    for key in ['previous_handoff','previous_audit','previous_selection','previous_publication','original_plan','native_seed_amendment','scientific_amendment']:checked(plan[key])
    previous_audit=read(plan['previous_audit']['path']);manifest=read(plan['previous_publication']['path'])
    for item in manifest['raw_products']:
        p=checked(item);assert p.stat().st_size==item['bytes']
    helper=exact('exact_headeronly_transport',plan['sources']['holdout']);headers=exact('exact_manual_headers',plan['sources']['headers'])
    task=plan['product'];item=dict(task['failed_record']);item.pop('error');item.pop('status');item['path']=str(RAW/'quarantine'/item['group_id']/Path(item['path']).name)
    deadline=datetime.datetime.fromisoformat(plan['deadline_utc']).timestamp();attempts=[]
    for index in range(task['max_attempts']):
        record=dict(attempt=index+1,started_utc=utc(),url=task['url'])
        try:
            source=helper.fetch(task['url'],Path(item['path']),task['max_file_bytes'],90,1,deadline);record.update(status='TRANSFERRED',source=source);attempts.append(record)
            item.update(source);item['header']=headers.inspect(Path(item['path']),item['obs_id'],item['detector']);mid=item['header']['midpoint_mjd']
            assert item['t_min_mjd']-.000002<=mid<=item['t_max_mjd']+.000002
            item.update(midpoint_mjd=mid,midpoint_utc=datetime.datetime.fromtimestamp((mid-40587)*86400,datetime.timezone.utc).isoformat(),status='HEADER_VERIFIED_QUARANTINED');break
        except Exception as error:
            if record not in attempts:attempts.append(record)
            record.update(error=f'{type(error).__name__}: {error}',status='FAILED')
            cause=error
            while cause.__cause__ is not None:cause=cause.__cause__
            retry_after=cause.headers.get('Retry-After')if isinstance(cause,HTTPError)else None
            record['retry_after']=retry_after;delay=10.
            if retry_after:
                try:delay=max(delay,float(retry_after))
                except ValueError:
                    try:delay=max(delay,email.utils.parsedate_to_datetime(retry_after).timestamp()-time.time())
                    except Exception:record['retry_after_parse_error']=True
            if index+1==task['max_attempts']or time.time()+delay>=deadline:
                item.update(error=record['error'],status='PLANNED_MISSING_PRODUCT');break
            record['backoff_seconds']=delay;print(json.dumps(record),flush=True);time.sleep(delay)
    result=dict(status=item['status'],plan_ref=ref(OWN/'transport-plan.json'),attempts=attempts,product=item,reused_verified_files=79,metadata_requests=0,pixels_opened=False,models_called=False,injections_generated=False,inference_authorized=False)
    write(OWN/'fixed-product-retry.json',result);write(RAW/'fixed-product-retry.json',result)
    print(json.dumps(dict(status=result['status'],attempts=len(attempts),metadata_requests=0,obs_id=item['obs_id'],sha256=item.get('sha256'),bytes=item.get('bytes'))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['declare','run']);args=p.parse_args();declare()if args.command=='declare'else run()
