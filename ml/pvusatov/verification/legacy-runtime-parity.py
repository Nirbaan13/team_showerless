"""Compare original v2 CLI and profile-aware runtime without fitting or final data."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

namespace = Path(__file__).resolve().parents[1]
packages = dict(archived=namespace/'releases/v2/backend/inference',
                active=namespace/'backend/inference')
sha = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(p/'models/ranker.onnx') == 'dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9'
           for p in packages.values()), 'Run before replacing the active v2 installation'
proof = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),
             designation='Local working-tree legacy compatibility, not a deployed v3 claim',
             source_sha256={str(p.relative_to(namespace)):sha(p)
                            for base in packages.values()
                            for p in [base/'ml_inference/model.py',base/'ml_inference/pipeline.py']}, cases={})
with tempfile.TemporaryDirectory(prefix='spaceapps-v2-cli-parity-') as scratch:
    root = Path(scratch)
    for preset in ['comet-d6','comet-d2','vesta-d6','vesta-d3']:
        results = {}
        for kind, package in packages.items():
            request = root/(preset+'-'+kind+'.json')
            request.write_text(json.dumps(dict(schema_version=1,analysis_id='legacy-parity',
                                              source=dict(kind='preset',preset_id=preset))))
            output = root/(preset+'-'+kind)
            env = {**os.environ,'PYTHONPATH':str(package),'PYTHONDONTWRITEBYTECODE':'1',
                   'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
            child = subprocess.run([sys.executable,'-m','ml_inference','--request',str(request),
                                    '--output',str(output)],cwd=package,env=env,
                                   capture_output=True,text=True,timeout=120)
            assert child.returncode == 0, (preset,kind,child.stderr)
            result = json.loads((output/'result.json').read_text())
            resources = {r['name']:sha(output/r['name']) for r in result['resources']}
            results[kind] = (result,resources)
        assert results['archived'] == results['active'], preset+' legacy output changed'
        result,resources = results['active']
        proof['cases'][preset] = dict(result_equal=True,all_resource_hashes_equal=True,
                                      frames=len(result['frames']),candidates=len(result['candidates']),
                                      resources=len(resources),algorithm_version=result['algorithm_version'])
destination = Path(__file__).with_name('legacy-runtime-parity-proof.json')
destination.write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof,indent=2))
