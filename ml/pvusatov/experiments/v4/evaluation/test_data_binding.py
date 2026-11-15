"""Portable audited metadata fixtures only; never read native FITS."""
import copy
from datetime import datetime,timedelta,timezone
import hashlib,importlib.util,json
from pathlib import Path
import pytest

HERE=Path(__file__).resolve().parent;DATA=HERE.parent/'data'
SPEC=importlib.util.spec_from_file_location('v4_data_binding_tested',HERE/'data_binding.py');binding=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(binding)

def fixture(scope='development'):
    plan=json.loads((DATA/'partition-plan.json').read_text());audit=json.loads((DATA/'complete-audit.json').read_text());handoff=json.loads((DATA/'development-handoff.json').read_text());groups={r['parent_id']:r for r in plan['groups']}
    ids=['v4-train04']if scope=='development'else[f'v4-final{i:02}'for i in range(1,13)];parents=[]
    for name in ids:
        path=DATA/'manifests'/('quarantine_final'if scope=='final'else'development')/(name+'-downloads.json');rows=json.loads(path.read_text());observations=[]
        for row in rows:
            observations.append({**row,'path':str(Path(row['path']).resolve()),'frame_id':Path(row['path']).stem,'observation_id':row['obs_id'],'access_url':row['url']})
        parents.append(dict(parent_id=name,center_deg=groups[name]['center'],downloads_manifest=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()),_observations=observations))
    prior=set(plan['excluded_physical_obsids']);dev={r['physical_obsid']for r in audit['observations']if r['split']in('train','validation')};excluded=sorted(prior|dev)if scope=='final'else sorted(prior)
    provenance={key:dict(path=str(DATA/name),sha256=hashlib.sha256((DATA/name).read_bytes()).hexdigest())for key,name in [('acquisition_plan','partition-plan.json'),('data_audit','complete-audit.json'),('development_handoff','development-handoff.json')]}
    return dict(scope=scope,provenance=provenance,native=dict(parents=parents,excluded_physical_obsids=excluded)),plan,audit,handoff

def prepared(expected):
    rows=expected['observations'];first=rows[0]['midpoint_mjd'];frames=[]
    for row in rows:
        utc=(datetime(1858,11,17,tzinfo=timezone.utc)+timedelta(days=row['midpoint_mjd'])).isoformat().replace('+00:00','Z')
        frames.append(dict(frame_id=row['frame_id'],observation_id=f"{row['obs_id']}:D{row['detector']}",physical_observation_id=row['obs_id'],detector=row['detector'],sha256=row['sha256'],midpoint_mjd=row['midpoint_mjd'],midpoint_utc=utc))
    return frames,[(r['midpoint_mjd']-first)*24 for r in rows]

def test_exact_development_metadata_and_frames_without_fits_reads(monkeypatch):
    args=fixture();original=Path.open
    def opened(path,*a,**kw):
        if path.suffix.lower()in('.fit','.fits','.fts'):raise AssertionError('FITS opened')
        return original(path,*a,**kw)
    monkeypatch.setattr(Path,'open',opened);expected=binding.validate_data_bindings(*args)['v4-train04'];frames,times=prepared(expected);binding.validate_prepared_frames(expected,frames,times)

def test_exact_final_12_by8_metadata_and338_exclusions_without_pixels():
    args=fixture('final');expected=binding.validate_data_bindings(*args);assert len(expected)==12;assert sum(len(v['observations'])for v in expected.values())==96

@pytest.mark.parametrize('column,value',[('obs_id','fake-identity'),('sha256','f'*64),('detector',2),('t_min_mjd',1.),('t_max_mjd',1.)])
def test_changed_resolved_observation_mapping_rejects(column,value):
    args=fixture();args[0]['native']['parents'][0]['_observations'][0][column]=value
    with pytest.raises(ValueError):binding.validate_data_bindings(*args)

def test_changed_parent_center_manifest_and_duplicate_parent_reject():
    for change in ['center','manifest','duplicate']:
        args=fixture();parent=args[0]['native']['parents'][0]
        if change=='center':parent['center_deg']=[parent['center_deg'][0]+.01,parent['center_deg'][1]]
        elif change=='manifest':parent['downloads_manifest']['sha256']='0'*64
        else:args[0]['native']['parents'].append(copy.deepcopy(parent))
        with pytest.raises(ValueError):binding.validate_data_bindings(*args)

def test_dev_final_alias_rejects_before_any_manifest_read(monkeypatch):
    args=fixture('final');args[0]['scope']='development'
    monkeypatch.setattr(Path,'read_bytes',lambda *a:(_ for _ in()).throw(AssertionError('late manifest access')))
    monkeypatch.setattr(Path,'open',lambda *a,**kw:(_ for _ in()).throw(AssertionError('late manifest access')))
    with pytest.raises(ValueError,match='DEVELOPMENT|development'):binding.validate_data_bindings(*args)

def test_final_dummy_exclusions_same_count_reject():
    args=fixture('final');args[0]['native']['excluded_physical_obsids']=[f'dummy-{i}'for i in range(338)]
    with pytest.raises(ValueError,match='exclusion'):binding.validate_data_bindings(*args)

def test_audit_repeated_hash_or_physicalid_rejects():
    for column in ['sha256','physical_obsid']:
        args=fixture();args[2]['observations'][1][column]=args[2]['observations'][0][column]
        with pytest.raises(ValueError):binding.validate_data_bindings(*args)

@pytest.mark.parametrize('change',['physical','detector','hash','utc','absolute_time','relative_time','order'])
def test_actual_prepared_identity_and_absolute_relative_times_reject(change):
    expected=binding.validate_data_bindings(*fixture())['v4-train04'];frames,times=prepared(expected)
    if change=='physical':frames[0]['physical_observation_id']='fake'
    elif change=='detector':frames[0]['detector']=2
    elif change=='hash':frames[0]['sha256']='0'*64
    elif change=='utc':frames[0]['midpoint_utc']='2000-01-01T00:00:00Z'
    elif change=='absolute_time':
        for f in frames:f['midpoint_mjd']+=1000;f['midpoint_utc']=(datetime(1858,11,17,tzinfo=timezone.utc)+timedelta(days=f['midpoint_mjd'])).isoformat()
    elif change=='relative_time':times[1]+=.01
    else:frames.reverse()
    with pytest.raises(ValueError):binding.validate_prepared_frames(expected,frames,times)

def test_prepared_numpy_time_array_is_supported_without_importing_numpy_in_guard():
    import numpy as np
    expected=binding.validate_data_bindings(*fixture())['v4-train04'];frames,times=prepared(expected)
    binding.validate_prepared_frames(expected,frames,np.asarray(times,dtype=np.float64))
