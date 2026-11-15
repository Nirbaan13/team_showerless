"""Second root-authorized original-artifact resource exception; exact global stored-byte budget."""
from pathlib import Path
import argparse,datetime,hashlib,json,types
OWN=Path(__file__).resolve().parent

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def ref(p):return dict(path=str(p.resolve()),sha256=sha(p))
def read(p):return json.loads(Path(p).read_text())
def checked(v):p=Path(v['path']);assert sha(p)==v['sha256'];return p
def exact(name,v):
    p=checked(v);m=types.ModuleType(name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
def write(p,v):
    if p.exists():raise ValueError('Immutable evidence exists: '+str(p))
    p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')

def declare():
    proof_record=read(OWN/'full-mef-05-head-size-proof.json');proof=proof_record['probe'];assert proof['method']=='HEAD'and proof['status']==200 and not proof['body_read'];size=int(next(v for k,v in proof['response_headers'].items()if k.lower()=='content-length'));assert size<=64*1024**2
    plan=read(OWN/'transport-plan.json');old=next(r for r in read(OWN/'byte-header-audit.json')['downloads']if r['obs_id']=='2026W14_1A_0529_1');assert old['detector']==1 and old.get('error');g=next(g for g in read(OWN/'selection.json')if g['group_id']=='association-holdout-05');row=next(r for r in g['exposures']if r['obs_id']==old['obs_id']);assert proof['url']==row['access_url']
    oldfiles=sorted(Path('/tmp/spaceapps-association-native-recovery2').rglob('*.fits'));total=sum(p.stat().st_size for p in oldfiles);assert len(oldfiles)==95 and total+size<=500000000
    amendment=dict(declared_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),root_authorization='Root explicitly authorized ONLY remaining05/D1originalartifact <=64MiB if concreteHEAD and actualglobalafterbothfullfiles<=500000000. SamephysicalID/processing/MJD/analysisROI; no substitution/pixelquality.',source=ref(Path(__file__)),original_plan=ref(OWN/'transport-plan.json'),previous_byte_audit=ref(OWN/'byte-header-audit.json'),previous09_resource=ref(OWN/'full-mef-resource-amendment.json'),logical_header_engineering=ref(OWN/'compressed-header-engineering-amendment.json'),logical_header_source=ref(OWN/'compressed_header_audit.py'),head_proof_ref=ref(OWN/'full-mef-05-head-size-proof.json'),head_size_proof=proof,obs_id=old['obs_id'],detector=1,full_source_url=row['access_url'],failed_cutout_url=old['url'],expected_bytes=size,max_this_file_bytes=64*1024**2,max_other_regular_file_bytes=5200000,max_total_bytes=500000000,preexisting_raw_files=[dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)for p in oldfiles],actual_preexisting_raw_bytes=total,projected_total_raw_bytes=total+size,max_GET_attempts=1,timeout_seconds=90,deadline_utc=plan['deadline_utc'],roi=plan['roi'],changed_transport='SameoriginalfullMEFwithoutcutoutquery; fullbytes/shapeexplicitlydifferent, NO byteparityclaimtofailedcutout; original503and5.2MBhistorypreserved.',pixels_opened=False,inference_authorized=False)
    write(OWN/'full-mef-05-resource-amendment.json',amendment);print(json.dumps(dict(amendment_sha256=sha(OWN/'full-mef-05-resource-amendment.json'),source_sha256=sha(Path(__file__)),expected_bytes=size,projected_total_raw_bytes=total+size)),flush=True)

def run():
    a=read(OWN/'full-mef-05-resource-amendment.json');checked(a['source']);checked(a['original_plan']);checked(a['previous_byte_audit']);checked(a['previous09_resource']);checked(a['logical_header_engineering']);checked(a['head_proof_ref']);logical=exact('full05_logical_headers',a['logical_header_source']);plan=read(a['original_plan']['path']);helper=exact('full05_opaque_fetch',plan['sources']['holdout'])
    for r in a['preexisting_raw_files']:checked(r)
    old=next(r for r in read(a['previous_byte_audit']['path'])['downloads']if r['obs_id']==a['obs_id']);item=dict(old);item.pop('error',None);item.pop('status',None);full=a['full_source_url'];path=Path(plan['raw_root'])/'full-mef'/item['group_id']/Path(full).name;item.update(url=full,source_url=full,requested_cutout_url=a['failed_cutout_url'],path=str(path),transfer_method='ORIGINAL_FULL_MEF_GET_SECOND_ARTIFACT_64MIB_EXCEPTION')
    try:
        deadline=datetime.datetime.fromisoformat(a['deadline_utc']).timestamp();item.update(helper.fetch(full,path,a['max_this_file_bytes'],90,1,deadline));assert item['bytes']==a['expected_bytes'];item['header']=logical.inspect(path,item['obs_id'],1,plan['sources']['headers']);mid=item['header']['midpoint_mjd'];assert item['t_min_mjd']-.000002<=mid<=item['t_max_mjd']+.000002;assert item['header']['wcs']['CTYPE1'].startswith('RA')and item['header']['wcs']['CTYPE2'].startswith('DEC')
        item.update(status='HEADER_VERIFIED_QUARANTINED',midpoint_mjd=mid,midpoint_utc=datetime.datetime.fromtimestamp((mid-40587)*86400,datetime.timezone.utc).isoformat(),processing_identity_evidence=dict(original_frozen_SIA_artifact_url=full,processing_version_path=Path(full).parent.parent.name,artifact_basename=Path(full).name,header_physical_id_and_detector_verified=True,header_midpoint_verified=True),full_vs_cutout_byte_parity_claim=False)
        assert sum(p.stat().st_size for p in Path('/tmp/spaceapps-association-native-recovery2').rglob('*.fits'))<=500000000
    except Exception as error:item.update(error=f'{type(error).__name__}: {error}',status='PLANNED_MISSING_PRODUCT')
    write(OWN/'full-mef-05-transfer.json',dict(status=item['status'],amendment_ref=ref(OWN/'full-mef-05-resource-amendment.json'),product=item,preserved_preexisting_raw_files=95,pixels_opened=False,inference_authorized=False));print(json.dumps(dict(status=item['status'],obs_id=item['obs_id'],bytes=item.get('bytes'),sha256=item.get('sha256'),shape=item.get('header',{}).get('native_shape'),error=item.get('error'))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['declare','run']);args=p.parse_args();globals()[args.command]()
