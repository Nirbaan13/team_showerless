"""Verify unchanged R3 provenance and exact product retry; merge a partial quarantined handoff."""
from pathlib import Path
import copy, datetime, hashlib, json, types
OWN=Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()
def ref(path):return dict(path=str(path.resolve()),sha256=sha(path))
def read(path):return json.loads(Path(path).read_text())
def checked(item):
    p=Path(item['path']);assert sha(p)==item['sha256'],str(p);return p
def exact(name,item):
    p=checked(item);m=types.ModuleType(name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
def write(path,value):
    if path.exists():raise ValueError('Evidence already exists: '+str(path))
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')

def main():
    plan=read(OWN/'transport-plan.json');checked(plan['wrapper']);previous=read(checked(plan['previous_handoff']));old_audit=read(checked(plan['previous_audit']));selection=read(checked(plan['previous_selection']))
    checked(plan['previous_publication']);checked(plan['original_plan']);checked(plan['native_seed_amendment']);checked(plan['scientific_amendment'])
    # Replay the complete existing R3 metadata/header guard without modifying its evidence.
    guard_path=Path(previous['strict_guard_ref']['path']);checked(previous['strict_guard_ref']);old_guard=read(guard_path)
    verifier=exact('replay_unchanged_R3_guard',old_guard['audit_source'])
    def compare(path,value):assert read(path)==value,'R3guard replay differs: '+str(path)
    verifier.write=compare;verifier.main()
    header=exact('r4_exact_manual_headers',plan['sources']['headers']);acquire=exact('r4_exact_selector',plan['sources']['acquire'])
    # A null supported-row time rejects the original field; it is not filtered away.
    row=dict(obs_id='null-time-behavior-proof',access_url='https://example.invalid/dr1/proof.fits',energy_bandpassname='SPHEREx-D1',t_min='',t_max='60000')
    try:acquire.select(dict(preferred_detector=1),[row],set())
    except ValueError as error:null_proof=dict(original_selector_raises='ValueError',error=str(error),null_row_filtered_before_selection=False)
    else:raise AssertionError('Original null-time behavior differs; partition gate requires review')
    assert plan['metadata']['network_requests_authorized_in_this_plan']==0
    retry=read(OWN/'fixed-product-retry.json');assert retry['metadata_requests']==0 and retry['reused_verified_files']==79
    assert 1<=len(retry['attempts'])<=3
    for index,attempt in enumerate(retry['attempts']):
        assert attempt['attempt']==index+1 and attempt['url']==plan['product']['url']
        if index+1<len(retry['attempts']):
            assert attempt['backoff_seconds']>=10
            if attempt.get('retry_after'):
                try:assert attempt['backoff_seconds']>=float(attempt['retry_after'])
                except ValueError:pass
    product=retry['product'];original=plan['product']['failed_record']
    for key in ['group_id','obs_id','physical_obsid','detector','url','source_url','metadata_obs_id','t_min_mjd','t_max_mjd','roi']:assert product[key]==original[key]
    merged=copy.deepcopy(previous);downloads=[r for r in old_audit['downloads']if not r.get('error')]
    assert len(downloads)==79
    success=not product.get('error')
    if success:
        p=checked(product);assert p.stat().st_size==product['bytes']<=5200000
        assert header.inspect(p,product['obs_id'],2)==product['header']
        assert product['midpoint_mjd']==product['header']['midpoint_mjd'] and product['t_min_mjd']-.000002<=product['midpoint_mjd']<=product['t_max_mjd']+.000002
        assert product['midpoint_utc']==datetime.datetime.fromtimestamp((product['midpoint_mjd']-40587)*86400,datetime.timezone.utc).isoformat()
        downloads.append(product)
    identifiers=[]
    for item in downloads:
        checked(item);assert header.inspect(item['path'],item['obs_id'],item['detector'])==item['header'];identifiers.append(item['obs_id'])
    assert len(identifiers)==len(set(identifiers)) and not set(identifiers)&set(merged['excluded_physical_obsids'])
    for group in merged['planned_groups']:
        if group['group_id']=='association-holdout-08'and success:
            group['images']=sorted(group['images']+[product],key=lambda r:(r['t_min_mjd'],r['obs_id']))
            group.update(available=True,status='COMPLETE_HEADER_VERIFIED_QUARANTINED');group.pop('reason',None)
            chosen=next(g for g in selection if g['group_id']==group['group_id'])
            assert {r['obs_id']for r in group['images']}=={r['obs_id']for r in chosen['exposures']}
            for key in ['metadata_span_hours','metadata_window_hours','selection_tier','s_region_max_radius_deg']:group[key]=chosen[key]
        if group['group_id']in ['association-holdout-05','association-holdout-09']:
            group['metadata_continuation_status']='BLOCKED_EXACT_SELECTION_BEHAVIOR_EQUIVALENCE_UNPROVEN';group['new_metadata_requests']=0
    merged['groups']=[g for g in merged['planned_groups']if g['available']]
    merged['counts']=dict(planned_parents=12,acquired_parents=len(merged['groups']),physical_exposures=len(downloads),bytes=sum(r['bytes']for r in downloads))
    assert len(downloads)<=96 and merged['counts']['bytes']<=500000000
    assert len(merged['groups'])==(10 if success else 9) and len(downloads)==(80 if success else 79)
    merged['evaluation_ready']=False;merged['inference_authorized']=False
    merged['status']='INCOMPLETE_PLANNED_MISSING';merged['continuation_plan_ref']=ref(OWN/'transport-plan.json');merged['product_retry_ref']=ref(OWN/'fixed-product-retry.json');merged['previous_handoff_ref']=plan['previous_handoff']
    merged['metadata_partition_gate']=dict(status='BLOCKED_EXACT_SELECTION_BEHAVIOR_EQUIVALENCE_UNPROVEN',network_queries=0,null_time_behavior=null_proof,standard_null_time_exclusion=True,references=plan['metadata']['references'])
    merged['raw_roots']=[previous['raw_root'],plan['raw_root']];merged['raw_root']='/tmp/spaceapps-association-native-recovery2'
    merged['physical_and_spatial_proof']=dict(merged['physical_and_spatial_proof'],acquired_unique_physical_obsids=len(downloads))
    audit=dict(downloads=downloads,pixels_opened=False,models_called=False,injections_generated=False,inference_authorized=False)
    write(OWN/'byte-header-audit.json',audit);merged['byte_header_audit_ref']=ref(OWN/'byte-header-audit.json')
    proof=dict(status='PASS_INCOMPLETE_QUARANTINE',strict_native_ready=False,counts=merged['counts'],prior_guard_replayed=True,all_existing79hashes_preserved=True,physical_exclusion_intersection=[],manual_headers_reverified=True,metadata_requests=0,null_time_behavior=null_proof,plan_ref=ref(OWN/'transport-plan.json'),product_retry_ref=ref(OWN/'fixed-product-retry.json'),audit_source=ref(Path(__file__)),pixels_opened=False,models_called=False,injections_generated=False,inference_authorized=False)
    write(OWN/'strict-guard.json',proof);merged['previous_strict_guard_ref']=merged['strict_guard_ref'];merged['strict_guard_ref']=ref(OWN/'strict-guard.json')
    write(OWN/'guarded-handoff.json',merged)
    print(json.dumps(dict(status=proof['status'],counts=merged['counts'],strict_native_ready=False,metadata_queries=0,handoff_sha256=sha(OWN/'guarded-handoff.json'))))

if __name__=='__main__':main()
