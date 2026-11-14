"""Read-only VPS inspection plus exactly one temporary candidate container."""
from __future__ import annotations
from datetime import datetime,timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

EXPECTED={'ranker.onnx':'c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204','metadata.json':'983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04','parity-reference.json':'53bb2b7aefc79d7b5a17613a25eb0a365a221fc34008d0d87decf6792ee3b89f'}


def docker_json(*args):return json.loads(subprocess.check_output(['docker',*args],text=True))


def backend():
    c=docker_json('inspect','spaceapps-api-1')[0];assert c['State']['Running']
    return dict(container_id=c['Id'],image_id=c['Image'],revision=c['Config']['Labels'].get('org.opencontainers.image.revision'),health=c['State'].get('Health',{}).get('Status'))


def main():
    config=json.load(sys.stdin);source=config['container_probe_source'];assert hashlib.sha256(source.encode()).hexdigest()==config['container_probe_sha256']
    assert set(config['files'])==set(EXPECTED)
    before=backend();image=docker_json('image','inspect',before['image_id'])[0];assert image['Id']==before['image_id']
    run_id=uuid.uuid4().hex[:12];name='spaceapps-candidate-probe-'+run_id;folder=Path(tempfile.mkdtemp(prefix=name+'-'));os.chmod(folder,0o755)
    staged=[];result=None;forced_cleanup=False;started=time.perf_counter()
    try:
        for filename,expected in EXPECTED.items():
            payload=config['files'][filename];raw=base64.b64decode(payload['base64'],validate=True)
            assert 0<len(raw)<=16*1024**2 and hashlib.sha256(raw).hexdigest()==expected==payload['sha256']
            path=folder/filename;path.write_bytes(raw);os.chmod(path,0o444);staged.append(dict(name=filename,sha256=expected,bytes=len(raw)))
        command=['docker','run','--rm','--name',name,'--label','spaceapps.candidate.probe='+run_id,
            '--network','none','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=268435456,mode=1777',
            '--cpus=1','--memory=1g','--pids-limit=128','--volume',str(folder)+':/candidate:ro',
            '--env','OPENBLAS_NUM_THREADS=1','--env','OMP_NUM_THREADS=1','--env','MKL_NUM_THREADS=1','--env','NUMEXPR_NUM_THREADS=1',
            '--entrypoint','/opt/inference-venv/bin/python',before['image_id'],'-u','-c',source]
        try:
            done=subprocess.run(command,text=True,capture_output=True,timeout=180);stdout,stderr,returncode=done.stdout,done.stderr,done.returncode;timed_out=False
        except subprocess.TimeoutExpired as exc:
            stdout=exc.stdout.decode() if isinstance(exc.stdout,bytes) else(exc.stdout or '');stderr=exc.stderr.decode() if isinstance(exc.stderr,bytes) else(exc.stderr or '');returncode=None;timed_out=True
        try:payload=json.loads(stdout)
        except (ValueError,TypeError):payload=None
        result=dict(container_name=name,docker_returncode=returncode,docker_timed_out=timed_out,docker_wall_seconds=time.perf_counter()-started,
            container_probe=payload,docker_stderr=stderr[:4096],unparsed_stdout=stdout[:4096] if payload is None else None)
    finally:
        try:
            remaining=subprocess.check_output(['docker','ps','-aq','--filter','name=^/'+name+'$'],text=True).strip()
            if remaining:
                forced_cleanup=True;subprocess.run(['docker','rm','-f',name],text=True,capture_output=True,check=True)
        finally:
            shutil.rmtree(folder)
    leftovers=subprocess.check_output(['docker','ps','-aq','--filter','label=spaceapps.candidate.probe='+run_id],text=True).strip();assert not leftovers
    after=backend()
    report=dict(schema_version=1,checked_at_utc=datetime.now(timezone.utc).isoformat(),run_id=run_id,backend_before=before,backend_after=after,
        pinned_image_id=before['image_id'],image_created=image['Created'],image_revision=image['Config']['Labels'].get('org.opencontainers.image.revision'),
        production_identity_unchanged=before==after,production_change_scope='No production exec/restart/write performed; any before/after difference is external to this probe',
        requested_limits=dict(cpus=1,memory_bytes=1073741824,pids=128,tmpfs_tmp_bytes=268435456,network='none',read_only_root=True,remove_after_exit=True,candidate_bind_read_only=True),
        uploaded_files=staged,probe_source_sha256=config['container_probe_sha256'],executed_probes=1,result=result,forced_cleanup=forced_cleanup,
        remote_staging_deleted=not folder.exists(),leftover_containers_for_run=0,production_service_changes_performed=False,final_data_or_labels_uploaded=False)
    print(json.dumps(report,allow_nan=False),flush=True)


if __name__=='__main__':main()
