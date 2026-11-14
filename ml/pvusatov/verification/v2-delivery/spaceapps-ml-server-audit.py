import datetime
import json
import subprocess
import urllib.request

def docker(*args):return subprocess.check_output(['docker',*args],text=True)
result={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'services':{}}
for service,name,url in [
    ('backend','spaceapps-api-1','http://127.0.0.1/version'),
    ('frontend','spaceapps-frontend-frontend-1','http://127.0.0.1:8080/frontend-version.json')]:
    container=json.loads(docker('inspect',name))[0]
    revision=container['Config']['Labels']['org.opencontainers.image.revision']
    image='spaceapps-api' if service=='backend' else 'spaceapps-frontend'
    latest=json.loads(docker('image','inspect',image+':latest'))[0]['Id']
    exact=json.loads(docker('image','inspect',image+':'+revision))[0]['Id']
    assert latest==exact==container['Image'],service+' latest/running/exact image mismatch'
    assert container['State']['Health']['Status']=='healthy',service
    with urllib.request.urlopen(url,timeout=15) as response:version=json.load(response)['version']
    assert version==revision,(service,version,revision)
    result['services'][service]={'revision':revision,'image_id':latest,'latest_matches_running':True,'health':'healthy'}
data=docker('exec','spaceapps-api-1','/opt/inference-venv/bin/python','-c',
            'import hashlib,sys;print(sys.version.split()[0]);print(hashlib.sha256(open("/app/inference/models/ranker.onnx","rb").read()).hexdigest())').splitlines()
assert data[1]=='dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9'
result['python']=data[0];result['model_sha256']=data[1]
bindings=docker('port','spaceapps-api-1','50051/tcp').splitlines()
assert bindings and all(b.startswith('127.0.0.1:') or b.startswith('[::1]:') for b in bindings),bindings
result['private_grpc_binding']=bindings
print(json.dumps(result,indent=2))
