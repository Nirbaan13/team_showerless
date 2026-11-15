"""Prospective bounded official metadata search; never reads image pixels."""
from __future__ import annotations
import csv,hashlib,io,json,math,time,xml.etree.ElementTree as ET
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen,Request
import numpy as np
OWN=Path(__file__).resolve().parent;EVID=OWN/'evidence';PLAN_SHA='dbc027aea38fbc1d315986fc5c7ac6a419e1b5cc4bd8a9073e24eeebe1ea3761'
_LAST=0.
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def fetch(url,path,*,timeout=120,max_attempts=2):
    global _LAST
    if path.exists():return path.read_bytes()
    path.parent.mkdir(parents=True,exist_ok=True);failure_path=path.with_suffix(path.suffix+'.failures.json');attempts=json.loads(failure_path.read_text()).get('failures',[])if failure_path.exists()else[]
    for attempt in range(max_attempts):
        time.sleep(max(0,1.05-(time.monotonic()-_LAST)));_LAST=time.monotonic()
        try:
            with urlopen(Request(url,headers={'User-Agent':'SpaceApps-known-object-metadata/1.0'}),timeout=timeout)as r:b=r.read();headers=dict(r.headers)
            path.write_bytes(b);write(path.with_suffix(path.suffix+'.request.json'),dict(url=url,sha256=sha(path),bytes=len(b),fetched_utc=datetime.now(timezone.utc).isoformat(),headers=headers,failures=attempts));return b
        except Exception as e:
            attempts.append(dict(attempt=len(attempts)+1,utc=datetime.now(timezone.utc).isoformat(),error=f'{type(e).__name__}: {e}'));write(path.with_suffix(path.suffix+'.failures.json'),dict(url=url,failures=attempts));time.sleep(2)
    raise RuntimeError(attempts)
def unit(point):
    r,d=np.deg2rad(point);return np.array([math.cos(d)*math.cos(r),math.cos(d)*math.sin(r),math.sin(d)])
def radec(v):
    v=np.asarray(v)/np.linalg.norm(v);return [math.degrees(math.atan2(v[1],v[0]))%360,math.degrees(math.asin(v[2]))]
def angle(a,b):return math.degrees(math.atan2(np.linalg.norm(np.cross(unit(a),unit(b))),np.dot(unit(a),unit(b))))
def inside(region,point):
    parts=region.split()
    if parts[:2]!=['POLYGON','ICRS']:raise ValueError('Only convex ICRS polygons supported')
    values=list(map(float,parts[2:]));vertices=np.array([unit(values[i:i+2])for i in range(0,len(values),2)])
    if np.linalg.norm(vertices[-1]-vertices[0])<1e-12:vertices=vertices[:-1]
    c=vertices.sum(axis=0);c/=np.linalg.norm(c);p=unit(point)
    # Hemisphere guard excludes spherical polygon antipodal complement.
    if np.dot(c,p)<=0:return False
    for a,b in zip(vertices,np.roll(vertices,-1,axis=0)):
        normal=np.cross(a,b);sign=np.dot(normal,c)
        if abs(sign)<1e-14:raise ValueError('Degenerate polygon')
        if np.min(vertices@normal*np.sign(sign))<-1e-12:raise ValueError('Nonconvex polygon')
        if np.dot(normal,p)*np.sign(sign)<-1e-12:return False
    return True

def tangent(center,x_deg,y_deg):
    ra,dec=np.deg2rad(center);east=np.array([-math.sin(ra),math.cos(ra),0]);north=np.array([-math.cos(ra)*math.sin(dec),-math.sin(ra)*math.sin(dec),math.cos(dec)])
    return radec(unit(center)+math.tan(math.radians(x_deg))*east+math.tan(math.radians(y_deg))*north)
