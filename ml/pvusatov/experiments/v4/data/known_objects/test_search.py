import importlib.util
from pathlib import Path
import pytest
p=Path(__file__).with_name('search.py')
s=importlib.util.spec_from_file_location('known_search',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_spherical_polygon_wrap_and_outside():
    region='POLYGON ICRS 359 -1 1 -1 1 1 359 1 359 -1'
    assert m.inside(region,[0,0]);assert not m.inside(region,[180,0]);assert not m.inside(region,[0,2])

def test_horizons_astrometric_csv_and_distance():
    text='Target body name: 1 Ceres\nCenter-site name: GEOCENTRIC\nR.A.___(ICRF) DEC____(ICRF)\n$$SOE\n 2025-May-01 00:00:00.000,2460796.5,,,358.3,-10.1,3.5,-16.9,\n$$EOE'
    rows=m.parse_horizons({'result':text},'Ceres');assert rows[0]['mjd']==60796.;assert rows[0]['range_au']==3.5
    with pytest.raises(ValueError):m.parse_horizons({'error':'no ephemeris'},'Ceres')

def test_common_roi_corner_reject():
    rows=[dict(s_region='POLYGON ICRS 9.99 -0.02 10.01 -0.02 10.01 0.02 9.99 0.02',t_min='60000',t_max='60000.0001')]*3
    points=[dict(ra_deg=10,dec_deg=0)]*3
    assert m.common_roi(rows,points) is None
    for r in rows:r['s_region']='POLYGON ICRS 9 -1 11 -1 11 1 9 1'
    assert m.common_roi(rows,points)['center'][0]==pytest.approx(10)

def test_nonconvex_footprint_rejected():
    with pytest.raises(ValueError,match='Nonconvex'):
        m.inside('POLYGON ICRS 0 0 2 0 1 0.5 2 2 0 2',[.5,.5])

def test_dedup_preserves_detectors_and_excludes_all_detector_versions():
    rows=[dict(obs_id='a',energy_bandpassname='SPHEREx-D2',access_url='/qr3/2/a.fits'),dict(obs_id='a',energy_bandpassname='SPHEREx-D2',access_url='/dr1/2/a.fits'),dict(obs_id='a',energy_bandpassname='SPHEREx-D1',access_url='/dr1/1/a.fits')]
    kept=m.deduplicate(rows,set());assert len(kept)==2
    assert all('/dr1/'in r['access_url']for r in kept)
    assert m.deduplicate(rows,{'a'})==[]

def test_retry_priority_uses_latest_explicit_resolution():
    old=dict(target='Ceres',anchor='2025-05-01',status='incomplete',failures=['timeout'])
    new=dict(target='Ceres',anchor='2025-05-01',status='complete',failures=[])
    assert m.latest_attempts([old])[('Ceres','2025-05-01')]['status']=='incomplete'
    assert m.latest_attempts([old,new])[('Ceres','2025-05-01')]['status']=='complete'
    assert old['failures']==['timeout']
