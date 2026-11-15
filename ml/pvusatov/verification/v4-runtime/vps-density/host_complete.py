"""Repeat fixed density cases with final whole-cgroup accounting.

The first host probe recorded limits and child exits but sampled cgroup peak
only at startup. This separate attempt preserves it and closes that gap.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

BASE = Path('/opt/spaceapps/ml-pvusatov-v4-probe')
OUTPUT = BASE / 'evidence-density-complete-20261115'
NAME = 'spaceapps-v4-probe-density-complete-20261115'
IMAGE = 'spaceapps-ml-v4-deps-probe:20261115'
RUNNER = '''from pathlib import Path
import json,runpy,sys
root=Path('/sys/fs/cgroup')
read=lambda:{name:(root/name).read_text().strip() for name in ('memory.max','memory.swap.max','cpu.max','memory.peak','memory.events','cpu.stat')}
before=read()
assert before['memory.max']==str(1024**3) and before['memory.swap.max']=='0' and before['cpu.max']=='100000 100000'
sys.argv=['/density/portable.py','--runtime','/probe/inference','--model-dir','/probe/inference/models','--output','/evidence/density']
try:
    runpy.run_path('/density/portable.py',run_name='__main__')
finally:
    after=read()
    proof=dict(before=before,after=after,peak_mib=int(after['memory.peak'])/1024**2,scope='Whole container including generator, child, tmpfs, output and file cache')
    Path('/evidence/cgroup-final.json').write_text(json.dumps(proof,indent=2)+'\\n')
events=dict(line.split()for line in after['memory.events'].splitlines())
assert int(events['oom'])==0 and int(events['oom_kill'])==0
assert int(after['memory.peak'])<=1024**3
'''


def main():
    digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    code = BASE / 'density-code-20261115'
    manifest = code / 'code-manifest.json'
    assert digest(manifest) == '770a8b0c08c51947b38c111edfa61ef762ef030f6555540c6fa8eb17c55f5152'
    for row in json.loads(manifest.read_text())['files']:
        assert digest(code / row['path']) == row['sha256']
    assert subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',IMAGE],text=True).strip() == 'sha256:8df7927bd71083a8419454906591d25d1e203b73a84608e2bce1e941da352573'
    runner = BASE / 'density-resource-runner-20261115.py'
    if runner.exists():
        raise ValueError('Resource runner path already exists')
    runner.write_text(RUNNER)
    OUTPUT.mkdir()
    os.chown(OUTPUT, 10001, 10001)
    args = ['docker','create','--name',NAME,'--cpus','1','--memory','1g','--memory-swap','1g','--pids-limit','64',
            '--network','none','--read-only','--no-healthcheck','--tmpfs','/tmp:rw,size=512m,mode=1777',
            '--mount','type=bind,src='+str(BASE/'bundle-v3')+',dst=/probe,readonly',
            '--mount','type=bind,src='+str(code)+',dst=/density,readonly',
            '--mount','type=bind,src='+str(runner)+',dst=/resource-runner.py,readonly',
            '--mount','type=bind,src='+str(OUTPUT)+',dst=/evidence',
            '--env','PYTHONDONTWRITEBYTECODE=1','--env','OPENBLAS_NUM_THREADS=1','--env','OMP_NUM_THREADS=1','--env','MKL_NUM_THREADS=1',
            '--entrypoint','/opt/inference-venv/bin/python',IMAGE,'/resource-runner.py']
    subprocess.run(args,check=True,stdout=subprocess.PIPE,text=True)
    completed=subprocess.run(['docker','start','--attach',NAME],capture_output=True,text=True,timeout=1020)
    (OUTPUT/'stdout.log').write_text(completed.stdout)
    (OUTPUT/'stderr.log').write_text(completed.stderr)
    inspect=json.loads(subprocess.check_output(['docker','inspect',NAME],text=True))[0]
    proof=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),container=NAME,
        coordinator_sha256=digest(__file__),runner_sha256=digest(runner),image_id=inspect['Image'],
        docker_start_exit=completed.returncode,state=inspect['State'],
        limits={key:inspect['HostConfig'][key]for key in ('Memory','MemorySwap','NanoCpus','PidsLimit','NetworkMode','ReadonlyRootfs')},
        production_services_modified=False)
    for name in ('cgroup-final.json','density/portable-receipt.json'):
        path=OUTPUT/name
        if path.exists():proof[name]=dict(sha256=digest(path),value=json.loads(path.read_text()))
    (OUTPUT/'host-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof,indent=2))
    assert completed.returncode==0 and inspect['State']['ExitCode']==0 and not inspect['State']['OOMKilled']
    assert 'cgroup-final.json' in proof and 'density/portable-receipt.json' in proof


if __name__ == '__main__':
    main()
