"""Replay metadata selection and header-only integrity; never open science arrays."""
from pathlib import Path
import datetime, hashlib, json, types, xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlsplit, urlencode

OWN=Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()
def ref(path):return dict(path=str(path.resolve()),sha256=sha(path))
def read(path):return json.loads(Path(path).read_text())
def write(path,value):
    if path.exists():raise ValueError('Refusing to overwrite audit/publication evidence: '+str(path))
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def checked(item):
    path=Path(item['path']);assert sha(path)==item['sha256'],str(path)
    return path

def main():
    retry=read(OWN/'transport-plan.json');original=read(checked(retry['original_plan']));amendment=read(checked(retry['native_seed_amendment']))
    checked(retry['association_freeze']);checked(retry['original_closed_handoff']);checked(retry['wrapper'])
    modules={}
    for name,item in retry['sources'].items():
        path=checked(item);module=types.ModuleType('audit_'+name);module.__file__=str(path)
        exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__);modules[name]=module
    old=modules['acquire'];helper=modules['holdout'];headers=modules['headers'];raw=Path(retry['quarantine']['raw_root'])
    assert sha(OWN/'transport-plan.json')==sha(raw/'transport-plan.json')
    for relative,digest in original['sources'].items():assert sha(OWN.parent.parent/relative)==digest
    assert len(original['groups'])==12 and len(set(original['excluded_physical_obsids']))==438
    assert sorted(amendment['native_seed_reservation'].values())==list(range(4110001,4110013))
    selection=read(OWN/'selection.json');assert sha(OWN/'selection.json')==sha(raw/'selection.json')
    assert [g['group_id']for g in selection]==[g['group_id']for g in original['groups']]
    excluded=set(original['excluded_physical_obsids']);metadata=[];successful=[]
    for declared,selected in zip(original['groups'],selection):
        identity=declared['group_id'];evidence_path=OWN/'query-evidence'/f'{identity}.json';evidence=read(evidence_path);discovery=read(checked(evidence['rows_ref']))
        assert evidence['center']==declared['center']==discovery['center'] and evidence['group_id']==identity
        assert len(discovery['attempts'])in(1,2)
        complete=False;rows=[]
        for index,attempt in enumerate(discovery['attempts']):
            params=parse_qs(urlsplit(attempt['url']).query)
            expected=dict(POS=[f"CIRCLE {declared['center'][0]} {declared['center'][1]} 0.001"],COLLECTION=['spherex_dr1'],RESPONSEFORMAT=['VOTABLE'],MAXREC=[str([512,4096][index])])
            assert params==expected and urlsplit(attempt['url']).netloc=='irsa.ipac.caltech.edu' and urlsplit(attempt['url']).path=='/SIA'
            if 'source'not in attempt:
                assert attempt.get('error') and not discovery['complete'];continue
            xml_path=checked(attempt['source']);root=ET.parse(xml_path).getroot()
            fields=root.findall('.//{*}TABLE/{*}FIELD');names=[f.attrib['name']for f in fields]
            assert len(names)==len(set(names)) and {'obs_id','access_url','t_min','t_max','s_region','energy_bandpassname'}.issubset(names)
            xmlrows=root.findall('.//{*}TABLEDATA/{*}TR')
            assert all(len(row)==len(fields)for row in xmlrows)
            parsed,status=old.parse(xml_path);assert len(parsed)==attempt['row_count'] and status==attempt['status']
            values=[s.get('value')for s in status if s.get('name')=='QUERY_STATUS']
            if values and all(s=='OK'for s in values):
                assert index==len(discovery['attempts'])-1 and discovery['complete'];complete=True;rows=parsed
                assert discovery['rows']==parsed
            else:
                assert 'OVERFLOW'in values or 'ERROR'in values
                if index==0 and len(discovery['attempts'])==2:assert 'OVERFLOW'in values
        assert complete==discovery['complete']==selected['metadata_complete']
        assert selected['seed']==amendment['native_seed_reservation'][identity] and selected['center']==declared['center']
        if complete:
            eligible=[r for r in rows if helper.physical_id(r['obs_id'])not in excluded]
            replay=old.select(dict(declared,seed=selected['seed']),eligible,excluded)
            for key in ['detector','exposures','short_exposures','metadata_span_hours','metadata_window_hours','selection_tier']:
                if key in selected:assert selected[key]==replay[key]
            if not selected.get('error'):
                ids=[helper.physical_id(r['obs_id'])for r in selected['exposures']]
                assert len(ids)==len(set(ids))==8 and not set(ids)&excluded
                assert max(helper.footprint_radius(r['s_region'],declared['center'])for r in selected['exposures'])<=4
                excluded.update(ids);successful.append(identity)
        else:assert selected.get('error') and not selected.get('exposures')
        metadata.append(dict(group_id=identity,complete=complete,evidence=ref(evidence_path),discovery=evidence['rows_ref']))
    handoff=read(OWN/'quarantined-handoff.json');downloads=read(OWN/'byte-header-audit.json')['downloads']
    assert len(downloads)<=96 and sum(r.get('bytes',0)for r in downloads)<=500000000
    ids=[];verified=[]
    for item in downloads:
        group=next(g for g in selection if g['group_id']==item['group_id'])
        exposure=next(r for r in group['exposures']if helper.physical_id(r['obs_id'])==item['obs_id'])
        expected_url=exposure['access_url']+'?'+urlencode(dict(center=','.join(map(str,group['center'])),size=.12))
        assert item['url']==item['source_url']==expected_url
        if item.get('error'):continue
        path=Path(item['path']);assert path.is_relative_to(raw/'quarantine') and path.stat().st_size==item['bytes']<=5200000
        assert sha(path)==item['sha256'];assert headers.inspect(path,item['obs_id'],group['detector'])==item['header']
        assert item['midpoint_mjd']==item['header']['midpoint_mjd'] and item['header']['header_only'] and not item['header']['pixels_opened']
        assert item['t_min_mjd']-.000002<=item['midpoint_mjd']<=item['t_max_mjd']+.000002
        timestamp=datetime.datetime.fromtimestamp((item['midpoint_mjd']-40587)*86400,datetime.timezone.utc).isoformat()
        assert item['midpoint_utc']==timestamp and item['roi']==retry['roi']
        ids.append(item['obs_id']);verified.append(item)
    assert len(ids)==len(set(ids)) and not set(ids)&set(original['excluded_physical_obsids'])
    assert len(handoff['planned_groups'])==12 and [g['group_id']for g in handoff['planned_groups']]==[g['group_id']for g in original['groups']]
    for group in handoff['planned_groups']:
        images=[r for r in verified if r['group_id']==group['group_id']]
        assert images==group['images'];assert group['available']==(len(images)==8 and group['group_id']in successful)
    ready=len(handoff['groups'])==12 and len(ids)==96
    assert handoff['evaluation_ready']==ready and not handoff['inference_authorized'] and not handoff['pixels_opened'] and not handoff['models_called']
    assert handoff['counts']==dict(planned_parents=12,acquired_parents=len(handoff['groups']),physical_exposures=len(ids),bytes=sum(r.get('bytes',0)for r in downloads))
    assert handoff['physical_and_spatial_proof']['minimum_distance_deg']>=8.5
    proof=dict(status='PASS_READY_QUARANTINE'if ready else'PASS_INCOMPLETE_QUARANTINE',strict_native_ready=ready,counts=handoff['counts'],metadata_complete_parents=sum(m['complete']for m in metadata),metadata_selected_parents=len(successful),metadata_evidence=metadata,
        input_handoff=ref(OWN/'quarantined-handoff.json'),transport_plan=ref(OWN/'transport-plan.json'),audit_source=ref(Path(__file__)),physical_exclusion_intersection=[],unique_verified_physical_obsids=len(ids),
        selection_replayed=True,manual_headers_reverified=True,pixels_opened=False,models_called=False,injections_generated=False,inference_authorized=False,no_coverage_claim=False)
    write(OWN/'strict-guard.json',proof)
    final=dict(handoff,strict_guard_ref=ref(OWN/'strict-guard.json'),metadata_evidence_refs=metadata,preliminary_handoff_ref=ref(OWN/'quarantined-handoff.json'))
    write(OWN/'guarded-handoff.json',final)
    print(json.dumps(dict(guard=proof['status'],strict_native_ready=ready,counts=handoff['counts'],handoff_sha256=sha(OWN/'guarded-handoff.json'))))

if __name__=='__main__':main()
