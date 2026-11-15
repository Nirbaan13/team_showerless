#!/usr/bin/env python3
"""Export the exact four running demo services; never copy production volumes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid

CONTAINERS={'frontend':'spaceapps-frontend-frontend-1','api':'spaceapps-api-1','pipeline':'spaceapps-pipeline-1','ml-inference':'spaceapps-ml-ml-inference-1'}

def snapshot(host, identity, known_hosts, output):
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+@[a-zA-Z0-9.-]+',host):
        raise ValueError('Use an explicit user@host SSH target')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    remote='/tmp/spaceapps-demo-snapshot-'+uuid.uuid4().hex
    script='''import subprocess,json,gzip,hashlib,pathlib,datetime
containers=CONTAINERS_VALUE
root=pathlib.Path(REMOTE_VALUE);root.mkdir(mode=0o700)
records={};images={}
for service,name in containers.items():
 c=json.loads(subprocess.check_output(['docker','container','inspect',name]))[0]
 if not c['State']['Running']:raise RuntimeError('Container is not running: '+name)
 image=json.loads(subprocess.check_output(['docker','image','inspect',c['Image']]))[0]
 labels=image.get('Config',{}).get('Labels') or {}
 env=dict(e.split('=',1) for e in image.get('Config',{}).get('Env',[]) if '=' in e)
 rev=labels.get('org.opencontainers.image.revision') or env.get('APP_REVISION')
 row={'image':c['Config']['Image'],'image_id':image['Id'],'revision':rev,'os':image['Os'],'architecture':image['Architecture'],'size':image['Size'],'source_container':name,'container_started_at':c['State']['StartedAt']}
 if image.get('Variant'):row['variant']=image['Variant']
 records[service]=row;images[row['image']]=row
inventory={'schema_version':1,'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_host':HOST_VALUE,'services':records,'source_images':list(images.values())}
archive=root/'images-source.tar.gz'
with archive.open('wb') as out:
 save=subprocess.Popen(['docker','image','save',*images.keys()],stdout=subprocess.PIPE)
 zipped=subprocess.run(['gzip','-1'],stdin=save.stdout,stdout=out)
 save.stdout.close()
 if save.wait()!=0 or zipped.returncode!=0:raise RuntimeError('Image export failed')
h=hashlib.sha256()
with archive.open('rb') as f:
 for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
inventory['source_export']={'path':str(archive),'sha256':h.hexdigest(),'size':archive.stat().st_size}
(root/'inventory.json').write_text(json.dumps(inventory,indent=2))
print(json.dumps(inventory),flush=True)
'''.replace('CONTAINERS_VALUE',repr(CONTAINERS)).replace('REMOTE_VALUE',repr(remote)).replace('HOST_VALUE',repr(host))
    opts=['-i',str(identity),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known_hosts),'-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=4']
    result=subprocess.run(['ssh',*opts,host,'python3 -'],input=script,text=True,capture_output=True,check=True)
    inventory=json.loads(result.stdout)
    (output/'inventory-source.json').write_text(json.dumps(inventory,indent=2)+'\n')
    subprocess.run(['scp',*opts,host+':'+inventory['source_export']['path'],str(output/'images-source.tar.gz')],check=True)
    h=hashlib.sha256()
    with (output/'images-source.tar.gz').open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    if h.hexdigest()!=inventory['source_export']['sha256']:raise ValueError('Transferred image archive checksum mismatch')
    print(json.dumps({'inventory':str(output/'inventory-source.json'),'archive':str(output/'images-source.tar.gz'),'sha256':h.hexdigest(),'services':list(inventory['services'])}),flush=True)
    return inventory

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',required=True);p.add_argument('--identity',type=Path,required=True);p.add_argument('--known-hosts',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();snapshot(args.host,args.identity,args.known_hosts,args.output)
