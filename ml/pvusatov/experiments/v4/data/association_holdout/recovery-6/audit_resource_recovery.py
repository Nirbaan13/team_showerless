"""Append-only two exact-artifact resource exceptions and logical compressed-header replay."""
from pathlib import Path
import copy,datetime,hashlib,json,math,types
OWN=Path(__file__).resolve().parent

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def ref(p):return dict(path=str(p.resolve()),sha256=sha(p))
def read(p):return json.loads(Path(p).read_text())
def checked(v):p=Path(v['path']);assert sha(p)==v['sha256'],str(p);return p
def exact(name,v):
    p=checked(v);m=types.ModuleType(name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
def write(p,v):
    if p.exists():raise ValueError('Immutable evidence exists: '+str(p))
    p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')

def main():
    initial=read(OWN/'guarded-handoff.json');initial_guard=read(checked(initial['strict_guard_ref']));verifier=exact('initial_R6_guard_replay',initial_guard['audit_source'])
    def compare(p,v):assert read(p)==v,'Initial R6 replay differs: '+str(p)
    verifier.write=compare;verifier.main()
    plan=read(OWN/'transport-plan.json');oldaudit=read(OWN/'byte-header-audit.json');oldgood={r['obs_id']:r for r in oldaudit['downloads']if not r.get('error')};assert len(oldgood)==94
    engineering=read(OWN/'compressed-header-engineering-amendment.json');logical=exact('logical_compressed_header_auditor',engineering['source']);checked(engineering['original_header_source']);checked(engineering['historical_failed_header_audit']);assert engineering['artifact_sha256']==read(OWN/'full-mef-transfer.json')['product']['sha256']
    headers=exact('unchanged_regular_header_auditor',plan['sources']['headers']);a09=read(OWN/'full-mef-resource-amendment.json');a05=read(OWN/'full-mef-05-resource-amendment.json')
    checked(a09['source']);checked(a09['original_transport_plan']);checked(a09['previous_byte_audit']);checked(a09['fixed_cutout_retry']);checked(a09['selection'])
    for item in a09['all_old_file_refs']:checked(item);assert oldgood[item['obs_id']]['path']==item['path']and oldgood[item['obs_id']]['sha256']==item['sha256']
    assert len(a09['all_old_file_refs'])==94 and a09['max_full_file_bytes']==64*1024**2 and a09['max_other_file_bytes']==5200000 and a09['max_total_bytes']==500000000
    for key in ['source','original_plan','previous_byte_audit','previous09_resource','logical_header_engineering','logical_header_source','head_proof_ref']:checked(a05[key])
    assert len(a05['preexisting_raw_files'])==95 and a05['max_this_file_bytes']==64*1024**2 and a05['max_other_regular_file_bytes']==5200000 and a05['max_total_bytes']==500000000
    for item in a05['preexisting_raw_files']:checked(item)
    verified09=read(OWN/'full-mef-logical-header-verification.json');assert verified09['engineering_amendment_ref']['sha256']==sha(OWN/'compressed-header-engineering-amendment.json')
    result05=read(OWN/'full-mef-05-transfer.json');assert result05['amendment_ref']['sha256']==sha(OWN/'full-mef-05-resource-amendment.json')and result05['preserved_preexisting_raw_files']==95
    items=[verified09['product'],result05['product']];exceptions={'2025W38_2C_0439_2':(a09,3),'2026W14_1A_0529_1':(a05,1)};assert{r['obs_id']for r in items}==set(exceptions)
    for item in items:
        amendment,detector=exceptions[item['obs_id']];target=next(t for t in initial['target_ledger']if t['obs_id']==item['obs_id']);proof=amendment.get('head_size_proof');full=amendment.get('original_full_artifact_url',amendment.get('full_source_url'));failed_cutout=amendment.get('failed_cutout_url')
        assert proof['status']==200 and proof['method']=='HEAD'and not proof['body_read']and proof['url']==full==target['artifact_url'];hs={k.lower():v for k,v in proof['response_headers'].items()};expected=int(hs['content-length']);assert expected<=64*1024**2
        assert item['url']==item['source_url']==full and item['requested_cutout_url']==failed_cutout==target['cutout_url']and item['detector']==detector==target['detector']
        assert not item.get('error');p=checked(item);assert p.stat().st_size==item['bytes']==expected
        report=logical.inspect(p,item['obs_id'],detector,plan['sources']['headers']);assert report==item['header'];assert report['native_shape']==[2040,2040]and report['compressed_image_header_evidence']
        for h in report['compressed_image_header_evidence']:assert h['name']=='FLAGS'and h['logical_image_dimensions']==[2040,2040]and h['ZIMAGE']and h['ZBITPIX']==32 and h['ZCMPTYPE']=='RICE_1'
        wcs=report['wcs'];assert wcs['CTYPE1'].startswith('RA')and wcs['CTYPE2'].startswith('DEC')and all(math.isfinite(float(wcs[k]))for k in ['CRVAL1','CRVAL2','CRPIX1','CRPIX2'])
        assert item['midpoint_mjd']==report['midpoint_mjd']and item['t_min_mjd']-.000002<=item['midpoint_mjd']<=item['t_max_mjd']+.000002
        assert item['midpoint_utc']==datetime.datetime.fromtimestamp((item['midpoint_mjd']-40587)*86400,datetime.timezone.utc).isoformat()and item['roi']==plan['roi']and not item['full_vs_cutout_byte_parity_claim']
        processing=Path(full).parent.parent.name;assert Path(full).name.endswith(processing+'.fits')and item['processing_identity_evidence']['processing_version_path']==processing
    byid={r['obs_id']:r for r in items};downloads=[byid.get(r['obs_id'],r)for r in oldaudit['downloads']];assert len(downloads)==96
    for item in downloads:
        checked(item);assert item['bytes']<=(64*1024**2 if item['obs_id']in exceptions else 5200000)
        if item['obs_id']in oldgood:assert item==oldgood[item['obs_id']]and headers.inspect(item['path'],item['obs_id'],item['detector'])==item['header']
    ids=[r['obs_id']for r in downloads];target_ids=[t['obs_id']for t in initial['target_ledger']];assert len(ids)==len(set(ids))==len(target_ids)==len(set(target_ids))==96 and set(ids)==set(target_ids)and not set(ids)&set(initial['excluded_physical_obsids'])
    root=Path(initial['raw_root']);rawfiles=sorted(root.rglob('*.fits'));assert len(rawfiles)==96 and not list(root.rglob('*.part'))and{str(p)for p in rawfiles}=={r['path']for r in downloads}
    actual_bytes=sum(p.stat().st_size for p in rawfiles);assert actual_bytes==sum(r['bytes']for r in downloads)==a05['projected_total_raw_bytes']<=500000000
    handoff=copy.deepcopy(initial);selection={g['group_id']:g for g in read(OWN/'selection.json')}
    for group in handoff['planned_groups']:
        extra=[r for r in items if r['group_id']==group['group_id']];group['images']=sorted(group['images']+extra,key=lambda r:(r['t_min_mjd'],r['obs_id']));assert len(group['images'])==8
        group.update(available=True,status='COMPLETE_HEADER_VERIFIED_QUARANTINED');group.pop('reason',None)
        for key in ['metadata_span_hours','metadata_window_hours','selection_tier','s_region_max_radius_deg']:group[key]=selection[group['group_id']][key]
    counts=dict(planned_parents=12,acquired_parents=12,physical_exposures=96,bytes=actual_bytes)
    write(OWN/'byte-header-audit-resource.json',dict(downloads=downloads,resource_amendment_refs=[ref(OWN/'full-mef-resource-amendment.json'),ref(OWN/'full-mef-05-resource-amendment.json')],compressed_header_engineering_ref=ref(OWN/'compressed-header-engineering-amendment.json'),actual_raw_file_count=96,actual_raw_bytes=actual_bytes,pixels_opened=False,models_called=False,inference_authorized=False))
    guard=dict(status='PASS_READY_QUARANTINE',strict_native_ready=True,counts=counts,actual_raw_file_count=96,actual_raw_bytes=actual_bytes,remaining_stored_FITS_budget_bytes=500000000-actual_bytes,initial_R6_capsule_replayed=True,all_old94_records_and_hashes_identical=True,pre05_all95_file_hashes_identical=True,known_original_selected_targets=96,unique_physical_observations=96,physical_exclusion_intersection=[],artifact_64MiB_exceptions=sorted(exceptions),all_other_files_max_bytes=5200000,resource_amendment_refs=[ref(OWN/'full-mef-resource-amendment.json'),ref(OWN/'full-mef-05-resource-amendment.json')],compressed_header_engineering_ref=ref(OWN/'compressed-header-engineering-amendment.json'),manual_headers_reverified=True,unchanged_analysis_roi=plan['roi'],full_cutout_byte_parity_claim=False,audit_source=ref(Path(__file__)),pixels_opened=False,models_called=False,injections_generated=False,inference_authorized=False)
    write(OWN/'strict-resource-guard.json',guard);handoff.update(status='COMPLETE_HEADER_VERIFIED_QUARANTINED',groups=handoff['planned_groups'],counts=counts,evaluation_ready=True,inference_authorized=False,initial_transport_handoff_ref=ref(OWN/'guarded-handoff.json'),resource_amendment_refs=guard['resource_amendment_refs'],compressed_header_engineering_ref=guard['compressed_header_engineering_ref'],strict_guard_ref=ref(OWN/'strict-resource-guard.json'),initial_strict_guard_ref=initial['strict_guard_ref'],byte_header_audit_ref=ref(OWN/'byte-header-audit-resource.json'))
    handoff['physical_and_spatial_proof']['acquired_unique_physical_obsids']=96
    handoff['transfer_provenance']=[dict(r,source_url=byid[r['obs_id']]['source_url'],requested_cutout_url=byid[r['obs_id']]['requested_cutout_url'],transfer_method=byid[r['obs_id']]['transfer_method'],sha256=byid[r['obs_id']]['sha256'],missing=False)if r['obs_id']in byid else r for r in handoff['transfer_provenance']]
    write(OWN/'guarded-resource-handoff.json',handoff);print(json.dumps(dict(status=guard['status'],strict_native_ready=True,counts=counts,actual_raw_bytes=actual_bytes,resource_handoff_sha256=sha(OWN/'guarded-resource-handoff.json'))))

if __name__=='__main__':main()
