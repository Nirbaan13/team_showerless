"""Bind opaque native bytes to the prospectively audited V4 parent cohort.

Standard library only. Reads hash-bound JSON download manifests, never FITS.
The six-decimal acquisition MJD precision allows .0864 s; immutable prepare
serializes UTC at millisecond precision, allowing .0011 s against header MJD.
Neither tolerance authorizes changed source intervals or observation identities.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib,json,math
from pathlib import Path
from numbers import Real

ACQUISITION_SHA='55e0203db48bc294c6b1f4999d0582d1d9030d9e3e1b558d9f00364ac797e6cd'
AUDIT_SHA='f0361395a0787ba4140238d714acc2da693db077a2a7700fc0709b572540ea44'
HANDOFF_SHA='f8898016db7fda2b74c59099b09c3ea864b5b1d39312273f06831915c9990afa'
ACQUISITION_SECONDS=.0864
PREPARE_SECONDS=.0011
DAY_SECONDS=86400.


def _fail(message):raise ValueError('native acquisition binding: '+message)
def _finite(value):return isinstance(value,Real)and not isinstance(value,bool)and math.isfinite(value)
def _index(rows,key):
    if not isinstance(rows,list):_fail('metadata list missing')
    result={}
    for row in rows:
        name=row.get(key)
        if not isinstance(name,str)or not name or name in result:_fail('duplicate/missing '+key)
        result[name]=row
    return result

def _json_manifest(ref):
    path=Path(ref['path'])
    if path.suffix.lower()!='.json':_fail('downloads manifest is not JSON')
    with path.open('rb')as handle:blob=handle.read(2*1024*1024+1)
    if len(blob)>2*1024*1024 or hashlib.sha256(blob).hexdigest()!=ref['sha256']:_fail('downloads manifest byte hash differs')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:_fail('duplicate downloads JSON key')
            result[key]=value
        return result
    def invalid(value):_fail('nonfinite downloads JSON')
    rows=json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)
    if not isinstance(rows,list)or len(rows)!=8:_fail('exact original eight observations required')
    return path,rows


def validate_data_bindings(frozen,plan,audit,development_handoff):
    """Return {parent_id: audited expected metadata} after opaque preflight.

    Caller must pass documents read from the hash-checked provenance references.
    `_observations` must be the resolved rows which will enter preparation.
    """
    refs=frozen.get('provenance',{})
    for key,expected in [('acquisition_plan',ACQUISITION_SHA),('data_audit',AUDIT_SHA),('development_handoff',HANDOFF_SHA)]:
        if refs.get(key,{}).get('sha256')!=expected:_fail('original '+key+' provenance differs')
    if (audit.get('complete')is not True or audit.get('plan_sha256')!=ACQUISITION_SHA
            or audit.get('development_handoff_sha256')!=HANDOFF_SHA
            or audit.get('header_time_precision_tolerance_seconds')!=ACQUISITION_SECONDS
            or audit.get('independent_parent_counts')!={'train':8,'validation':8,'final':12}
            or audit.get('native_mefs')!=224 or audit.get('unique_physical_obsids')!=224
            or audit.get('final_pixels_opened')is not False or audit.get('final_pixel_reader_called')is not False):_fail('incomplete or inconsistent original audit')
    if(development_handoff.get('plan_sha256')!=ACQUISITION_SHA or development_handoff.get('pending_development')!=[]
            or development_handoff.get('cross_parent_obsid_overlap')!=0 or development_handoff.get('final_pixels_opened')is not False):_fail('development handoff incomplete')
    declared=_index(plan.get('groups'),'parent_id');audited=_index(audit.get('parents'),'parent_id');development=_index(development_handoff.get('groups'),'parent_id')
    names={f'v4-{kind}{i:02}'for kind,count in [('train',8),('validation',8),('final',12)]for i in range(1,count+1)}
    if set(declared)!=names or set(audited)!=names:_fail('original 28 parent declarations differ')
    expected_dev={name for name,g in declared.items()if g['split']in('train','validation')}
    if set(development)!=expected_dev:_fail('exact sixteen development parents required')
    prior=plan.get('excluded_physical_obsids')
    if not isinstance(prior,list)or len(prior)!=210 or len(set(prior))!=210:_fail('original prior exclusion set differs')
    all_rows=audit.get('observations');by_parent={name:[]for name in names};ids=set();hashes=set()
    if not isinstance(all_rows,list)or len(all_rows)!=224:_fail('exact 224 audited observations required')
    for row in all_rows:
        name=row.get('parent_id');identifier=row.get('physical_obsid');checksum=row.get('sha256')
        if name not in declared or identifier in ids or checksum in hashes or identifier in prior:_fail('reused or unknown audited physical observation/bytes')
        ids.add(identifier);hashes.add(checksum);group=declared[name];parent=audited[name];header=row.get('header_integrity',{})
        if (row.get('split')!=group['split']or parent.get('split')!=group['split']or row.get('detector')!=parent.get('detector')
                or row.get('detector')not in(1,2,3)or header.get('physical_obsid')!=identifier or header.get('detector')!=row['detector']
                or header.get('midpoint_mjd')!=row.get('midpoint_mjd')or not _finite(row.get('midpoint_mjd'))
                or header.get('header_only')is not True or header.get('pixels_opened')is not False
                or header.get('epsf_detcoord')!='sky'or header.get('epsf_oversampling')!=[5,5]):_fail('audited header/physical/detector/split identity differs')
        by_parent[name].append(row)
    for name,rows in by_parent.items():
        if len(rows)!=8 or audited[name].get('native_epochs')!=8 or any(b['midpoint_mjd']<=a['midpoint_mjd']for a,b in zip(rows,rows[1:])):_fail('audited ordered eight-epoch map differs')
        if name in development:
            group=development[name]
            if (group.get('split')!=declared[name]['split']or group.get('center_deg')!=declared[name]['center']or group.get('detector')!=audited[name]['detector']
                    or group.get('physical_obsids')!=[r['physical_obsid']for r in rows]
                    or group.get('downloads_manifest',{}).get('sha256')!=audited[name]['downloads_manifest']['sha256']
                    or group.get('header_integrity')!=[r['header_integrity']for r in rows]):_fail('development handoff mapping differs')
    parents=frozen.get('native',{}).get('parents',[]);frozen_names=[p.get('parent_id')for p in parents]
    if not parents or len(set(frozen_names))!=len(parents):_fail('duplicate or missing frozen parents')
    scope=frozen.get('scope')
    if scope=='development'and any(name not in expected_dev for name in frozen_names):_fail('DEVELOPMENT cannot alias a FINAL or unknown parent')
    if scope=='final'and frozen_names!=[f'v4-final{i:02}'for i in range(1,13)]:_fail('exact twelve FINAL parents required')
    if scope not in('development','final'):_fail('unknown evaluation scope')
    exclusions=frozen['native'].get('excluded_physical_obsids')
    if not isinstance(exclusions,list)or len(exclusions)!=len(set(exclusions)):_fail('invalid physical exclusion set')
    if scope=='final':
        required=set(prior)|{r['physical_obsid']for r in all_rows if r['split']in('train','validation')}
        if len(required)!=338 or set(exclusions)!=required:_fail('exact prior210 plus development128 exclusion set required')
    result={};used_ids=set();used_hashes=set()
    for parent in parents:
        name=parent['parent_id'];rows=by_parent[name];original=audited[name];ref=parent.get('downloads_manifest',{})
        if parent.get('center_deg')!=declared[name]['center']:_fail('prospective parent center differs')
        if ref.get('sha256')!=original['downloads_manifest']['sha256']:_fail('original parent manifest hash differs')
        path,manifest=_json_manifest(ref);resolved=parent.get('_observations')
        if not isinstance(resolved,list)or len(resolved)!=8:_fail('resolved eight-epoch list differs')
        expected=[]
        for raw,current,record in zip(manifest,resolved,rows):
            for key in ('obs_id','sha256','detector','t_min_mjd','t_max_mjd','url','bytes'):
                if current.get(key)!=raw.get(key):_fail('resolved row changed: '+key)
            identifier=raw.get('obs_id');checksum=raw.get('sha256');t0,t1=raw.get('t_min_mjd'),raw.get('t_max_mjd');midpoint=record['midpoint_mjd']
            if (identifier!=record['physical_obsid']or checksum!=record['sha256']or raw.get('detector')!=record['detector']
                    or raw.get('bytes')!=record['bytes']or raw.get('url')!=record['url']or identifier in used_ids or checksum in used_hashes or identifier in exclusions):_fail('wrong/repeated physical ID, detector, bytes or source URL')
            if (not _finite(t0)or not _finite(t1)or t1<=t0 or not t0-ACQUISITION_SECONDS/DAY_SECONDS<=midpoint<=t1+ACQUISITION_SECONDS/DAY_SECONDS
                    or abs((t0+t1)/2-midpoint)*DAY_SECONDS>ACQUISITION_SECONDS):_fail('physical midpoint versus acquisition interval differs')
            native=Path(raw['path']);native=native.resolve()if native.is_absolute()else(path.parent/native).resolve();frame_id=native.stem
            if (Path(current['path']).resolve()!=native or current.get('frame_id')!=frame_id or current.get('observation_id')!=identifier
                    or current.get('access_url')!=raw.get('url')):_fail('resolved frame/source mapping differs')
            used_ids.add(identifier);used_hashes.add(checksum)
            expected.append(dict(obs_id=identifier,sha256=checksum,detector=record['detector'],frame_id=frame_id,midpoint_mjd=midpoint,t_min_mjd=t0,t_max_mjd=t1))
        result[name]=dict(parent_id=name,split=declared[name]['split'],center_deg=list(declared[name]['center']),detector=original['detector'],observations=expected,acquisition_precision_seconds=ACQUISITION_SECONDS,prepare_precision_seconds=PREPARE_SECONDS)
    return result


def validate_prepared_frames(expected,frames,times_hours):
    """Check actual prepared FITS identities/absolute times before injections."""
    rows=expected['observations']
    if len(frames)!=len(rows)or len(times_hours)!=len(rows):_fail('prepared frame/time count differs')
    actual=[]
    for row,frame in zip(rows,frames):
        if (frame.get('frame_id')!=row['frame_id']or frame.get('physical_observation_id')!=row['obs_id']
                or frame.get('observation_id')!=f"{row['obs_id']}:D{row['detector']}"or frame.get('detector')!=row['detector']
                or frame.get('sha256')!=row['sha256']):_fail('actual FITS physical/frame/detector/hash identity differs')
        value=frame.get('midpoint_mjd')
        if not _finite(value)or abs(value-row['midpoint_mjd'])*DAY_SECONDS>PREPARE_SECONDS:_fail('actual FITS absolute midpoint differs')
        try:
            utc=datetime.fromisoformat(frame['midpoint_utc'].replace('Z','+00:00'))
            if utc.tzinfo is None:raise ValueError('missing timezone')
            mjd=(utc.astimezone(timezone.utc)-datetime(1858,11,17,tzinfo=timezone.utc)).total_seconds()/DAY_SECONDS
        except (ValueError,TypeError,KeyError,AttributeError):_fail('invalid actual midpoint UTC')
        if abs(mjd-value)*DAY_SECONDS>PREPARE_SECONDS:_fail('actual UTC/MJD midpoint mismatch')
        actual.append(value)
    if any(b<=a for a,b in zip(actual,actual[1:])):_fail('actual midpoints are not increasing')
    for value,mjd in zip(times_hours,actual):
        if not _finite(value)or abs(value-(mjd-actual[0])*24)>1e-9:_fail('relative preparation time differs from physical dates')
