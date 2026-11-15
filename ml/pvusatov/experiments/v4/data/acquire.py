"""Bounded official-IRSA V4 acquisition; final files remain opaque."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib,json,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import xml.etree.ElementTree as ET
ROOT=Path('/tmp/spaceapps-v4-native-data');OWN=Path(__file__).resolve().parent

def digest(path):
    sha=hashlib.sha256()
    with Path(path).open('rb')as f:
        for chunk in iter(lambda:f.read(1048576),b''):sha.update(chunk)
    return sha.hexdigest()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temporary.replace(path)
def fetch(url,path,timeout=120):
    failures=[];path.parent.mkdir(parents=True,exist_ok=True)
    for attempt in range(4):
        try:
            temporary=path.with_suffix(path.suffix+'.part');sha=hashlib.sha256()
            with urlopen(Request(url,headers={'User-Agent':'SpaceApps-native-v4-research/1.0'}),timeout=timeout)as response,temporary.open('wb')as out:
                headers={key:response.headers.get(key)for key in ['Date','Last-Modified','ETag','Content-Type']}
                for block in iter(lambda:response.read(1048576),b''):sha.update(block);out.write(block)
            temporary.replace(path)
            return dict(url=url,path=str(path),bytes=path.stat().st_size,sha256=sha.hexdigest(),response_headers=headers,transient_failures=failures)
        except Exception as error:
            failures.append(f'{type(error).__name__}: {error}')
            if attempt==3:raise
            time.sleep(2*(attempt+1))
def parse(path):
    root=ET.parse(path).getroot();names=[node.attrib['name']for node in root.findall('.//{*}TABLE/{*}FIELD')]
    rows=[dict(zip(names,[''.join(cell.itertext()).strip()for cell in row]))for row in root.findall('.//{*}TABLEDATA/{*}TR')]
    status=[node.attrib for node in root.findall('.//{*}INFO')];return rows,status

def discover(group,plan):
    directory=ROOT/'metadata'/group['group_id'];record=dict(group,created_utc=datetime.now(timezone.utc).isoformat(),attempts=[])
    for limit in [512,4096]:
        params=dict(POS=f"CIRCLE {group['center'][0]} {group['center'][1]} 0.001",COLLECTION='spherex_dr1',RESPONSEFORMAT='VOTABLE',MAXREC=limit)
        url='https://irsa.ipac.caltech.edu/SIA?'+urlencode(params)
        try:
            source=fetch(url,directory/f'sia-{limit}.xml',150);rows,status=parse(source['path']);record['attempts'].append(dict(source=source,status=status))
            if any(item.get('value')=='ERROR'for item in status):raise ValueError('IRSA SIA reports QUERY_STATUS ERROR')
            if any(item.get('value')=='OVERFLOW'for item in status):
                if limit==4096:raise ValueError('SIA overflow persists at predeclared4096limit')
                continue
            record.update(rows=rows,status=status,query_url=url);break
        except Exception as error:record['error']=f'{type(error).__name__}: {error}';break
    write(directory/'discovery.json',record);return record

def select(group,rows,excluded):
    choices=[];removed=0
    for detector in [1,2,3]:
        usable=[r for r in rows if r.get('energy_bandpassname')==f'SPHEREx-D{detector}'and'/dr1/'in r.get('access_url','')]
        usable.sort(key=lambda r:(float(r['t_min']),r['obs_id'],r['access_url']))
        unique={}
        for row in usable:
            if row['obs_id']in excluded:removed+=1;continue
            unique.setdefault(row['obs_id'],row)
        exposures=sorted(unique.values(),key=lambda r:(float(r['t_min']),r['obs_id']))
        for i,start in enumerate(exposures):
            t0=float(start['t_min']);short=[r for r in exposures[i:]if(float(r['t_min'])-t0)*24<=1.5][:3]
            if len(short)<3:continue
            ids={r['obs_id']for r in short}
            for window in [48.,168.]:
                rest=[r for r in exposures[i:]if(float(r['t_min'])-t0)*24<=window and r['obs_id']not in ids]
                n=min(8-len(short),len(rest));extra=[rest[round(j*(len(rest)-1)/(n-1))]for j in range(n)]if n>1 else rest[:n]
                chosen=sorted(short+extra,key=lambda r:float(r['t_min']));span=(float(chosen[-1]['t_max'])-t0)*24
                tier=(0 if window==48 else 1)if len(chosen)==8 and span>=2 else((2 if window==48 else 3)if len(chosen)>=6 and span>=2 else 4)
                choices.append(((tier,detector!=group['preferred_detector'],t0,window,detector),detector,chosen,short,span,window))
    if not choices:return dict(group,error='No >=3 unique supported SWIR metadata cluster after physical-OBSID exclusions',excluded_row_count=removed)
    priority,detector,chosen,short,span,window=min(choices,key=lambda c:c[0])
    return dict(group,detector=detector,exposures=chosen,short_exposures=short,metadata_span_hours=span,metadata_window_hours=window,selection_tier=priority[0],excluded_row_count=removed,
                feasibility_constraints=[]if priority[0]==0 else['Predeclared cadence/detector fallback applied; retained without pixel or model-performance filtering'])

def download(group,plan):
    if group.get('error'):return group
    directory=ROOT/('quarantine_final'if group['split']=='final'else'development')/group['group_id'];directory.mkdir(parents=True,exist_ok=True)
    downloads=[];failures=[]
    for exposure in group['exposures']:
        url=exposure['access_url']+'?'+urlencode(dict(center=','.join(map(str,group['center'])),size=.12));path=directory/Path(exposure['access_url']).name
        try:
            info=dict(url=url,path=str(path),bytes=path.stat().st_size,sha256=digest(path))if path.exists()else fetch(url,path,180)
            if info['bytes']%2880:raise ValueError('FITS file not2880-bytealigned')
            with path.open('rb')as f:
                if f.read(9)!=b'SIMPLE  =':raise ValueError('Not a FITS primary header')
            info.update(obs_id=exposure['obs_id'],detector=group['detector'],t_min_mjd=float(exposure['t_min']),t_max_mjd=float(exposure['t_max']))
            downloads.append(info);write(directory/'downloads.json',downloads)
        except Exception as error:
            failures.append(dict(url=url,obs_id=exposure['obs_id'],error=f'{type(error).__name__}: {error}'));write(directory/'download-failures.json',failures)
    result=dict(group,directory=str(directory),downloads=downloads,download_failures=failures,pixels_opened=False)
    write(directory/'group.json',result);return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['discover','select','download']);parser.add_argument('--groups',nargs='*');parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    if not 1<=args.workers<=4:raise ValueError('Network workers must be1–4')
    plan=json.loads((OWN/'partition-plan.json').read_text())
    if digest(OWN/'partition-plan.json')!=digest(ROOT/'partition-plan.json'):raise ValueError('Declared plan copies differ')
    if args.command=='select':
        destination=ROOT/'selected-groups.json'
        if destination.exists():raise ValueError('Refusing to overwrite prospective selection')
        selected=[];excluded=set(plan['excluded_physical_obsids'])
        for group in plan['groups']:
            discovery=json.loads((ROOT/'metadata'/group['group_id']/'discovery.json').read_text());result=select(group,discovery.get('rows',[]),excluded)
            if discovery.get('error'):result['discovery_error']=discovery['error']
            excluded.update(r['obs_id']for r in result.get('exposures',[]));selected.append(result)
            print(result['group_id'],result.get('detector'),len(result.get('exposures',[])),round(result.get('metadata_span_hours',0),3),result.get('error','ok'),flush=True)
        write(destination,selected);write(OWN/'selected-groups.json',selected);print('selected_sha256',digest(destination));return
    groups=plan['groups']if args.command=='discover'else json.loads((ROOT/'selected-groups.json').read_text())
    groups=[g for g in groups if not args.groups or g['group_id']in args.groups]
    function=discover if args.command=='discover'else download
    with ThreadPoolExecutor(max_workers=args.workers)as pool:
        for future in as_completed([pool.submit(function,g,plan)for g in groups]):
            r=future.result();print(r['group_id'],len(r.get('rows',[]))if args.command=='discover'else len(r.get('downloads',[])),r.get('error','ok'),flush=True)

if __name__=='__main__':main()
