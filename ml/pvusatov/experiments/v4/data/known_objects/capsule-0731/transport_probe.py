"""Read-only VPS egress diagnostic: exact failed minimal metadata URL only."""
from pathlib import Path
import base64,hashlib,json,subprocess,datetime
OWN=Path(__file__).resolve().parent
REMOTE=r'''
import base64,json,time
from urllib.request import Request,urlopen
url=__URL__
record=dict(url=url,transport_host='144.124.238.101',timeout_seconds=30,response_cap_bytes=4194304)
t=time.monotonic()
try:
 with urlopen(Request(url,headers={'User-Agent':'SpaceApps-known-object-metadata/1.0'}),timeout=30)as r:
  b=r.read(4194305)
  if len(b)>4194304:raise ValueError('Response exceeds declared 4MiB cap')
  record.update(status=r.status,headers=dict(r.headers),response_base64=base64.b64encode(b).decode())
except Exception as e:record['error']=f'{type(e).__name__}: {e}'
record['wall_seconds']=time.monotonic()-t
print(json.dumps(record))
'''
def main():
    original=json.loads((OWN/'evidence/minimal-diagnostic.xml.failures.json').read_text());url=original['url'];script=REMOTE.replace('__URL__',repr(url))
    declaration=dict(declared_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),purpose='Exact same declared minimal SIA query through independently authorized VPS egress; no services/app/container changes',url=url,transport_host='144.124.238.101',remote_source_sha256=hashlib.sha256(script.encode()).hexdigest(),timeout_seconds=30,response_cap_bytes=4194304,selection_use=False)
    (OWN/'transport-diagnostic-plan.json').write_text(json.dumps(declaration,indent=2)+'\n')
    args=['ssh','-i','/home/usatovpavel/.ssh/spaceapps-netherlands-admin-20261114','-o','UserKnownHostsFile=/home/usatovpavel/.local/state/spaceapps-migration-20261114/known_hosts','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','root@144.124.238.101','PYTHONDONTWRITEBYTECODE=1 python3 -']
    result=subprocess.run(args,input=script,text=True,capture_output=True,timeout=50)
    if result.returncode:raise RuntimeError(f'SSH diagnostic failed: {result.stderr}')
    record=json.loads(result.stdout);record['local_received_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();b=base64.b64decode(record.pop('response_base64'))if'response_base64'in record else None
    if b is not None:
        p=OWN/'evidence/vps-minimal-diagnostic.xml';p.write_bytes(b);record.update(response_path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
    (OWN/'evidence/vps-transport-diagnostic.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({k:v for k,v in record.items()if k!='headers'}))
if __name__=='__main__':main()
