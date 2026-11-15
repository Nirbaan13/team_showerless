"""Metadata-only prospectively fixed longer-span case; no IRSA/FITS/model calls."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,hashlib,json,math,types
OWN=Path(__file__).resolve().parent;CASE=OWN.parent/'point-grid-0750';p=CASE/'search.py';m=types.ModuleType('known_secondary_helper');m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);m.EVID=OWN/'evidence'
def main():
    plan=json.loads((OWN/'plan.json').read_text());original=json.loads((CASE/'plan.json').read_text());target=original['targets'][0];log=json.loads((CASE/'search-log.json').read_text());excluded=set(plan['excluded_physical_obsids']);checks=[]
    for anchor in log:
        rows=[]
        for query in anchor['queries']:
            raw=gzip.decompress((CASE/'evidence'/(Path(query['path']).name+'.gz')).read_bytes());assert hashlib.sha256(raw).hexdigest()==query['sha256'];found,_=m.parse_sia(raw);day=query['point_mjd'];rows.extend(r for r in found if float(r['t_max'])>=max(anchor['t_min'],day-.5)and float(r['t_min'])<=min(anchor['t_max'],day+.5))
        usable=m.deduplicate(rows,excluded)
        for detector in original['selection']['detector_preference']:
            det=[r for r in usable if r['energy_bandpassname']==f'SPHEREx-D{detector}']
            for index,start in enumerate(det):
                cluster=[r for r in det[index:]if(float(r['t_max'])-float(start['t_min']))*24<=6][:5]
                if len(cluster)<3:continue
                if datetime.now(timezone.utc)>=datetime.fromisoformat(plan['deadline_utc']):raise RuntimeError('Original acquisition deadline exhausted')
                times=[(float(r['t_min'])+float(r['t_max']))/2 for r in cluster];points,ref=m.horizons(target,times=times);positions=[min(points,key=lambda p:abs(p['mjd']-t))for t in times]
                covered=[(r,p)for r,p in zip(cluster,positions)if m.inside(r['s_region'],[p['ra_deg'],p['dec_deg']])];roi=m.common_roi([r for r,p in covered],[p for r,p in covered])if len(covered)>=3 else None
                span=max((m.angle([a['ra_deg'],a['dec_deg']],[b['ra_deg'],b['dec_deg']])*3600/6.15 for r,a in covered for s,b in covered),default=0);parallax=max(math.degrees(math.atan2(8000,p['range_au']*149597870.7-8000))*3600/6.15 for p in positions);separation=min(m.angle(roi['center'],c)for c in original['excluded_parent_centers'].values())if roi else None
                record=dict(anchor=anchor['anchor'],detector=detector,obsids=[r['obs_id']for r in cluster],exact_ephemeris=ref,covered_epochs=len(covered),common_roi=roi,geocentric_footprint_covered_span_px=span,maximum_parallax_envelope_px=parallax,parent_separation_deg=separation)
                checks.append(record);m.write(OWN/'checks.json',checks)
                if roi and span>=5 and parallax<1 and separation>=5:
                    m.write(OWN/'selected-long-metadata.json',dict(status='METADATA_ELIGIBLE_ONLY; NO IMAGE DOWNLOAD OR MODELS',plan_sha256=m.sha(OWN/'plan.json'),record=record,exposures=[r for r,p in covered],positions_offline_only=[p for r,p in covered],correlated_with_original_known_sky=True));print('LONG_METADATA_ELIGIBLE',len(covered),span,parallax,flush=True);return
    m.write(OWN/'feasibility-result.json',dict(status='NO_ELIGIBLE_LONG_CASE_IN_EXISTING_NARROW_QUERY_DOMAIN',metadata_clusters_checked=len(checks),plan_sha256=m.sha(OWN/'plan.json'),no_exhaustive_archive_noncoverage_claim=True,no_images_or_models=True));print('NO_ELIGIBLE_LONG_METADATA',len(checks),flush=True)
if __name__=='__main__':main()
