"""Run one candidate probe over strict authorized SSH; never expose credentials."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

EXPECTED={'ranker.onnx':'c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204','metadata.json':'983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04','parity-reference.json':'53bb2b7aefc79d7b5a17613a25eb0a365a221fc34008d0d87decf6792ee3b89f'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--key',default='/home/usatovpavel/.ssh/spaceapps-1gb-admin-20261115')
    parser.add_argument('--known-hosts',default='/home/usatovpavel/.local/state/spaceapps-migration-20261115-1gb/known_hosts');args=parser.parse_args()
    folder=Path(__file__).resolve().parent;probe=(folder/'candidate_container_probe.py').read_text();remote=(folder/'candidate_remote_runner.py').read_text()
    files={}
    for filename,digest in EXPECTED.items():
        raw=(args.candidate_dir/filename).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('candidate published checksum differs: '+filename)
        files[filename]=dict(sha256=digest,base64=base64.b64encode(raw).decode())
    config=dict(container_probe_source=probe,container_probe_sha256=hashlib.sha256(probe.encode()).hexdigest(),files=files)
    command=['ssh','-T','-i',args.key,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+args.known_hosts,'-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=4','root@146.103.122.246','python3 -c '+shlex.quote(remote)]
    done=subprocess.run(command,input=json.dumps(config),text=True,capture_output=True,timeout=600)
    if done.returncode:raise SystemExit('Candidate SSH probe failed: '+done.stderr[:4096])
    report=json.loads(done.stdout)
    report['driver_source_sha256']={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ['candidate_container_probe.py','candidate_remote_runner.py','candidate_run_ssh.py']}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    p=report['result'];success=p['docker_returncode']==0 and not p['docker_timed_out'] and p['container_probe'] and p['container_probe']['success']
    print(json.dumps(dict(output=str(args.output),success=bool(success),executed_probes=report['executed_probes'],pinned_image_id=report['pinned_image_id'],leftover_containers=report['leftover_containers_for_run'],remote_staging_deleted=report['remote_staging_deleted']),indent=2))
    if not success:raise SystemExit(2)


if __name__=='__main__':main()
