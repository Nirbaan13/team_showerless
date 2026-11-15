import datetime
import json
import subprocess
import urllib.request

EXPECTED_METADATA='472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13'
EXPECTED_RUNTIME={
    '__init__.py':'1f534210089fc71f7708cd5b6a252db95c4b760e9d1af1db30d600eed247713a',
    '__main__.py':'935a1c1166b0c1ea35a82256345000bf2c73ded718d77773bc27a71ecce28f7d',
    'cli.py':'ef937b51b0a9aa66e59c64769133fefc65facb6ec796b20f22c5c57e0f19009a',
    'contracts.py':'0c05d439e6ec20a56f5fbf93d40cdea62010150f5d41eae1733b9c49bf985816',
    'detector.py':'0f8debc9ecb9c377abd489451ccad1e00808633b071659644045859ac501e31d',
    'features.py':'8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282',
    'median_reference.py':'353f4d0a7b6032d18158df99cf90fa992d3cb0bfc714c96e50c05e75c4b18a2e',
    'model.py':'cd7154e2bbba3595b656c4207e9a6afe890a35e1f12ffa4203ab0b7cf6a74598',
    'pipeline.py':'1d4a7793f89f190cb580c2b9da7defdf2c6ecc864842d3173ceb9c099dda19b0',
    'prepare.py':'27ef087aa19f394eaf16ee19c0801ed6c7557a79a7ea77b3410445363f4624ec',
    'render.py':'abfda31de11555586a2b6ce573d3efc199a1ef96f5c8aa0c11254e216f521f23'
}

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
pipeline=json.loads(docker('inspect','spaceapps-pipeline-1'))[0]
assert pipeline['State']['Health']['Status']=='healthy','pipeline'
assert pipeline['Image']==result['services']['backend']['image_id'],'pipeline/backend image mismatch'
assert pipeline['Config']['Labels']['org.opencontainers.image.revision']==result['services']['backend']['revision']
pipeline_health=json.loads(docker('exec','spaceapps-pipeline-1','/opt/inference-venv/bin/python','-c',
    'import urllib.request;print(urllib.request.urlopen("http://127.0.0.1:8002/health",timeout=15).read().decode())'))
assert pipeline_health['status']=='ok','pipeline direct health'
result['services']['pipeline']={'revision':result['services']['backend']['revision'],
    'image_id':pipeline['Image'],'same_image_as_backend':True,'health':'healthy','direct_health_verified':True}
data=json.loads(docker('exec','spaceapps-api-1','/opt/inference-venv/bin/python','-c',
    'import hashlib,sys,json,pathlib,importlib.metadata as m;'
    'root=pathlib.Path("/app/inference");h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();'
    'print(json.dumps(dict(python=sys.version.split()[0],model_sha256=h(root/"models/ranker.onnx"),'
    'metadata_sha256=h(root/"models/metadata.json"),runtime_sha256={p.name:h(p)for p in (root/"ml_inference").glob("*.py")},'
    'versions={n:m.version(n)for n in ("numpy","scipy","astropy","onnxruntime","onnx","pillow")},'
    'training_packages=sorted({d.metadata["Name"].lower()for d in m.distributions()} & {"scikit-learn","skl2onnx","torch","xgboost","lightgbm"}))))'))
assert data['model_sha256']=='c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
assert data['metadata_sha256']==EXPECTED_METADATA
assert data['runtime_sha256']==EXPECTED_RUNTIME
assert not data['training_packages']
result.update(data)
bindings=docker('port','spaceapps-api-1','50051/tcp').splitlines()
assert bindings and all(b.startswith('127.0.0.1:') or b.startswith('[::1]:') for b in bindings),bindings
result['private_grpc_binding']=bindings
print(json.dumps(result,indent=2))
