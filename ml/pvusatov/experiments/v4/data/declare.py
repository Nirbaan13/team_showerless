"""Declare a V4 sky/split/cadence cohort before any IRSA query or pixel access."""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,math,re
from astropy.coordinates import SkyCoord
import astropy.units as u

NAMESPACE=Path(__file__).resolve().parents[3]
ROOT=Path('/tmp/spaceapps-v4-native-data')

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def separation(a,b):
    ra,dec,rb,db=map(math.radians,[*a,*b]);x=math.sin(dec)*math.sin(db)+math.cos(dec)*math.cos(db)*math.cos(ra-rb)
    return math.degrees(math.acos(max(-1.,min(1.,x))))
def write_new(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x')as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')

def declare():
    data=NAMESPACE/'backend/inference/experiments/v3_data/evidence/acquisition'
    sources=[data/'audit.json',data/'expansion-v2/audit-expanded-v2.json',NAMESPACE/'verification/final/draft-331c6b1/physical-observation-audit.json',NAMESPACE/'backend/inference/fixtures/observations.csv']
    original=json.loads(sources[0].read_text());expanded=json.loads(sources[1].read_text())
    prior={g['parent_group_id']:g['center']for g in original['groups']+expanded['new_groups']}
    prior.update(M101=[210.80227,54.34895],v2_final=[127.69444,-39.17760])
    legacy={};legacy_obsids=set()
    for row in csv.DictReader(sources[3].open()):
        legacy.setdefault(row['series'],[]).append([float(row['ra_deg']),float(row['dec_deg'])]);legacy_obsids.add(re.sub(r'D[1-6]$','',row['observation_id']))
    for name,points in legacy.items():prior['legacy_'+name]=[sum(p[i]for p in points)/len(points)for i in [0,1]]
    mapping=json.loads(sources[2].read_text())['observations'];excluded={r['physical_obsid']for r in mapping}|legacy_obsids
    candidates=[]
    for lon in range(0,360,15):
        for lat in [-65.,-40.,-10.,0.,10.,40.,65.]:
            icrs=SkyCoord(l=lon*u.deg,b=lat*u.deg,frame='galactic').icrs
            center=[round(float(icrs.ra.deg),8),round(float(icrs.dec.deg),8)]
            if min(separation(center,p)for p in prior.values())>=8.:
                candidates.append(dict(center=center,galactic_lon_lat_deg=[float(lon),lat],stratum='low_galactic_latitude'if abs(lat)<=10 else'off_plane'))
    selected=[];counts={'train':8,'validation':8,'final':12};offsets={'train':0,'validation':1,'final':2}
    for i in range(1,13):
        for split in ['train','validation','final']:
            if i>counts[split]:continue
            stratum='low_galactic_latitude'if i%2 else'off_plane'
            available=[c for c in candidates if c['stratum']==stratum and all(separation(c['center'],g['center'])>=8. for g in selected)]
            if not available:raise ValueError('insufficient pre-query separated grid points')
            def key(c):return(-min(separation(c['center'],p)for p in list(prior.values())+[g['center']for g in selected]),c['galactic_lon_lat_deg'])
            row=min(available,key=key);selected.append(dict(row,parent_id=f'v4-{split}{i:02d}',group_id=f'v4-{split}{i:02d}',split=split,preferred_detector=1+(i-1+offsets[split])%3))
    plan=dict(schema_version=4,declared_utc=datetime.now(timezone.utc).isoformat(),
        purpose='NEW V4 native train/development-validation/quarantined-final; metadata-only prospective selection',
        parent_unit='Sky position containing ALL physical OBSIDs, detectors, crops, processing versions, epochs and derivatives; no independent-N inflation',
        groups=selected,grid=dict(galactic_longitudes_deg=list(range(0,360,15)),galactic_latitudes_deg=[-65,-40,-10,0,10,40,65],selection='Round-robin split slots; odd slot low latitude/even offplane; deterministic maximum minimum separation from all excluded and already selected centers; tie by Galactic lon/lat; NO archive query, pixel or model outcome used',minimum_center_separation_deg=8.),
        excluded_parent_centers=prior,excluded_physical_obsids=sorted(excluded),v3_physical_exposures=200,
        input_provenance=[dict(path=str(p),sha256=digest(p))for p in sources],declaration_source_sha256=digest(__file__),
        query=dict(endpoint='https://irsa.ipac.caltech.edu/SIA',collection='spherex_dr1',position_radius_deg=.001,maxrec=512,overflow_fallback_maxrec=4096,network_workers_max=4,retries=4),
        acquisition=dict(target_exposures=8,minimum_exposures=3,cutout_size_deg=.12,analysis_width_arcmin=6.,analysis_height_arcmin=6.,pixel_scale_arcsec=6.15,mask_policy='motion',supported_detectors=[1,2,3],
            selection='Remove all V3/legacy/V4-other-parent physical OBSIDs before selection. Earliest cluster >=3 epochs within1.5h plus evenly spanning followups. Priority tiers:8 epochs >=2h within48h;8 >=2h within168h;6–7 >=2h within48h;6–7 >=2h within168h;otherwise >=3 within168h constrained. Within tier prefer declared detector, then earliest date, then shortest window. No replacement sky parents after archive or model outcomes. Short variants remain same parent.',
            transport='Actual official IRSA IBE native MEF cutouts; preserve native orientation and all mission HDUs; bounded retries and SHA256/size/FITS-header integrity',
            failure_policy='Keep explicitly failed/constrained declared parent; no performance-based replacement. Metadata-only detector/cadence fallback above predeclared; any further change requires append-only protocol before pixels/outcomes.'),
        quarantine='Final opaque bytes/hash/header-integrity only; no pixel reader, registration, injections, features, inference or scoring until coordinator prospective final model/code freeze and explicit authorization.',
        science_limits=['Native SWIR D1–D3 ePSF offsets are native detector axes; sample native ePSF then WCS-project once. SKY label does not mean north-up. Existing official orientation verification retained.',
                        'Unknown real controls never receive fabricated negative labels or real-precision claims.',
                        'V3 train/validation may remain DEVELOPMENT; published V3 FINAL is excluded from V4 model selection and is not fresh holdout.'])
    path=Path(__file__).parent/'partition-plan.json';write_new(path,plan);write_new(ROOT/'partition-plan.json',plan)
    print(json.dumps(dict(plan=str(path),sha256=digest(path),parents=len(selected),minimum_new_to_old_deg=min(separation(g['center'],p)for g in selected for p in prior.values()),minimum_new_pair_deg=min(separation(a['center'],b['center'])for i,a in enumerate(selected)for b in selected[i+1:]),excluded_obsids=len(excluded)),indent=2))

if __name__=='__main__':declare()
