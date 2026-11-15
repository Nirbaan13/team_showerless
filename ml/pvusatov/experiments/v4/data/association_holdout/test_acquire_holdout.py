import importlib.util
from pathlib import Path


def module():
    p = Path(__file__).with_name('acquire_holdout.py')
    assert p.exists(), 'Holdout acquisition not implemented'
    spec = importlib.util.spec_from_file_location('association_acquisition', p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_spherical_separation_handles_ra_wrap():
    m = module()
    assert abs(m.separation([359., 0.], [1., 0.]) - 2.) < 1e-10


def test_physical_parent_detector_alias_is_excluded():
    m = module()
    assert m.physical_id('2025W27_1A_0591_1D2') == '2025W27_1A_0591_1'
    assert m.physical_id('2025W27_1A_0591_1') == '2025W27_1A_0591_1'


def test_full_parent_caps_are_conservative():
    m = module()
    assert m.footprint_radius('POLYGON ICRS 359 -1 1 -1 1 1 359 1', [0., 0.]) > 1.4


def test_portable_audit_rejects_changed_acquisition_source_first(tmp_path):
    import json, pytest
    source = Path(__file__).with_name('audit_holdout.py')
    spec = importlib.util.spec_from_file_location('association_audit', source)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    (tmp_path/'plan.json').write_text(json.dumps({'code_sha256':'0'*64,'groups':[]}))
    (tmp_path/'acquire_holdout.py').write_text('changed')
    with pytest.raises(ValueError, match='Acquisition source'):
        m.audit(tmp_path)
