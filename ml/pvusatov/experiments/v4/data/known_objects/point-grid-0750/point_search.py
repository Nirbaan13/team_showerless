"""Bounded daily POINT-grid transport adapter; original eligibility unchanged."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from datetime import datetime,timezone
import hashlib,json,time,threading
import search
OWN=Path(__file__).resolve().parent;RULE=json.loads((OWN/'point-grid-plan.json').read_text());END=datetime.fromisoformat(RULE['deadline_utc']).timestamp();LOCK=threading.Lock();LAST=0

def fetch(url,path,*,timeout=60,max_attempts=1):
    global LAST
    if path.exists():return path.read_bytes()
    with LOCK:
        if time.time()>=END:raise RuntimeError('Original 08:46 UTC hard budget exhausted')
        time.sleep(max(0,1.05-(time.monotonic()-LAST)));LAST=time.monotonic()
    record=dict(url=url,transport_host='local workstation',requested_utc=datetime.now(timezone.utc).isoformat());start=time.monotonic()
    try:
        with urlopen(Request(url,headers={'User-Agent':'SpaceApps-known-object-metadata/1.0'}),timeout=min(timeout,max(1,END-time.time())))as response:
            b=response.read(4194305)
            if len(b)>4194304:raise RuntimeError('Unresolved response-cap overflow >4MiB')
            record.update(status=response.status,headers=dict(response.headers),bytes=len(b),sha256=hashlib.sha256(b).hexdigest());path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b)
        return b
    except Exception as e:record['error']=f'{type(e).__name__}: {e}';raise
    finally:
        record['wall_seconds']=time.monotonic()-start;search.write(path.with_suffix(path.suffix+'.request.json'),record)

def daily(label,collection,center,radius,t0,t1):
    target=next(t for t in json.loads((OWN/'plan.json').read_text())['targets']if t['name'].lower()==label.split('-')[0]);grid,_=search.horizons(target);days=[p for p in grid if t0-1e-8<=p['mjd']<=t1+1e-8]
    if len(days)!=15:raise ValueError('Original daily grid is incomplete')
    def one(day):
        sources=[]
        for limit in [512,4096]:
            params=dict(POS=f'CIRCLE {day["ra_deg"]:.10f} {day["dec_deg"]:.10f} 0.001',COLLECTION=collection,RESPONSEFORMAT='VOTABLE',MAXREC=limit);path=OWN/'evidence'/f'{label}-{collection}-day{day["mjd"]:.0f}-{limit}.xml';b=fetch('https://irsa.ipac.caltech.edu/SIA?'+urlencode(params),path);rows,status=search.parse_sia(b);raw=len(rows);rows=[r for r in rows if float(r['t_max'])>=max(t0,day['mjd']-.5)and float(r['t_min'])<=min(t1,day['mjd']+.5)];sources.append(dict(path=str(path),sha256=search.sha(path),status=status,raw_rows=raw,time_filtered_rows=len(rows),point_mjd=day['mjd']))
            if not any(s.get('value')=='OVERFLOW'for s in status):return rows,sources
        raise RuntimeError('Unresolved daily-point query overflow at 4096 rows')
    rows=[];sources=[]
    try:
        with ThreadPoolExecutor(max_workers=2)as pool:
            for index in range(0,15,2):
                futures=[pool.submit(one,p)for p in days[index:index+2]]
                for future in futures:
                    found,refs=future.result();rows.extend(found);sources.extend(refs)
                search.write(OWN/f'progress-{label}-{collection}.json',dict(completed_points=min(index+2,15),planned_points=15,rows=len(rows),sources=sources));print('POINTS',label,collection,min(index+2,15),'rows',len(rows),flush=True)
    except Exception as e:
        search.write(OWN/'point-incomplete.json',dict(status='INCOMPLETE_DAILY_METADATA_DOMAIN',label=label,collection=collection,error=f'{type(e).__name__}: {e}',completed_sources=sources,no_coverage_inference=True,no_pixels=True));raise SystemExit('INCOMPLETE '+str(e))
    return rows,sources

if __name__=='__main__':
    search.fetch=fetch;search.query_sia=daily;search.main()
