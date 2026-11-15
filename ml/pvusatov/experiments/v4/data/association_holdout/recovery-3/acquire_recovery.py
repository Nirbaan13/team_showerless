"""Prospective metadata-informed footprint eligibility-order amendment; quarantine only."""
from pathlib import Path
from urllib.parse import urlsplit
import argparse, datetime, hashlib, json, shutil, types

OWN=Path(__file__).resolve().parent
PARENT=OWN.parent
PREVIOUS=PARENT/'recovery-2'
RAW=Path('/tmp/spaceapps-association-native-recovery2/recovery-3')

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()
def ref(path):return dict(path=str(path.resolve()),sha256=sha(path))
def read(path):return json.loads(Path(path).read_text())
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def checked(item):
    path=Path(item['path']);assert sha(path)==item['sha256'],str(path)
    return path
def exact(name,item):
    path=checked(item);m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m

def declare():
    if (OWN/'transport-plan.json').exists()or RAW.exists():raise ValueError('New evidence paths required')
    previous=read(PREVIOUS/'transport-plan.json');original=read(checked(previous['original_plan']));oldselected=read(PREVIOUS/'selection.json')
    cached={}
    for group in original['groups']:
        evidence=read(PREVIOUS/'query-evidence'/f"{group['group_id']}.json")
        discovery=read(checked(evidence['rows_ref']))
        if discovery['complete']:
            source=discovery['attempts'][-1]['source'];checked(source)
            cached[group['group_id']]=dict(source=source,discovery=evidence['rows_ref'],evidence=ref(PREVIOUS/'query-evidence'/f"{group['group_id']}.json"))
    assert set(cached)=={'association-holdout-'+i for i in ['03','04','06','07','10']}
    start=datetime.datetime.now(datetime.timezone.utc)
    plan=dict(previous,schema_version=3,declared_utc=start.isoformat(),deadline_utc=(start+datetime.timedelta(minutes=45)).isoformat(),wrapper=ref(Path(__file__)),
        authorization='Root explicitly authorized recovery-3 continuation: metadata-only footprint prefilter before unchanged temporal/detector selector; native inference remains unauthorized.',
        engine_source=ref(PREVIOUS/'acquire_recovery.py'),previous_guarded_handoff=ref(PREVIOUS/'guarded-handoff.json'),previous_selection=ref(PREVIOUS/'selection.json'),
        scientific_amendment=dict(change='Apply existing supported-POLYGON s_region maximum-vertex-distance <=4degree eligibility BEFORE unchanged acquire.select, rather than selecting8first then rejecting entire parent on4degree check.',
            disclosure='Metadata-informed protocol amendment after synthetic unblinding and recovery-2 metadata inspection, BEFORE ANY native pixels, models, features, quality scores, or native injections. Selected exposure identities may change; not equivalent to a transport-only retry.',
            unchanged='All12parentcoordinates,4110001..4110012seedmap,438physicalexclusions,4degree numerical bound,detectorpreferences,earliest3within1.5h,temporalspread8within48hthen168h,>=2hpreference,footprintpostcheck,ROI/pixelscale/mask,caps; no field replacement or bound relaxation.',
            cached_sources=cached,old_selected_identity_binding=ref(PREVIOUS/'selection.json'),root_native_release='All12ready plus separate exact external handoff hash and independent review required; not authorized here.'),
        cached_metadata=cached,retry_group_ids=[g['group_id']for g in original['groups']if g['group_id']not in cached],
        selection='Original physical-OBSID exclusion, then original <=4degree s_region footprint eligibility prefilter, then exact unchanged acquire.select detector/cadence/temporal rules; require8unique physicalexposures and recheck4degree bound. Record old/new IDs for cached5before transfer.',
        quarantine=dict(raw_root=str(RAW),header_only=True,pixels_opened=False,models_called=False,injections_generated=False,inference_authorized=False))
    plan['query']=dict(previous['query'],max_workers=2,max_attempts=2,timeout_seconds=90,transport_header='Cache-Control: no-cache on seven unresolved SIA requests only',network_group_ids=plan['retry_group_ids'],cached_group_ids=list(cached))
    RAW.mkdir()
    for path in [OWN/'transport-plan.json',RAW/'transport-plan.json']:write(path,plan)
    print(json.dumps(dict(amendment_sha256=sha(OWN/'transport-plan.json'),deadline_utc=plan['deadline_utc'],cached_metadata_groups=len(cached),retry_metadata_groups=len(plan['retry_group_ids']),native_inference_authorized=False)),flush=True)

