"""One final exact-domain retry, preserving every preceding failure."""
from pathlib import Path
import datetime, hashlib, importlib.util, json, time

OWN=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    out=OWN/'final-exact-retry';raw=Path('/tmp/spaceapps-v4-association-holdout/final-exact-retry')
    if out.exists()or raw.exists():raise ValueError('Retry evidence paths must be new')
    plan=json.loads((OWN/'plan.json').read_text())
    amendment=dict(declared_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   original_plan_sha256=sha(OWN/'plan.json'),
                   role='ROOT-authorized ONE final all-time exact-domain retry after fixedTIME also failed; no field/eligibility replacement',
                   not_before_utc='2026-11-15T11:15:00+00:00',deadline_utc=plan['acquisition']['deadline_utc'],
                   native_seed_reservation={g['group_id']:4110001+i for i,g in enumerate(plan['groups'])},
                   pixels_opened=False,inference_authorized=False,source_sha256=sha(__file__))
    out.mkdir();raw.mkdir()
    for p in [out/'amendment.json',raw/'amendment.json']:p.write_text(json.dumps(amendment,indent=2)+'\n')
    for p in [out/'plan.json',raw/'plan.json']:p.write_bytes((OWN/'plan.json').read_bytes())
    start=datetime.datetime.fromisoformat(amendment['not_before_utc']).timestamp()
    while time.time()<start:time.sleep(min(1.,start-time.time()))
    spec=importlib.util.spec_from_file_location('final_exact_association',OWN/'acquire_holdout.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.OWN=out;m.RAW=raw;m.run()

if __name__=='__main__':main()
