import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('v4_freeze', Path(__file__).with_name('freeze.py'))
freeze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze)


def plan():
    return dict(schema_version=4, status='frozen', scope='final', authorized_final=True,
                protocol_revision='v4-blinded-coverage-repair-1',
                runtime=dict(workers=6, math_threads=1, max_frames=32, max_grid=512),
                proposal_policy='c13-sigma08-v1', detector_settings=freeze.PROFILE,
                models={'baseline': {'artifact': {'sha256': freeze.C13}}, 'candidate': {}},
                native={'parents': [dict(parent_id='v4-final%02d' % i, seed=3950000+i, center_deg=[float(i), 0.]) for i in range(1, 13)],
                        'region': dict(width_arcmin=6., height_arcmin=6., pixel_scale_arcsec=6.15, mask_policy='motion')},
                synthetic={'seeds': list(range(3900000, 3903000))})


def test_exact_final_identities_and_strong_baseline_are_required():
    value = plan()
    freeze.validate_plan(value)
    value['models']['baseline']['artifact']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='C13'):
        freeze.validate_plan(value)


def test_draft_and_unauthorized_final_reject_before_any_science_or_file_reference(tmp_path):
    path = tmp_path / 'freeze.json'
    value = plan(); value.update(status='draft', authorized_final=False)
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='frozen'):
        freeze.validate_freeze(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_final_seeds_and_parent_map_cannot_be_changed():
    for column in ('synthetic', 'native'):
        value = plan()
        if column == 'synthetic': value[column]['seeds'][0] += 1
        else: value[column]['parents'][0]['seed'] += 1
        with pytest.raises(ValueError, match='reservation'):
            freeze.validate_plan(value)


def test_changed_bytes_reject_without_interpreting_untrusted_json(tmp_path):
    path = tmp_path / 'freeze.json'; path.write_text('not even JSON')
    with pytest.raises(ValueError, match='SHA'):
        freeze.validate_freeze(path, '0' * 64)


def test_metadata_file_hash_and_duplicate_json_keys_reject(tmp_path):
    path = tmp_path / 'meta.json'; path.write_text('{"a":1,"a":2}')
    with pytest.raises(ValueError, match='duplicate'):
        freeze.read_json(path)
    with pytest.raises(ValueError, match='hash'):
        freeze.checked_ref(dict(path=str(path), sha256='0' * 64), tmp_path)


def test_checked_relative_reference_is_the_absolute_file_later_executed(tmp_path):
    path = tmp_path / 'source.py'; path.write_text('VALUE=3\n')
    ref = dict(path='source.py', sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    freeze.checked_ref(ref, tmp_path)
    assert ref['path'] == str(path.resolve())


def test_selected_model_record_must_bind_the_actual_frozen_graph():
    selected = dict(baseline_sha256=freeze.C13, selected_candidate=dict(artifact_sha256='a' * 64, metadata_sha256='b' * 64),
                    all_required_development_fields_complete=True, selection_uses_final=False)
    models = dict(candidate=dict(artifact={'sha256': 'c' * 64}, metadata={'sha256': 'b' * 64}))
    with pytest.raises(ValueError, match='selection'):
        freeze.check_selection(selected, models)


def test_physical_observation_cannot_be_shared_across_parents_or_old_fields():
    freeze.check_physical_ids([dict(parent_id='a', observations=[{'obs_id':'one'}]), dict(parent_id='b', observations=[{'obs_id':'two'}])], {'old'})
    with pytest.raises(ValueError, match='physical'):
        freeze.check_physical_ids([dict(parent_id='a', observations=[{'obs_id':'one'}]), dict(parent_id='b', observations=[{'obs_id':'one'}])], set())
    with pytest.raises(ValueError, match='physical'):
        freeze.check_physical_ids([dict(parent_id='a', observations=[{'obs_id':'old'}])], {'old'})


def test_same_bytes_compile_exactly_despite_an_existing_timestamp_cache(tmp_path):
    import os, py_compile
    path=tmp_path/'source.py';path.write_text('VALUE=1\n');os.utime(path,(1700000000,1700000000));py_compile.compile(str(path),doraise=True)
    path.write_text('VALUE=2\n');os.utime(path,(1700000000,1700000000))
    ref=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert freeze.exact_module('v4_exact_test',ref,tmp_path).VALUE==2
