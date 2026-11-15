"""Retrieve only the prospectively selected known case; no pixel reads."""
from __future__ import annotations
import hashlib,json,math,types
from pathlib import Path
from urllib.parse import urlencode
import search
OWN=Path(__file__).resolve().parent

def main():
    selected_path=OWN/'selected-metadata.json'
    if not selected_path.exists():raise ValueError('No prospectively selected metadata case')
    search_log=json.loads((OWN/'search-log.json').read_text())
    if any(r.get('status')!='complete'or r.get('failures')for r in search.latest_attempts(search_log).values()):raise ValueError('Unresolved earlier-priority metadata query/refinement failures; no partial selection download')
    selected=json.loads(selected_path.read_text());plan=json.loads((OWN/'plan.json').read_text())
    if search.sha(OWN/'plan.json')!=search.PLAN_SHA or selected['plan_sha256']!=search.PLAN_SHA:raise ValueError('Plan binding mismatch')
    excluded=set(plan['excluded_physical_obsids']);obsids=[r['obs_id']for r in selected['exposures']]
    if len(obsids)!=len(set(obsids))or set(obsids)&excluded:raise ValueError('Physical OBSID exclusion/uniqueness failure')
    root=Path(plan['download']['raw_root'])/selected['group_id'];root.mkdir(parents=True,exist_ok=True)
    # Scanner only reads 2880-byte header blocks and seeks across data payloads.
    source=OWN.parent/'headers.py';headers=types.ModuleType('header_only');exec(compile(source.read_bytes(),str(source),'exec'),headers.__dict__)
    items=[];download_evidence=[]
    for row in selected['exposures']:
        url=row['access_url']+'?'+urlencode(dict(center=','.join(map(str,selected['roi']['center'])),size=.12));path=root/Path(row['access_url']).name
        # search.fetch saves exact request URL/HTTP headers/hash beside the opaque file.
        search.fetch(url,path)
        with path.open('rb')as stream:hdus=headers.scan(stream,path.stat().st_size)
        byname={h['name']:h for h in hdus};required={'IMAGE','FLAGS','VARIANCE','ZODI','EPSF','WCS-WAVE'}
        if not required.issubset(byname):raise ValueError('Missing native mission extension')
        primary=hdus[0]['header'];image=byname['IMAGE']['header'];combined={**primary,**image}
        if combined.get('OBSID')!=row['obs_id']or int(combined['DETECTOR'])!=selected['detector']:raise ValueError('Wrong physical exposure/detector')
        shape=[image[k]for k in ['NAXIS2','NAXIS1']]
        if any([byname[n]['header'][k]for k in ['NAXIS2','NAXIS1']]!=shape for n in ['FLAGS','ZODI','VARIANCE']):raise ValueError('Array dimensions disagree')
        midpoint=float(combined['MJD-AVG']);t0,t1=float(row['t_min']),float(row['t_max'])
        if not t0-1e-6<=midpoint<=t1+1e-6:raise ValueError('Header midpoint outside acquisition interval')
        evidence=dict(obs_id=row['obs_id'],detector=selected['detector'],url=url,path=str(path),sha256=search.sha(path),bytes=path.stat().st_size,midpoint_mjd=midpoint,native_shape=shape,image_bunit=image.get('BUNIT'),variance_bunit=byname['VARIANCE']['header'].get('BUNIT'),epsf_detcoord=byname['EPSF']['header'].get('DETCOORD'),epsf_oversampling=[byname['EPSF']['header'].get('OVSMPX'),byname['EPSF']['header'].get('OVSMPY')],pixels_opened=False,header_only=True,hdu_headers=hdus)
        download_evidence.append(evidence);items.append(dict(path=str(path),obs_id=row['obs_id'],sha256=evidence['sha256'],midpoint_mjd=midpoint,t_min_mjd=t0,t_max_mjd=t1));print('DOWNLOADED',row['obs_id'],evidence['bytes'],flush=True)
    ephemeris,ref=search.horizons(selected['target'],times=[r['midpoint_mjd']for r in items]);points=[min(ephemeris,key=lambda p:abs(p['mjd']-r['midpoint_mjd']))for r in items]
    # Refinement uses header timestamps, remains offline truth only.
    for row,point in zip(selected['exposures'],points):
        if not search.inside(row['s_region'],[point['ra_deg'],point['dec_deg']]):raise ValueError('Header-time target outside full footprint')
    handoff=dict(schema_version=1,role='KNOWN DEVELOPMENT CASE; target ephemerides not feature/detection inputs',group_id=selected['group_id'],split='known_development',detector=selected['detector'],center=selected['roi']['center'],region_arcmin=[6,6],pixel_scale_arcsec=6.15,images=items,physical_obsids=obsids,metadata_selection_sha256=search.sha(selected_path),plan_sha256=search.PLAN_SHA,exclusion_count=len(excluded),pixels_opened=False,no_model_calls=True,no_training_labels=True)
    truth=dict(role='OFFLINE KNOWN-TARGET MATCHING ONLY; keep separate until features/predictions fixed',target=selected['target'],ephemeris_ref=ref,positions=points,observer='Earth geocenter',parallax_arcsec_bounds=[math.degrees(math.atan2(8000,p['range_au']*149597870.7-8000))*3600 for p in points],astrometric_limits=plan['parallax']['limitations'],image_sha256s=[r['sha256']for r in items],handoff_sha256=None)
    search.write(OWN/'raw-handoff.json',handoff);truth['handoff_sha256']=search.sha(OWN/'raw-handoff.json');search.write(OWN/'offline-header-time-ephemeris.json',truth);search.write(OWN/'header-byte-audit.json',dict(header_scanner_sha256=search.sha(source),metadata_selection_sha256=search.sha(selected_path),downloads=download_evidence,no_image_data_reader=True));print('HANDOFF',search.sha(OWN/'raw-handoff.json'),flush=True)
if __name__=='__main__':main()
