"""Prospective fixed narrower TIME-domain retry; no case substitution."""
from pathlib import Path
import datetime, hashlib, importlib.util, json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

OWN=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    out=OWN/'time-window';raw=Path('/tmp/spaceapps-v4-association-holdout/time-window')
    if out.exists()or raw.exists():raise ValueError('Evidence paths must be new')
    plan=json.loads((OWN/'plan.json').read_text())
    amendment=dict(declared_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),root_authorization='2026-11-15 root approved same12centers fixed2025-07-01..2025-08-15 TIME amendment before anymetadata rows/pixels',
                   original_plan_sha256=sha(OWN/'plan.json'),prior_incomplete_state_sha256=sha(OWN/'initial-transport-state.json'),
                   role='Explicitly narrower NONEXHAUSTIVE acquisition domain, not globally equivalent to failed all-time search',
                   time_utc=['2025-07-01T00:00:00','2025-08-15T00:00:00'],time_mjd=[60857,60902],
                   changed_parameters=dict(TIME='60857 60902',MAXREC=4096),max_query_urls=12,max_workers=2,max_attempts_per_url=2,
                   overflow_policy='A truncated4096row response is incomplete; no extra query or selection',
                   unchanged='Exact12parentcoordinates, ordering,8physicalepochs,detector/cadence rules,exclusions,budgets/deadline; no replacements',
                   native_seed_reservation={g['group_id']:4110001+i for i,g in enumerate(plan['groups'])},
                   pixels_opened=False,inference_authorized=False,source_sha256=sha(__file__))
    out.mkdir();raw.mkdir()
    for p in [out/'amendment.json',raw/'amendment.json']:p.write_text(json.dumps(amendment,indent=2)+'\n')
    for p in [out/'plan.json',raw/'plan.json']:p.write_bytes((OWN/'plan.json').read_bytes())
    spec=importlib.util.spec_from_file_location('fixed_association_time',OWN/'acquire_holdout.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    original=m.fetch;seen=set()
    def fetch(url,*args,**kwargs):
        parts=urlsplit(url)
        if parts.path=='/SIA':
            params=dict(parse_qsl(parts.query));params.update(TIME='60857 60902',MAXREC='4096')
            actual=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(params),parts.fragment))
            if actual in seen:raise ValueError('Declared oneURL/parent exhausted or overflow; do notquery/claimno-coverage')
            seen.add(actual)
            return original(actual,*args,**kwargs)
        return original(url,*args,**kwargs)
    m.fetch=fetch;m.OWN=out;m.RAW=raw;m.run()
    report=json.loads((out/'byte-header-audit.json').read_text())
    state=dict(status='COMPLETE_QUARANTINED_SUBSET'if report['downloaded_files']and report['downloaded_files']==report['selected_metadata_groups']*8 else'INCOMPLETE_OR_NO_ELIGIBLE_GROUPS',
               amendment_sha256=sha(out/'amendment.json'),audit_sha256=sha(out/'byte-header-audit.json'),
               exact_query_urls=len(seen),counts={k:report[k]for k in ['groups_planned','selected_metadata_groups','downloaded_files','bytes']},
               missing_remain_planned=True,pixels_opened=False,inference_authorized=False,selection_not_exhaustive_full_archive=True)
    (out/'state.json').write_text(json.dumps(state,indent=2)+'\n')

if __name__=='__main__':main()
