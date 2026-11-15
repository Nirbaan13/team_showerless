"""Replay unchanged R5 eligibility, refined interval union, exact artifact methods and manual headers."""
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,urlencode
import datetime,hashlib,json,math,types,xml.etree.ElementTree as ET
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
def valid(row):
    try:a=float(row['t_min']);b=float(row['t_max']);return math.isfinite(a)and math.isfinite(b)and b>=a
    except(ValueError,TypeError,KeyError):return False

def main():
    plan=read(OWN/'transport-plan.json');checked(plan['wrapper']);oldplan=read(checked(plan['R5_amendment']));previous=read(checked(plan['previous_handoff']));previous_selection=read(checked(plan['previous_selection']));checked(plan['previous_publication']);checked(plan['same_eligibility_engine'])
    assert sha(OWN/'transport-plan.json')==sha(Path(plan['raw_root'])/'transport-plan.json')
    previous_guard=read(checked(previous['strict_guard_ref']));prior=exact('fresh_R5_guard',previous_guard['audit_source'])
    def compare(p,v):assert read(p)==v,'Prior replay differs: '+str(p)
    prior.write=compare;prior.main()
    modules={k:exact('audit6_'+k,v)for k,v in plan['sources'].items()};helper=modules['holdout'];old=modules['acquire'];headers=modules['headers'];original=read(checked(oldplan['original_plan']));reservation=read(checked(oldplan['native_seed_amendment']))['native_seed_reservation']
    assert len(original['groups'])==12 and len(set(original['excluded_physical_obsids']))==438 and sorted(reservation.values())==list(range(4110001,4110013))
    rows={}
    for identity,cached in oldplan['cached_metadata'].items():
        d=read(checked(cached['discovery']));parsed,status=old.parse(checked(cached['source']));assert d['complete']and parsed==d['rows'];rows[identity]=parsed
    def cached_part(item):
        evidence=read(checked(item));record=read(checked(evidence['raw_record_ref']));assert record['complete'];parsed,status=old.parse(checked(record['attempts'][-1]['source']));assert parsed==record['rows'];values=[s.get('value')for s in status if s.get('name')=='QUERY_STATUS'];assert values and all(v=='OK'for v in values);return parsed
    def union(parts):
        result={};duplicates=0
        for part in parts:
            for row in part:
                key=(row['access_url'],helper.physical_id(row['obs_id']),row.get('energy_bandpassname'))
                if key in result:assert result[key]==row;duplicates+=1
                else:result[key]=row
        return list(result.values()),duplicates
    rows['association-holdout-09'],_=union([cached_part(i)for i in plan['cached_09_parts']]);right=cached_part(plan['cached_05_right']);assert len(right)==141
    records=[];requests=0;new05parts=[];allcomplete=True
    for part in plan['query']['partitions']:
        evidence_path=OWN/'query-evidence'/f"{part['name']}.json";evidence=read(evidence_path);record=read(checked(evidence['raw_record_ref']));assert record['partition']==part and record['group_id']=='association-holdout-05';attempts=record['attempts'];assert 1<=len(attempts)<=2;requests+=len(attempts);limit=512;complete=False;parsed=[]
        declared=next(g for g in original['groups']if g['group_id']==record['group_id']);assert record['center']==declared['center']
        for index,attempt in enumerate(attempts):
            assert attempt['number']==index+1 and attempt['limit']==limit;u=urlsplit(attempt['url']);center=declared['center'];assert u.netloc=='irsa.ipac.caltech.edu'and u.path=='/SIA'
            assert parse_qs(u.query)==dict(POS=[f'CIRCLE {center[0]} {center[1]} 0.001'],COLLECTION=['spherex_dr1'],RESPONSEFORMAT=['VOTABLE'],MAXREC=[str(limit)],TIME=[part['TIME']])
            if'source'not in attempt:assert attempt.get('error');continue
            p=checked(attempt['source']);xml=ET.parse(p).getroot();fields=xml.findall('.//{*}TABLE/{*}FIELD');names=[f.attrib['name']for f in fields];assert len(names)==len(set(names))and{'obs_id','access_url','t_min','t_max','s_region','energy_bandpassname'}.issubset(names);assert all(len(r)==len(fields)for r in xml.findall('.//{*}TABLEDATA/{*}TR'))
            candidate,status=old.parse(p);assert len(candidate)==attempt['row_count']and status==attempt['status'];values=[s.get('value')for s in status if s.get('name')=='QUERY_STATUS']
            if values and all(v=='OK'for v in values):
                assert index==len(attempts)-1 and record['complete'];complete=True;parsed=candidate;assert parsed==record['rows']
                for row in parsed:
                    if valid(row):assert float(row['t_min'])<=60827. if part['name']=='before-june'else float(row['t_min'])<=60949. and float(row['t_max'])>=60827.
            elif'OVERFLOW'in values:limit=4096
            else:assert'ERROR'in values
        assert complete==record['complete'];allcomplete=allcomplete and complete;records.append(ref(evidence_path));new05parts.append(parsed)
    assert requests<=4
    domain=read(OWN/'metadata-domain05.json');assert domain['complete']==allcomplete and domain['metadata_requests']==requests
    if allcomplete:
        rows['association-holdout-05'],duplicates=union(new05parts+[right]);assert domain['union_rows']==len(rows['association-holdout-05'])and domain['identical_boundary_duplicates']==duplicates
    selection=read(OWN/'selection.json');oldbyid={g['group_id']:g for g in previous_selection};excluded=set(original['excluded_physical_obsids']);targets=[]
    for declared,g in zip(original['groups'],selection):
        identity=declared['group_id'];assert g['group_id']==identity and g['center']==declared['center']and g['seed']==reservation[identity]
        eligible=[]
        for row in rows.get(identity,[]):
            if row.get('energy_bandpassname')not in ['SPHEREx-D1','SPHEREx-D2','SPHEREx-D3']or'/dr1/'not in row.get('access_url','')or helper.physical_id(row['obs_id'])in excluded or not valid(row):continue
            if helper.footprint_radius(row['s_region'],g['center'])<=4:eligible.append(row)
        replay=old.select(dict(declared,seed=g['seed']),eligible,excluded)
        for key in ['detector','exposures','short_exposures','metadata_span_hours','metadata_window_hours','selection_tier']:
            if key in g:assert g[key]==replay[key]
        if identity!='association-holdout-05':assert not g.get('error')and[r['obs_id']for r in g['exposures']]==[r['obs_id']for r in oldbyid[identity]['exposures']]
        if not g.get('error'):
            ids=[helper.physical_id(r['obs_id'])for r in g['exposures']];assert len(ids)==len(set(ids))==8 and not set(ids)&excluded;excluded.update(ids)
            targets.extend(dict(group_id=identity,obs_id=helper.physical_id(r['obs_id']),detector=g['detector'],artifact_url=r['access_url'],cutout_url=r['access_url']+'?'+urlencode(dict(center=','.join(map(str,g['center'])),size=.12)))for r in g['exposures'])
    assert len(selection)==12 and len({t['obs_id']for t in targets})==len(targets)
    parity=read(OWN/'cached11-parity.json');assert parity['status']=='PASS_ALL11_SAME_ORDERED8_IDENTITIES'and len(parity['groups'])==11 and parity['network_requests_before_parity']==0
    retry=read(OWN/'fixed09-retry.json');assert{r['obs_id']for r in retry}=={r['obs_id']for r in plan['missing_09_products']}
    for r in retry:
        target=next(t for t in targets if t['obs_id']==r['obs_id']);assert r['diagnostic']['url']==target['cutout_url']and r['diagnostic']['method']=='HEAD';assert 1<=len(r['cutout_attempts'])<=2
        for attempt in r['cutout_attempts']:
            assert attempt['url']==target['cutout_url']and attempt['backoff_seconds']>=10
            value=next((v for k,v in attempt.get('response_headers',{}).items()if k.lower()=='retry-after'),None)
            if value:
                try:assert attempt['backoff_seconds']>=float(value)
                except ValueError:pass
        fallback=r['full_MEF_fallback']
        if fallback:
            assert fallback['full_source_url']==target['artifact_url'];proof=fallback['size_proof'];assert proof['url']==target['artifact_url'];hs={k.lower():v for k,v in proof.get('response_headers',{}).items()}
            if proof.get('status')==200 and hs.get('content-length','').isdigit():assert fallback['proven_full_bytes']==int(hs['content-length'])
            assert not fallback['eligible'],'Pending eligible full-MEF proposal requires separate transfer and audit amendment'
            assert fallback['status']=='STOP_OVERSIZE_OR_UNKNOWN_NO_FULL_TRANSFER'and(fallback['proven_full_bytes']is None or fallback['proven_full_bytes']>5200000)
    state=read(OWN/'execution-state.json');assert not state['pending_full_MEF_proposals']
    audit=read(OWN/'byte-header-audit.json');downloads=audit['downloads'];assert audit['reused_existing_files']==86 and audit['new_product_tasks']<=10
    previous_images={r['obs_id']:r for g in previous['planned_groups']for r in g['images']};assert len(previous_images)==86;good=[];seen=set();source_methods=[]
    for item in downloads:
        if item['obs_id']in previous_images:assert item==previous_images[item['obs_id']]
        target=next(t for t in targets if t['obs_id']==item['obs_id']);assert item['url']==item['source_url']==target['cutout_url']
        method=item.get('transfer_method','EXISTING_FIXED_CUTOUT_GET');source_methods.append(dict(obs_id=item['obs_id'],source_url=item['source_url'],transfer_method=method,sha256=item.get('sha256'),missing=bool(item.get('error'))))
        if item.get('error'):continue
        p=checked(item);assert p.stat().st_size==item['bytes']<=5200000 and headers.inspect(p,item['obs_id'],item['detector'])==item['header'];assert item['detector']==target['detector']
        assert item['midpoint_mjd']==item['header']['midpoint_mjd']and item['t_min_mjd']-.000002<=item['midpoint_mjd']<=item['t_max_mjd']+.000002
        assert item['midpoint_utc']==datetime.datetime.fromtimestamp((item['midpoint_mjd']-40587)*86400,datetime.timezone.utc).isoformat()and item['roi']==plan['roi']
        assert item['obs_id']not in seen and item['obs_id']not in original['excluded_physical_obsids'];seen.add(item['obs_id']);good.append(item)
    assert set(previous_images).issubset(seen);total=sum(r.get('bytes',0)for r in downloads);assert total<=500000000 and len(downloads)<=96
    planned=[]
    for g in selection:
        images=[r for r in good if r['group_id']==g['group_id']];available=len(images)==8 and not g.get('error');entry={k:g[k]for k in ['group_id','parent_id','center','split','preferred_detector','stratum','seed']};entry.update(images=images,available=available,status='COMPLETE_HEADER_VERIFIED_QUARANTINED'if available else'PLANNED_MISSING')
        if'detector'in g:entry['detector']=g['detector']
        if available:
            for k in ['metadata_span_hours','metadata_window_hours','selection_tier','s_region_max_radius_deg']:entry[k]=g[k]
        else:entry['reason']=g.get('error','Fixed product unavailable under predeclared transfer/size caps; no substitution')
        planned.append(entry)
    groups=[g for g in planned if g['available']];ready=len(groups)==12 and len(good)==96;counts=dict(planned_parents=12,acquired_parents=len(groups),physical_exposures=len(good),bytes=total)
    guard=dict(status='PASS_READY_QUARANTINE'if ready else'PASS_INCOMPLETE_QUARANTINE',strict_native_ready=ready,counts=counts,plan_ref=ref(OWN/'transport-plan.json'),prior_R5_guard_replayed=True,cached11_metadata_id_parity=True,existing86_record_and_hash_parity=True,known_planned_target_count=len(targets),target_ledger=targets,transfer_provenance=source_methods,metadata_requests=requests,metadata_evidence=records,manual_headers_reverified=True,physical_exclusion_intersection=[],full_MEF_transfer_performed=False,audit_source=ref(Path(__file__)),pixels_opened=False,models_called=False,inference_authorized=False)
    write(OWN/'strict-guard.json',guard)
    handoff=dict(schema_version=6,status='COMPLETE_HEADER_VERIFIED_QUARANTINED'if ready else'INCOMPLETE_PLANNED_MISSING',created_utc=plan['declared_utc'],evaluation_ready=ready,inference_authorized=False,injections_authorized=False,pixels_opened=False,models_called=False,groups=groups,planned_groups=planned,counts=counts,region_arcmin=[6,6],pixel_scale_arcsec=6.15,mask_policy='motion',excluded_physical_obsids=original['excluded_physical_obsids'],physical_and_spatial_proof=dict(previous['physical_and_spatial_proof'],acquired_unique_physical_obsids=len(good)),plan_ref=oldplan['original_plan'],seed_amendment_ref=oldplan['native_seed_amendment'],finite_time_amendment_ref=plan['R5_amendment'],transport_refinement_ref=ref(OWN/'transport-plan.json'),scientific_amendment=previous['scientific_amendment'],previous_handoff_ref=plan['previous_handoff'],selection_ref=ref(OWN/'selection.json'),byte_header_audit_ref=ref(OWN/'byte-header-audit.json'),strict_guard_ref=ref(OWN/'strict-guard.json'),source_refs=plan['sources'],target_ledger=targets,transfer_provenance=source_methods,raw_roots=previous['raw_roots']+[plan['raw_root']],raw_root='/tmp/spaceapps-association-native-recovery2',no_coverage_claim=False,quarantine='Native inference/injections unauthorized until exact external handoff release and independent root review. Same R5 finite-valid-time eligible domain; no unrestricted null-time catalog claim or failed-cutout/full-MEF byte-parity claim.')
    write(OWN/'guarded-handoff.json',handoff);print(json.dumps(dict(status=guard['status'],strict_native_ready=ready,counts=counts,known_targets=len(targets),metadata_requests=requests,handoff_sha256=sha(OWN/'guarded-handoff.json'))))

if __name__=='__main__':main()