def common_roi(rows,points):
    coords=[[p['ra_deg'],p['dec_deg']]for p in points];center=radec(np.sum([unit(p)for p in coords],axis=0))
    corners=[tangent(center,x*3.05/60,y*3.05/60)for x,y in [(-1,-1),(-1,1),(1,1),(1,-1)]]
    # Central square test in the exact local tangent basis.
    ra,dec=np.deg2rad(center);east=np.array([-math.sin(ra),math.cos(ra),0]);north=np.array([-math.cos(ra)*math.sin(dec),-math.sin(ra)*math.sin(dec),math.cos(dec)])
    for p in coords:
        v=unit(p);den=np.dot(v,unit(center))
        if den<=0 or max(abs(math.degrees(math.atan2(np.dot(v,east),den))),abs(math.degrees(math.atan2(np.dot(v,north),den))))>2/60:return None
    try:
        if not all(inside(r['s_region'],p)and all(inside(r['s_region'],c)for c in corners)for r,p in zip(rows,coords)):return None
    except ValueError:return None
    return dict(center=center,corner_half_width_arcmin=3.05,corners_icrf_deg=corners,target_and_corner_coverage_proven=True)
def parse_horizons(payload,name):
    s=payload.get('result','')
    if payload.get('error')or '$$SOE'not in s or '$$EOE'not in s:raise ValueError(f'Horizons missing ephemeris: {payload.get("error",s[:300])}')
    if f'Target body name: 'not in s or name not in s or 'GEOCENTRIC'not in s or 'R.A.___(ICRF)'not in s:raise ValueError('Wrong target/reference origin/frame')
    rows=[]
    for cells in csv.reader(io.StringIO(s.split('$$SOE')[1].split('$$EOE')[0])):
        if not cells or not cells[0].strip():continue
        rows.append(dict(utc=cells[0].strip(),mjd=float(cells[1])-2400000.5,ra_deg=float(cells[4]),dec_deg=float(cells[5]),range_au=float(cells[6])))
    if not rows or any(not all(math.isfinite(r[k])for k in ['mjd','ra_deg','dec_deg','range_au'])or r['range_au']<=0 for r in rows):raise ValueError('Invalid Horizons numbers')
    return rows
def horizons(target,*,times=None):
    params=dict(format='json',COMMAND=f"'{target['command']}'",OBJ_DATA='YES',MAKE_EPHEM='YES',EPHEM_TYPE='OBSERVER',CENTER="'500@399'",REF_SYSTEM='ICRF',QUANTITIES="'1,20'",ANG_FORMAT='DEG',CSV_FORMAT='YES',EXTRA_PREC='YES',TIME_TYPE='UT',TIME_DIGITS='FRACSEC',CAL_FORMAT='BOTH')
    if times is None:
        params.update(START_TIME="'2025-04-24'",STOP_TIME="'2026-04-09'",STEP_SIZE="'1 d'");label=target['name'].lower()+'-grid'
    else:
        times=sorted(set(times));params.update(TLIST="'"+' '.join(f'{t:.12f}'for t in times)+"'",TLIST_TYPE='MJD');label=target['name'].lower()+'-tlist-'+hashlib.sha256(json.dumps(times).encode()).hexdigest()[:16]
    path=EVID/(label+'.json');payload=json.loads(fetch('https://ssd.jpl.nasa.gov/api/horizons.api?'+urlencode(params),path));rows=parse_horizons(payload,target['name'])
    if times is not None and(len(rows)!=len(times)or any(abs(r['mjd']-t)>2e-8 for r,t in zip(rows,times))):raise ValueError('Horizons TLIST times mismatch')
    return rows,dict(path=str(path),sha256=sha(path))
def parse_sia(b):
    root=ET.fromstring(b);names=[n.attrib['name']for n in root.findall('.//{*}TABLE/{*}FIELD')];rows=[dict(zip(names,[''.join(c.itertext()).strip()for c in row]))for row in root.findall('.//{*}TABLEDATA/{*}TR')];status=[dict(n.attrib,text=n.text)for n in root.findall('.//{*}INFO')]
    if any(s.get('value')=='ERROR'for s in status):raise ValueError(f'SIA error {status}')
    return rows,status
