"""Independent finite-time eligibility/partition/identity/manual-header replay; no science arrays."""
from pathlib import Path
from urllib.parse import parse_qs,urlsplit,urlencode
import copy,datetime,hashlib,json,math,types,xml.etree.ElementTree as ET
OWN=Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def ref(path):return dict(path=str(path.resolve()),sha256=sha(path))
def read(path):return json.loads(Path(path).read_text())
def checked(item):
    p=Path(item['path']);assert sha(p)==item['sha256'],str(p);return p
def exact(name,item):
    p=checked(item);m=types.ModuleType(name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
def write(path,value):
    if path.exists():raise ValueError('Evidence exists: '+str(path))
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def valid_time(row):
    try:
        low=float(row['t_min']);high=float(row['t_max'])
        return math.isfinite(low)and math.isfinite(high)and high>=low
    except (ValueError,TypeError,KeyError):return False

def main():
    plan=read(OWN/'amendment-plan.json');checked(plan['wrapper']);original=read(checked(plan['original_plan']));amendment=read(checked(plan['native_seed_amendment']));previous=read(checked(plan['previous_handoff']));oldselection=read(checked(plan['previous_selection']))
    checked(plan['previous_publication']);checked(plan['scientific_amendment_R3'])
    assert sha(OWN/'amendment-plan.json')==sha(Path(plan['raw_root'])/'amendment-plan.json')
    previous_guard=read(checked(previous['strict_guard_ref']));verifier=exact('replay_R4_guard',previous_guard['audit_source'])
    def compare(path,value):assert read(path)==value,'Prior guard replay differs: '+str(path)
    verifier.write=compare;verifier.main()
    modules={name:exact('guard5_'+name,item)for name,item in plan['sources'].items()};old=modules['acquire'];helper=modules['holdout'];headers=modules['headers']
    assert len(original['groups'])==12 and len(set(original['excluded_physical_obsids']))==438
    assert sorted(amendment['native_seed_reservation'].values())==list(range(4110001,4110013))
    cases=[({'t_min':'1','t_max':'1'},True),({'t_min':'1','t_max':'2'},True),({'t_min':'','t_max':'2'},False),({'t_min':'nan','t_max':'2'},False),({'t_min':'1','t_max':'inf'},False),({'t_min':'2','t_max':'1'},False),({},False)]
    assert all(valid_time(row)==expected for row,expected in cases)
    rows={};metadata=[];requests=0;original_by_id={g['group_id']:g for g in original['groups']}
    for identity,cached in plan['cached_metadata'].items():
        checked(cached['evidence']);d=read(checked(cached['discovery']));parsed,status=old.parse(checked(cached['source']));assert d['complete']and parsed==d['rows']
        values=[s.get('value')for s in status if s.get('name')=='QUERY_STATUS'];assert values and all(s=='OK'for s in values)
        rows[identity]=parsed;metadata.append(dict(group_id=identity,cached=True,source=cached))
    domains=read(OWN/'metadata-domains.json')
    for identity in plan['retry_group_ids']:
        union={};duplicates=0;allcomplete=True;parts=[]
        for part in plan['partitions']:
            evidence_path=OWN/'query-evidence'/f"{identity}-{part['name']}.json";evidence=read(evidence_path);record=read(checked(evidence['raw_record_ref']));assert record['partition']==part and record['center']==original_by_id[identity]['center']
            attempts=record['attempts'];assert 1<=len(attempts)<=2;requests+=len(attempts);complete=False;partrows=[];expected_limit=512
            for index,attempt in enumerate(attempts):
                assert attempt['number']==index+1 and attempt['limit']==expected_limit
                u=urlsplit(attempt['url']);params=parse_qs(u.query);center=original_by_id[identity]['center']
                assert u.netloc=='irsa.ipac.caltech.edu'and u.path=='/SIA'
                assert params==dict(POS=[f'CIRCLE {center[0]} {center[1]} 0.001'],COLLECTION=['spherex_dr1'],RESPONSEFORMAT=['VOTABLE'],MAXREC=[str(expected_limit)],TIME=[part['TIME']])
                if 'source'not in attempt:assert attempt.get('error');continue
                p=checked(attempt['source']);xml=ET.parse(p).getroot();fields=xml.findall('.//{*}TABLE/{*}FIELD');names=[f.attrib['name']for f in fields]
                assert len(names)==len(set(names))and{'obs_id','access_url','t_min','t_max','s_region','energy_bandpassname'}.issubset(names)
                assert all(len(row)==len(fields)for row in xml.findall('.//{*}TABLEDATA/{*}TR'))
                parsed,status=old.parse(p);assert status==attempt['status']and len(parsed)==attempt['row_count'];values=[s.get('value')for s in status if s.get('name')=='QUERY_STATUS']
                if values and all(s=='OK'for s in values):
                    assert index==len(attempts)-1 and record['complete'];complete=True;partrows=parsed;assert record['rows']==parsed
                    for row in parsed:
                        if valid_time(row):assert float(row['t_min'])<=60949. if part['name']=='through-boundary'else float(row['t_max'])>=60949.
                elif'OVERFLOW'in values:expected_limit=4096
                else:assert'ERROR'in values
            assert complete==record['complete'];allcomplete=allcomplete and complete
            parts.append(ref(evidence_path))
            if complete:
                for row in partrows:
                    key=(row['access_url'],helper.physical_id(row['obs_id']),row.get('energy_bandpassname'))
                    if key in union:assert union[key]==row;duplicates+=1
                    else:union[key]=row
        assert domains[identity]['complete']==allcomplete
        if allcomplete:
            assert domains[identity]['union_rows']==len(union)and domains[identity]['identical_boundary_duplicates']==duplicates;rows[identity]=list(union.values())
        metadata.append(dict(group_id=identity,cached=False,complete=allcomplete,partition_evidence=parts,unique_union_rows=len(union)if allcomplete else None,identical_boundary_duplicates=duplicates if allcomplete else None))
    assert requests<=8 and len(metadata)==12
    selection=read(OWN/'selection.json');oldbyid={g['group_id']:g for g in oldselection};excluded=set(original['excluded_physical_obsids']);parity=[]
    for declared,g in zip(original['groups'],selection):
        identity=declared['group_id'];assert g['group_id']==identity and g['seed']==amendment['native_seed_reservation'][identity]and g['center']==declared['center']
        eligible=[];counts=dict(input_rows=len(rows.get(identity,[])),unsupported=0,excluded=0,invalid_time=0,footprint=0,eligible=0)
        for row in rows.get(identity,[]):
            if row.get('energy_bandpassname')not in ['SPHEREx-D1','SPHEREx-D2','SPHEREx-D3']or'/dr1/'not in row.get('access_url',''):counts['unsupported']+=1;continue
            if helper.physical_id(row['obs_id'])in excluded:counts['excluded']+=1;continue
            if not valid_time(row):counts['invalid_time']+=1;continue
            if helper.footprint_radius(row['s_region'],declared['center'])>4:counts['footprint']+=1;continue
            eligible.append(row)
        counts['eligible']=len(eligible);assert g['eligibility_counts']==counts
        replay=old.select(dict(declared,seed=g['seed']),eligible,excluded)
        for key in ['detector','exposures','short_exposures','metadata_span_hours','metadata_window_hours','selection_tier']:
            if key in g:assert g[key]==replay[key]
        if identity in plan['cached_metadata']:
            before=[r['obs_id']for r in oldbyid[identity]['exposures']];after=[r['obs_id']for r in g['exposures']];assert before==after and not g.get('error')
            parity.append(dict(group_id=identity,ordered8_metadata_obs_ids=after,unchanged=True))
        if not g.get('error'):
            ids=[helper.physical_id(r['obs_id'])for r in g['exposures']];assert len(ids)==len(set(ids))==8 and not set(ids)&excluded
            assert all(valid_time(r)for r in g['exposures']);assert max(helper.footprint_radius(r['s_region'],g['center'])for r in g['exposures'])<=4;excluded.update(ids)
    assert len(selection)==12 and len(parity)==10
    proof_before=read(OWN/'cached-parity.json');assert proof_before['status']=='PASS_ALL10_SAME_ORDERED8_IDENTITIES'and proof_before['network_queries_before_parity']==0
    audit=read(OWN/'byte-header-audit.json');downloads=audit['downloads'];assert audit['reused_existing_files']==80 and audit['new_product_tasks']<=16
    previous_images={r['obs_id']:r for g in previous['planned_groups']for r in g['images']};assert len(previous_images)==80
    good=[];seen=set();new_count=0
    for item in downloads:
        if item['obs_id']in previous_images:assert item==previous_images[item['obs_id']]
        else:new_count+=1;assert item['group_id']in plan['retry_group_ids']
        group=next(g for g in selection if g['group_id']==item['group_id']);row=next(r for r in group['exposures']if helper.physical_id(r['obs_id'])==item['obs_id'])
        url=row['access_url']+'?'+urlencode(dict(center=','.join(map(str,group['center'])),size=.12));assert item['url']==item['source_url']==url
        if item.get('error'):continue
        p=checked(item);assert p.stat().st_size==item['bytes']<=5200000 and headers.inspect(p,item['obs_id'],group['detector'])==item['header']
        assert item['header']['header_only']and not item['header']['pixels_opened']and item['midpoint_mjd']==item['header']['midpoint_mjd']
        assert item['t_min_mjd']-.000002<=item['midpoint_mjd']<=item['t_max_mjd']+.000002
        assert item['midpoint_utc']==datetime.datetime.fromtimestamp((item['midpoint_mjd']-40587)*86400,datetime.timezone.utc).isoformat()and item['roi']==plan['roi']
        assert item['obs_id']not in seen and item['obs_id']not in original['excluded_physical_obsids'];seen.add(item['obs_id']);good.append(item)
    assert new_count==audit['new_product_tasks']and set(previous_images).issubset(seen)
    total=sum(r.get('bytes',0)for r in downloads);assert total<=500000000 and len(downloads)<=96
    planned=[]
    for g in selection:
        images=[r for r in good if r['group_id']==g['group_id']];complete=len(images)==8 and not g.get('error')
        entry={k:g[k]for k in ['group_id','parent_id','center','split','preferred_detector','stratum','seed']};entry.update(images=images,available=complete,status='COMPLETE_HEADER_VERIFIED_QUARANTINED'if complete else'PLANNED_MISSING')
        if 'detector'in g:entry['detector']=g['detector']
        if complete:
            for k in ['metadata_span_hours','metadata_window_hours','selection_tier','s_region_max_radius_deg']:entry[k]=g[k]
        else:entry['reason']=g.get('error','One or more fixed product transfers/manual-header checks failed; no replacement')
        planned.append(entry)
    groups=[g for g in planned if g['available']];ready=len(groups)==12 and len(good)==96
    counts=dict(planned_parents=12,acquired_parents=len(groups),physical_exposures=len(good),bytes=total)
    guard=dict(status='PASS_READY_QUARANTINE'if ready else'PASS_INCOMPLETE_QUARANTINE',strict_native_ready=ready,counts=counts,amendment_ref=ref(OWN/'amendment-plan.json'),cached_parity_ref=ref(OWN/'cached-parity.json'),cached10_identity_parity_after_union=parity,metadata_requests=requests,metadata_evidence=metadata,finite_validity_edge_cases_checked=len(cases),existing80_identical=True,unique_verified_physical_obsids=len(good),physical_exclusion_intersection=[],manual_headers_reverified=True,audit_source=ref(Path(__file__)),pixels_opened=False,models_called=False,injections_generated=False,inference_authorized=False)
    write(OWN/'strict-guard.json',guard)
    handoff=dict(schema_version=5,status='COMPLETE_HEADER_VERIFIED_QUARANTINED'if ready else'INCOMPLETE_PLANNED_MISSING',created_utc=read(OWN/'execution-state.json')['amendment_ref'] and plan['declared_utc'],evaluation_ready=ready,inference_authorized=False,injections_authorized=False,pixels_opened=False,models_called=False,groups=groups,planned_groups=planned,counts=counts,
        region_arcmin=[6,6],pixel_scale_arcsec=6.15,mask_policy='motion',excluded_physical_obsids=original['excluded_physical_obsids'],physical_and_spatial_proof=dict(previous['physical_and_spatial_proof'],acquired_unique_physical_obsids=len(good)),plan_ref=plan['original_plan'],seed_amendment_ref=plan['native_seed_amendment'],finite_time_amendment_ref=ref(OWN/'amendment-plan.json'),scientific_amendment=plan['scientific_amendment'],previous_R3_amendment_ref=plan['scientific_amendment_R3'],previous_handoff_ref=plan['previous_handoff'],selection_ref=ref(OWN/'selection.json'),byte_header_audit_ref=ref(OWN/'byte-header-audit.json'),strict_guard_ref=ref(OWN/'strict-guard.json'),source_refs=plan['sources'],metadata_evidence_refs=metadata,raw_roots=previous['raw_roots']+[plan['raw_root']],raw_root='/tmp/spaceapps-association-native-recovery2',no_coverage_claim=False,
        quarantine='No native inference or injections authorized. Root must independently review this exact external handoff digest and explicitly authorize native execution. Finite-valid-time eligible-domain coverage only; no unrestricted/null-time catalogue equivalence.')
    write(OWN/'guarded-handoff.json',handoff);print(json.dumps(dict(status=guard['status'],strict_native_ready=ready,counts=counts,metadata_requests=requests,handoff_sha256=sha(OWN/'guarded-handoff.json'))))

if __name__=='__main__':main()
