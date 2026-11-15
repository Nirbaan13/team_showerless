"""Append-only exact-domain acquisition retry; transport encoding only."""
from pathlib import Path
import datetime,json,hashlib,importlib.util

OWN=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    out=OWN/'retry-percent20';raw=Path('/tmp/spaceapps-v4-association-holdout/retry-percent20')
    if out.exists()or raw.exists():raise ValueError('Retry evidence must be new')
    plan=json.loads((OWN/'plan.json').read_text());old=json.loads((OWN/'byte-header-audit.json').read_text())
    assert old['selected_metadata_groups']==0 and old['downloaded_files']==0
    amendment=dict(declared_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),original_plan_sha256=sha(OWN/'plan.json'),original_audit_sha256=sha(OWN/'byte-header-audit.json'),
                   reason='All original SIA requests returned upstream HTTP502 ProxyError; no coverage inference or raw selection occurred',
                   change='Same exact URL parameters/domain, spaces encoded as literal%20 instead of+; original acquisition implementation imported read-only',
                   preserved='12fixed centers, metadata eligibility/order, physical exclusions, byte budget/global deadline, no replacements/no pixels',
                   native_seed_reservation={g['group_id']:4110001+i for i,g in enumerate(plan['groups'])},
                   superseded_unexecuted_seed_reservation='3900001..3900012 overlaps prior synthetic; no injection ever drawn; ROOT assigned4110001..4110012',
                   source_sha256=sha(__file__))
    out.mkdir();raw.mkdir()
    for p in [out/'amendment.json',raw/'amendment.json']:p.write_text(json.dumps(amendment,indent=2)+'\n')
    for p in [out/'plan.json',raw/'plan.json']:p.write_bytes((OWN/'plan.json').read_bytes())
    spec=importlib.util.spec_from_file_location('fixed_association_acquire',OWN/'acquire_holdout.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original_fetch=module.fetch
    def encoded_fetch(url,*args,**kwargs):return original_fetch(url.replace('+','%20'),*args,**kwargs)
    module.fetch=encoded_fetch;module.OWN=out;module.RAW=raw
    module.run()

if __name__=='__main__':main()