def query_sia(label,collection,center,radius,t0,t1):
    sources=[]
    for limit in [512,4096]:
        params=dict(POS=f'CIRCLE {center[0]:.10f} {center[1]:.10f} {radius:.10f}',COLLECTION=collection,RESPONSEFORMAT='VOTABLE',MAXREC=limit);path=EVID/f'{label}-{collection}-posonly-{limit}.xml';b=fetch('https://irsa.ipac.caltech.edu/SIA?'+urlencode(params),path,timeout=60,max_attempts=1);rows,status=parse_sia(b);rows=[r for r in rows if float(r['t_max'])>=t0 and float(r['t_min'])<=t1];sources.append(dict(path=str(path),sha256=sha(path),status=status,rows=len(rows)))
        if not any(s.get('value')=='OVERFLOW'for s in status):return rows,sources
    # Fixed daily fallback; no pixel-dependent or trajectory-dependent adaptation.
    raise OverflowError('SIA overflow: caller must use declared daily-grid fallback')
def deduplicate(rows,excluded):
    unique={}
    for row in sorted(rows,key=lambda r:(0 if '/dr1/'in r['access_url']else 1,r['access_url'])):
        if row['obs_id']not in excluded:unique.setdefault((row['obs_id'],row['energy_bandpassname']),row)
    return sorted(unique.values(),key=lambda r:(float(r.get('t_min',0)),r['obs_id'],r['energy_bandpassname']))

def latest_attempts(log):
    return {(record['target'],record['anchor']):record for record in log}

