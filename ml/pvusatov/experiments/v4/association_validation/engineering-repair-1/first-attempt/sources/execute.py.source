"""Root-anchored exact-source entry point; source preparation alone is not a run."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def bootstrap(path,anchor):
    path=Path(path).resolve();raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=anchor:raise ValueError('external research anchor differs before execution')
    value=json.loads(raw);ref=value['sources']['freeze'];source=Path(ref['path']).read_bytes()
    if len(source)>2*1024**2 or hashlib.sha256(source).hexdigest()!=ref['sha256']:raise ValueError('research validator source differs')
    spec=importlib.util.spec_from_file_location('association_checked_freeze',ref['path']);module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module;exec(compile(source,ref['path'],'exec'),module.__dict__);module.__source_sha256__=ref['sha256']
    frozen=module.validate(path,anchor)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=frozen['sources']['execute']['sha256']:raise ValueError('checked entry point differs')
    return frozen,module


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',required=True);p.add_argument('--anchor',required=True)
    p.add_argument('--kind',required=True,choices=('synthetic','native','report'));p.add_argument('--output',required=True)
    p.add_argument('--handoff');p.add_argument('--handoff-sha256');p.add_argument('--authorize-native',action='store_true')
    p.add_argument('--synthetic-manifest');p.add_argument('--native-manifest');a=p.parse_args()
    frozen,validator=bootstrap(a.freeze,a.anchor)
    runner=validator.exact('association_checked_runner',frozen['sources']['runner'])
    print(runner.run(a,frozen,validator))
