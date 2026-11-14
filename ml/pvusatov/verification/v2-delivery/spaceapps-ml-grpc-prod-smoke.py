import json
from pathlib import Path
import subprocess
import time
import urllib.request

root=Path('/home/usatovpavel/.codex/worktrees/spaceapps-zio-backend/backend')
command=['/tmp/spaceapps-grpc-v2/grpcurl','-plaintext','-import-path',str(root/'src/main/protobuf'),
         '-import-path',str(root/'target/protobuf_external'),'-proto','spaceapps/retrieval/v1/retrieval.proto']
def rpc(method,data):
    completed=subprocess.run(command+['-d',json.dumps(data),'127.0.0.1:15057',
                              'spaceapps.retrieval.v1.AnalysisService/'+method],capture_output=True,text=True,timeout=120)
    assert completed.returncode==0,completed.stderr
    return json.loads(completed.stdout)
models=rpc('GetModels',{})
assert models['models'][0]['model_id']=='spherex-track-rf-v2'
assert len(rpc('GetPresets',{})['presets'])==4
job=rpc('SubmitAnalysis',{'preset':'comet-d2'})
deadline=time.monotonic()+120
while job['status'] not in ('COMPLETED','FAILED'):
    assert time.monotonic()<deadline,job
    time.sleep(.25)
    job=rpc('GetAnalysis',{'analysisId':job['id']})
assert job['status']=='COMPLETED',job
with urllib.request.urlopen('http://144.124.238.101/api/analyses/'+job['id'],timeout=15) as response:
    http=json.load(response)
assert http['result']==job['result']
assert len(job['result']['frames'])==3 and job['result']['candidates']
watch=subprocess.run(command+['-d',json.dumps({'analysisId':job['id']}),'127.0.0.1:15057',
                             'spaceapps.retrieval.v1.AnalysisService/WatchAnalysis'],capture_output=True,text=True,timeout=30)
assert watch.returncode==0 and 'COMPLETED' in watch.stdout,watch.stderr
proof=dict(job_id=job['id'],frames=len(job['result']['frames']),candidates=len(job['result']['candidates']),
           model_sha256=job['result']['model']['sha256'],http_grpc_result_equal=True,
           completed_watch_replays=True)
Path('/tmp/spaceapps-ml-grpc-prod-proof.json').write_text(json.dumps(proof,indent=2))
print(json.dumps(proof,indent=2))
