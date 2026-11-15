"""Byte/header-only V4 audit and incremental development-only handoff."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
from acquire import ROOT,OWN,digest,write
from headers import inspect

def main():
    plan=json.loads((OWN/'partition-plan.json').read_text());selected=json.loads((OWN/'selected-groups.json').read_text())
    seen={obs:'V3_or_legacy'for obs in plan['excluded_physical_obsids']};ready=[];final=[];pending=[]
    for group in selected:
        parent=group['parent_id']
        for exposure in group.get('exposures',[]):
            if exposure['obs_id']in seen:raise ValueError('Cross-parent/split physical OBSID leakage: '+exposure['obs_id'])
            seen[exposure['obs_id']]=parent
        directory=ROOT/('quarantine_final'if group['split']=='final'else'development')/parent
        path=directory/'downloads.json'
        if not(directory/'group.json').exists():pending.append(parent);continue
        data=json.loads(path.read_text())
        if len(data)!=len(group.get('exposures',[])):pending.append(parent);continue
        header_records=[]
        for row in data:
            p=Path(row['path'])
            if digest(p)!=row['sha256']or p.stat().st_size!=row['bytes']:raise ValueError('Observation hash/size mismatch')
            header_records.append(inspect(p,row['obs_id'],row['detector']))
        destination=OWN/'manifests'/('quarantine_final'if group['split']=='final'else'development')/(parent+'-downloads.json')
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():
            if digest(destination)!=digest(path):raise ValueError('Published download manifest changed')
        else:destination.write_bytes(path.read_bytes())
        record=dict(parent_id=parent,group_id=parent,split=group['split'],stratum=group['stratum'],center=group['center'],center_deg=group['center'],detector=group['detector'],
            native_epochs=len(data),physical_obsids=[r['obs_id']for r in data],metadata_span_hours=group['metadata_span_hours'],
            physical_midpoint_span_hours=(max(r['midpoint_mjd']for r in header_records)-min(r['midpoint_mjd']for r in header_records))*24,
            directory=str(directory),downloads_manifest=dict(path=str(destination),sha256=digest(destination)),
            region=dict(width_arcmin=6.,height_arcmin=6.,pixel_scale_arcsec=6.15,mask_policy='motion'),
            header_integrity=header_records,pixels_opened_by_data_agent=False,final_authorized=False)
        if group['split']=='final':final.append(record)
        else:ready.append(record)
    common=dict(schema_version=4,updated_utc=datetime.now(timezone.utc).isoformat(),plan_sha256=digest(OWN/'partition-plan.json'),selection_sha256=digest(OWN/'selected-groups.json'),
        excluded_v3_or_legacy_physical_obsids=len(plan['excluded_physical_obsids']),cross_parent_obsid_overlap=0,final_pixels_opened=False)
    development=dict(common,scope='TRAIN_AND_DEVELOPMENT_VALIDATION_ONLY',groups=ready,pending_development=[p for p in pending if'final'not in p])
    quarantine=dict(common,scope='QUARANTINED_FINAL_METADATA_ONLY_NO_PIXEL_AUTHORIZATION',groups=final,pending_final=[p for p in pending if'final'in p])
    write(OWN/'development-handoff.json',development);write(OWN/'final-quarantine-audit.json',quarantine)
    write(ROOT/'development-handoff.json',development);write(ROOT/'final-quarantine-audit.json',quarantine)
    print(json.dumps(dict(development_ready=[g['parent_id']for g in ready],final_byte_header_ready=len(final),pending=pending,development_handoff_sha256=digest(OWN/'development-handoff.json')),indent=2))
if __name__=='__main__':main()