def main():
    if sha(OWN/'plan.json')!=PLAN_SHA:raise ValueError('Prospective plan hash mismatch')
    write(OWN/'active-search-source.json',dict(source_sha256=sha(Path(__file__)),plan_sha256=PLAN_SHA,operational_supplement_sha256=sha(OWN/'operational-supplement.json')));plan=json.loads((OWN/'plan.json').read_text());excluded=set(plan['excluded_physical_obsids']);logpath=OWN/'search-log.json';log=json.loads(logpath.read_text())if logpath.exists()else[]
    if (OWN/'selected-metadata.json').exists():raise ValueError('Selection already committed; refuse new search')
    for target in plan['targets']:
        grid,gridref=horizons(target)
        for anchor in plan['anchor_dates']:
            previous=latest_attempts(log).get((target['name'],anchor))
            if previous and previous.get('status')=='complete':continue
            anchor_mjd=(datetime.fromisoformat(anchor)-datetime(1858,11,17)).total_seconds()/86400;t0,t1=anchor_mjd-7,anchor_mjd+7;window=[r for r in grid if t0-1e-8<=r['mjd']<=t1+1e-8];ar=min(grid,key=lambda r:abs(r['mjd']-anchor_mjd));center=[ar['ra_deg'],ar['dec_deg']];radius=max(angle(center,[r['ra_deg'],r['dec_deg']])for r in window)+2*max(angle([a['ra_deg'],a['dec_deg']],[b['ra_deg'],b['dec_deg']])for a,b in zip(window,window[1:]))+.06
            record=dict(target=target['name'],anchor=anchor,ephemeris_grid=gridref,cone_center=center,cone_radius_deg=radius,t_min=t0,t_max=t1,queries=[],failures=[]);rows=[]
            for collection in plan['query']['collections']:
                try:
                    found,sources=query_sia(f'{target["name"].lower()}-{anchor}',collection,center,radius,t0,t1);rows.extend(found);record['queries'].extend(sources)
                except OverflowError:
                    for day in window:
                        try:
                            found,sources=query_sia(f'{target["name"].lower()}-{anchor}-day{day["mjd"]:.0f}',collection,[day['ra_deg'],day['dec_deg']],2*max(angle([a['ra_deg'],a['dec_deg']],[b['ra_deg'],b['dec_deg']])for a,b in zip(window,window[1:]))+.06,max(t0,day['mjd']-.5),min(t1,day['mjd']+.5));rows.extend(found);record['queries'].extend(sources)
                        except Exception as e:record['failures'].append(str(e))
                except Exception as e:record['failures'].append(f'{collection}: {type(e).__name__}: {e}')
            if record['failures']:
                record['status']='incomplete';log.append(record);write(logpath,log);write(OWN/'incomplete-acquisition.json',dict(status='INCOMPLETE_ARCHIVE_REQUEST_FAILURE',target=target['name'],anchor=anchor,plan_sha256=PLAN_SHA,log_sha256=sha(logpath),no_coverage_inference=True,no_pixels_opened=True));print('INCOMPLETE',target['name'],anchor,record['failures'],flush=True);return
            record['raw_rows']=len(rows);usable=deduplicate(rows,excluded);record['unique_unexcluded_rows']=len(usable);record['clusters_checked']=[]
            for detector in plan['selection']['detector_preference']:
                det=[r for r in usable if r.get('energy_bandpassname')==f'SPHEREx-D{detector}'];clusters=[]
                for i,r in enumerate(det):
                    cluster=[q for q in det[i:]if(float(q['t_max'])-float(r['t_min']))*24<=2][:5]
                    if len(cluster)>=3:clusters.append(cluster)
                for cluster in clusters:
                    times=[(float(r['t_min'])+float(r['t_max']))/2 for r in cluster]
                    try:
                        exact,ref=horizons(target,times=times);bytime={round(r['mjd'],7):r for r in exact};points=[min(exact,key=lambda x:abs(x['mjd']-t))for t in times]
                        # Keep only target-covered frames, then common-ROI proof on >=3.
                        covered=[(r,p)for r,p in zip(cluster,points)if inside(r['s_region'],[p['ra_deg'],p['dec_deg']])]
                        roi=common_roi([r for r,p in covered],[p for r,p in covered])if len(covered)>=3 else None
                        sep=min(angle(roi['center'],c)for c in plan['excluded_parent_centers'].values())if roi else None
                        record['clusters_checked'].append(dict(detector=detector,obsids=[r['obs_id']for r in cluster],covered=len(covered),common_roi=bool(roi),minimum_parent_separation_deg=sep,ephemeris=ref))
                        if roi and sep>=5:
                            selected=dict(status='metadata_selected_before_download',target=target,anchor=anchor,detector=detector,group_id=f'known-{target["name"].lower()}-{anchor}-d{detector}',split='known_development',exposures=[r for r,p in covered],roi=roi,minimum_parent_separation_deg=sep,metadata_span_hours=(float(covered[-1][0]['t_max'])-float(covered[0][0]['t_min']))*24,plan_sha256=PLAN_SHA,exact_ephemeris_ref=ref,pixels_opened=False)
                            record['status']='complete';write(OWN/'selected-metadata.json',selected);write(OWN/'offline-ephemeris.json',dict(role='OFFLINE LABELS ONLY; never detector/model inputs',target=target,positions=[p for r,p in covered],ephemeris_ref=ref,parallax_arcsec_bounds=[math.degrees(math.atan2(8000,p['range_au']*149597870.7-8000))*3600 for r,p in covered]));log.append(record);write(logpath,log);print('SELECTED',selected['group_id'],len(covered),sep,flush=True);return
                    except Exception as e:
                        record['failures'].append(f'cluster: {type(e).__name__}: {e}');record['status']='incomplete';log.append(record);write(logpath,log);write(OWN/'incomplete-acquisition.json',dict(status='INCOMPLETE_MIDPOINT_REFINEMENT_FAILURE',target=target['name'],anchor=anchor,plan_sha256=PLAN_SHA,log_sha256=sha(logpath),no_coverage_inference=True,no_pixels_opened=True));print('INCOMPLETE',target['name'],anchor,record['failures'],flush=True);return
            record['status']='complete';log.append(record);write(logpath,log);print(target['name'],anchor,'rows',len(rows),'clusters',len(record['clusters_checked']),'failures',record['failures'],flush=True)
    write(OWN/'no-coverage.json',dict(status='no_eligible_metadata_case',plan_sha256=PLAN_SHA,log_sha256=sha(logpath),no_pixels_opened=True))
if __name__=='__main__':main()