def run():
    retry=read(OWN/'transport-plan.json');checked(retry['wrapper']);checked(retry['engine_source'])
    assert sha(OWN/'transport-plan.json')==sha(RAW/'transport-plan.json')
    for key in ['original_plan','native_seed_amendment','association_freeze','original_closed_handoff','previous_guarded_handoff','previous_selection']:checked(retry[key])
    original=read(retry['original_plan']['path']);oldselected={g['group_id']:g for g in read(retry['previous_selection']['path'])}
    for relative,digest in original['sources'].items():assert sha(PARENT.parent/relative)==digest
    modules={name:exact('recovery3_'+name,item)for name,item in retry['sources'].items()}
    h=modules['holdout'];old=modules['acquire'];original_select=old.select
    def amended_select(group,rows,excluded):
        eligible=[r for r in rows if h.footprint_radius(r['s_region'],group['center'])<=4.]
        result=original_select(group,eligible,excluded)
        before=oldselected[group['group_id']].get('exposures',[])
        result['footprint_prefilter']=dict(input_rows=len(rows),eligible_rows=len(eligible),rejected_rows=len(rows)-len(eligible),bound_deg=4.,eligible_supported_detector_counts={str(d):sum(r.get('energy_bandpassname')==f'SPHEREx-D{d}'and'/dr1/'in r.get('access_url','')for r in eligible)for d in [1,2,3]})
        result['old_vs_new_selection']=dict(cached_complete=group['group_id']in retry['cached_metadata'],old_metadata_obs_ids=[r['obs_id']for r in before],new_metadata_obs_ids=[r['obs_id']for r in result.get('exposures',[])],old_physical_obsids=[h.physical_id(r['obs_id'])for r in before],new_physical_obsids=[h.physical_id(r['obs_id'])for r in result.get('exposures',[])])
        return result
    old.select=amended_select
    original_fetch=h.fetch;original_request=h.Request
    cached_by_url={item['source']['url']:item for item in retry['cached_metadata'].values()}
    def no_cache_request(url,headers=None,**kwargs):
        headers=dict(headers or {})
        if urlsplit(url).path=='/SIA':headers['Cache-Control']='no-cache'
        return original_request(url,headers=headers,**kwargs)
    h.Request=no_cache_request
    def cached_fetch(url,path,cap,timeout,attempts,deadline):
        if url in cached_by_url:
            cached=cached_by_url[url];source=cached['source'];src=checked(source)
            path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,path)
            assert sha(path)==source['sha256'] and path.stat().st_size<=cap
            return dict(source,path=str(path),cached_from=source,cache_discovery=cached['discovery'],cache_reused=True)
        if urlsplit(url).path=='/SIA':
            assert any(f"CIRCLE+{g['center'][0]}+{g['center'][1]}+0.001"in url for g in original['groups']if g['group_id']in retry['retry_group_ids'])
        return original_fetch(url,path,cap,timeout,attempts,deadline)
    h.fetch=cached_fetch
    engine=exact('unchanged_recovery2_engine',retry['engine_source']);engine.OWN=OWN;engine.RAW=RAW
    engine.context=lambda:(retry,original,modules)
    engine.run()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['declare','run']);args=p.parse_args();declare()if args.command=='declare'else run()
