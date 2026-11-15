"""One bounded exact-URL local retry, metadata diagnostic only."""
from pathlib import Path
import datetime,hashlib,json,time
from urllib.request import Request,urlopen
OWN=Path(__file__).resolve().parent

def main():
    output=OWN/'evidence/later-minimal-diagnostic.json'
    if output.exists():raise ValueError('The one declared later retry has already run')
    original=OWN/'evidence/minimal-diagnostic.xml.failures.json';url=json.loads(original.read_text())['url']
    declaration=dict(declared_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),url=url,original_failure_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),transport_host='local workstation',timeout_seconds=30,response_cap_bytes=4194304,max_requests=1,selection_use=False)
    (OWN/'later-retry-plan.json').write_text(json.dumps(declaration,indent=2)+'\n');record=dict(declaration);start=time.monotonic()
    try:
        with urlopen(Request(url,headers={'User-Agent':'SpaceApps-known-object-metadata/1.0'}),timeout=30)as r:
            b=r.read(4194305)
            if len(b)>4194304:raise ValueError('Response exceeds declared cap')
            path=OWN/'evidence/later-minimal-diagnostic.xml';path.write_bytes(b);record.update(status=r.status,headers=dict(r.headers),response_path=str(path),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
    except Exception as e:record['error']=f'{type(e).__name__}: {e}'
    record['wall_seconds']=time.monotonic()-start;record['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();output.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
if __name__=='__main__':main()
