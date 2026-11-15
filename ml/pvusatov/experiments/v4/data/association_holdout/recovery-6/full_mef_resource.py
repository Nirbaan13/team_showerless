"""One-artifact root-authorized <=64MiB transport amendment; immutable ROI/physical identity."""
from pathlib import Path
import argparse,datetime,hashlib,json,math,types
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
    plan=read(OWN/'transport-plan.json');audit=read(OWN/'byte-header-audit.json');retry=next(r for r in read(OWN/'fixed09-retry.json')if r['obs_id']=='2025W38_2C_0439_2');selection=read(OWN/'selection.json');g=next(g for g in selection if g['group_id']=='association-holdout-09');row=next(r for r in g['exposures']if r['obs_id']==retry['obs_id']);proof=retry['full_MEF_fallback']['size_proof'];assert proof['status']==200 and proof['url']==row['access_url'];size=int(next(v for k,v in proof['response_headers'].items()if k.lower()=='content-length'));assert size==59123520 and size<=64*1024**2
    oldgood=[r for r in audit['downloads']if not r.get('error')];assert len(oldgood)==94
    for item in oldgood:checked(item)
    total=sum(r['bytes']for r in oldgood);assert total+size<=500000000
    amendment=dict(schema_version=1,declared_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),original_transport_plan=ref(OWN/'transport-plan.json'),source=ref(Path(__file__)),previous_byte_audit=ref(OWN/'byte-header-audit.json'),fixed_cutout_retry=ref(OWN/'fixed09-retry.json'),selection=ref(OWN/'selection.json'),
        root_authorization='Root explicitly authorized append-only resource exception ONLY for same09physicalOBSID2025W38_2C_0439_2/D3 originalfullartifact after concreteHEADproof. Otherfiles<=5.2MB/global<=500MB. No inference/pixels/quality authorized.',
        obs_id=row['obs_id'],group_id=g['group_id'],detector=3,original_full_artifact_url=row['access_url'],failed_cutout_url=retry['product']['url'],head_size_proof=proof,expected_full_bytes=size,max_full_file_bytes=64*1024**2,max_other_file_bytes=5200000,max_total_bytes=500000000,max_full_GET_attempts=1,timeout_seconds=90,deadline_utc=plan['deadline_utc'],
        old_verified_files=len(oldgood),old_verified_bytes=total,projected_total_raw_bytes=total+size,all_old_file_refs=[{k:r[k]for k in ['path','sha256','bytes','obs_id']}for r in oldgood],roi=plan['roi'],
        identity_constraints='SAMEselectedphysicalID,D3,originalSIAartifactprocessingversionpath/filename,headerMJDwithinsealedinterval,celestialRA/DECaxes; analysisROI6arcmin/6.15arcsec/motion/recenterfalseunchanged.',
        changed_transport='OriginalfullMEFwithoutcutoutquery; nativefullshapeandbytesdifferfromcutoutstrategy. NO byteparityclaimtofailedcutout. Failedcutoutandoriginal5.2MBdeclinepreservedhistorically.',pixels_opened=False,models_called=False,inference_authorized=False)
    write(OWN/'full-mef-resource-amendment.json',amendment);print(json.dumps(dict(amendment_sha256=sha(OWN/'full-mef-resource-amendment.json'),source_sha256=sha(Path(__file__)),same_artifact_url=row['access_url'],expected_bytes=size,projected_total_raw_bytes=total+size)),flush=True)

def run():
    amendment=read(OWN/'full-mef-resource-amendment.json');checked(amendment['source']);checked(amendment['original_transport_plan']);checked(amendment['previous_byte_audit']);checked(amendment['fixed_cutout_retry']);checked(amendment['selection'])
    for item in amendment['all_old_file_refs']:checked(item)
    plan=read(amendment['original_transport_plan']['path']);helper=exact('full_transport_only',plan['sources']['holdout']);headers=exact('full_manual_headers',plan['sources']['headers']);old=next(r for r in read(amendment['previous_byte_audit']['path'])['downloads']if r['obs_id']==amendment['obs_id']);item=dict(old);item.pop('error',None);item.pop('status',None)
    full=amendment['original_full_artifact_url'];path=Path(plan['raw_root'])/'full-mef'/item['group_id']/Path(full).name;item.update(url=full,source_url=full,requested_cutout_url=amendment['failed_cutout_url'],path=str(path),transfer_method='ORIGINAL_FULL_MEF_GET_ONE_ARTIFACT_64MIB_EXCEPTION')
    deadline=datetime.datetime.fromisoformat(amendment['deadline_utc']).timestamp()
    try:
        item.update(helper.fetch(full,path,amendment['max_full_file_bytes'],90,1,deadline));assert item['bytes']==amendment['expected_full_bytes'];item['header']=headers.inspect(path,amendment['obs_id'],3);mid=item['header']['midpoint_mjd'];assert item['t_min_mjd']-.000002<=mid<=item['t_max_mjd']+.000002
        wcs=item['header']['wcs'];assert wcs['CTYPE1'].startswith('RA')and wcs['CTYPE2'].startswith('DEC')and all(math.isfinite(float(wcs[k]))for k in ['CRVAL1','CRVAL2','CRPIX1','CRPIX2'])
        processing=Path(full).parent.parent.name;assert Path(full).name.endswith(processing+'.fits')
        item.update(midpoint_mjd=mid,midpoint_utc=datetime.datetime.fromtimestamp((mid-40587)*86400,datetime.timezone.utc).isoformat(),status='HEADER_VERIFIED_QUARANTINED',processing_identity_evidence=dict(original_frozen_SIA_artifact_url=full,processing_version_path=processing,artifact_basename=Path(full).name,header_physical_id_and_detector_verified=True,header_midpoint_verified=True),full_vs_cutout_byte_parity_claim=False)
    except Exception as error:item.update(error=f'{type(error).__name__}: {error}',status='PLANNED_MISSING_PRODUCT')
    result=dict(status=item['status'],amendment_ref=ref(OWN/'full-mef-resource-amendment.json'),product=item,preserved_old_files=94,pixels_opened=False,models_called=False,inference_authorized=False);write(OWN/'full-mef-transfer.json',result)
    print(json.dumps(dict(status=item['status'],obs_id=item['obs_id'],bytes=item.get('bytes'),sha256=item.get('sha256'),shape=item.get('header',{}).get('native_shape'),error=item.get('error'))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['declare','run']);args=p.parse_args();globals()[args.command]()
