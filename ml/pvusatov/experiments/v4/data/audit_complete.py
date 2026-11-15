"""Complete V4 native audit: opaque hashes and FITS headers, never FINAL pixels."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import hashlib,json,math
from urllib.parse import urlsplit,parse_qs
from acquire import OWN,digest
from headers import scan,inspect

def main():
    plan=json.loads((OWN/'partition-plan.json').read_text());selected=json.loads((OWN/'selected-groups.json').read_text());development=json.loads((OWN/'development-handoff.json').read_text());final=json.loads((OWN/'final-quarantine-audit.json').read_text())
    all_ready=development['groups']+final['groups'];lookup={g['parent_id']:g for g in all_ready};seen=set(plan['excluded_physical_obsids']);records=[];parents=[];max_time_error=0.
    if len(lookup)!=28 or development['pending_development']or final['pending_final']:raise ValueError('Declared cohort not complete')
    for group in selected:
        parent=lookup[group['parent_id']];manifest=Path(parent['downloads_manifest']['path'])
        if digest(manifest)!=parent['downloads_manifest']['sha256']:raise ValueError('Handoff manifest bytes changed')
        rows=json.loads(manifest.read_text());exposures={r['obs_id']:r for r in group['exposures']}
        if len(rows)!=8 or len({r['obs_id']for r in rows})!=8 or set(exposures)!={r['obs_id']for r in rows}:raise ValueError('Exact eight-epoch selection differs')
        times=[];units=[]
        for row in rows:
            obs=row['obs_id']
            if obs in seen:raise ValueError('Physical OBSID overlaps excluded or another parent')
            seen.add(obs);path=Path(row['path'])
            if digest(path)!=row['sha256']or path.stat().st_size!=row['bytes']:raise ValueError('Native bytes changed')
            split=urlsplit(row['url']);query=parse_qs(split.query)
            if split.scheme!='https'or split.netloc!='irsa.ipac.caltech.edu'or not split.path.startswith('/ibe/data/spherex/dr1/')or query['size']!=['0.12']:raise ValueError('Not the declared official native cutout transport')
            if[float(v)for v in query['center'][0].split(',')]!=group['center']:raise ValueError('Cutout center changed')
            check=inspect(path,obs,group['detector'])
            with path.open('rb')as stream:hdus=scan(stream,path.stat().st_size)
            byname={h['name']:h['header']for h in hdus};header={**hdus[0]['header'],**byname['IMAGE']}
            if byname['IMAGE'].get('DETCOORD')!=byname['EPSF'].get('DETCOORD')or byname['EPSF'].get('DETCOORD')!='sky':raise ValueError('Native IMAGE/ePSF frame mismatch')
            if[byname['EPSF'].get('OVSMPX'),byname['EPSF'].get('OVSMPY')]!=[5,5]:raise ValueError('Unsupported ePSF oversampling')
            midpoint=float(check['midpoint_mjd']);expected=(row['t_min_mjd']+row['t_max_mjd'])/2;error=abs(midpoint-expected)*86400;max_time_error=max(max_time_error,error)
            if error>.0864:raise ValueError('Native midpoint differs beyond SIA endpoint precision')
            times.append(midpoint);units.append(header.get('BUNIT'))
            records.append(dict(parent_id=group['parent_id'],split=group['split'],physical_obsid=obs,detector=group['detector'],path=str(path),url=row['url'],sha256=row['sha256'],bytes=row['bytes'],midpoint_mjd=midpoint,sia_midpoint_error_seconds=error,header_integrity=check))
        if len(set(times))!=8 or len(set(units))!=1:raise ValueError('Independent time/unit metadata inconsistent')
        span=(max(times)-min(times))*24
        if span<2 or span>48.01:raise ValueError('Metadata-supported primary cadence not satisfied')
        parents.append(dict(parent_id=group['parent_id'],split=group['split'],stratum=group['stratum'],detector=group['detector'],native_epochs=8,physical_span_hours=span,unit=units[0],downloads_manifest=parent['downloads_manifest']))
    split_counts=Counter(g['split']for g in parents);detector_counts={split:dict(Counter(g['detector']for g in parents if g['split']==split))for split in split_counts}
    if dict(split_counts)!=dict(train=8,validation=8,final=12)or len(records)!=224 or len({r['sha256']for r in records})!=224:raise ValueError('Final cohort counts/raw hashes differ')
    source_files=sorted(OWN.glob('*.py'))
    report=dict(schema_version=4,created_utc=datetime.now(timezone.utc).isoformat(),scope='Complete fixed V4 native cohort; opaque byte hash and manual header-only audit. NO FINAL data arrays/pixels, registration, injection, features or models accessed.',
        complete=True,plan_sha256=digest(OWN/'partition-plan.json'),selection_sha256=digest(OWN/'selected-groups.json'),query_index_sha256=digest(OWN/'query-provenance.json'),
        development_handoff_sha256=digest(OWN/'development-handoff.json'),final_quarantine_handoff_sha256=digest(OWN/'final-quarantine-audit.json'),
        data_source_sha256={p.name:digest(p)for p in source_files},
        independent_parent_counts=dict(split_counts),detector_parent_counts=detector_counts,native_mefs=224,native_bytes=sum(r['bytes']for r in records),unique_physical_obsids=224,
        physical_obsid_overlap_with_v3_legacy_or_other_v4_parent=0,excluded_prior_physical_obsids=len(plan['excluded_physical_obsids']),
        maximum_header_vs_sia_midpoint_error_seconds=max_time_error,header_time_precision_tolerance_seconds=.0864,
        native_mission_hdus_preserved=['IMAGE','FLAGS','VARIANCE','ZODI','EPSF','WCS-WAVE'],supported_native_epsf_detectors=[1,2,3],
        final_pixels_opened=False,final_pixel_reader_called=False,final_model_or_protocol_frozen_by_this_audit=False,
        transfer_errors_preserved='transfer-attempts/round01/snapshot-manifest.json; all seven missing URLs recovered without changing prospective physical selection',
        parents=parents,observations=records)
    path=OWN/'complete-audit.json'
    with path.open('x')as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({k:v for k,v in report.items()if k not in ['parents','observations','data_source_sha256']},indent=2));print('audit_sha256',digest(path))
if __name__=='__main__':main()
