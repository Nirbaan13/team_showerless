"""The blinded repair cannot change a holdout, graph, simulator or gate."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('v4_amendment_validator', HERE/'freeze.py')
freeze = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(freeze)


def fixture(tmp_path):
    namespace = HERE.parents[2]
    source = namespace/'verification/v4-final/freeze.json'
    original_path = tmp_path/'original.json'; original_path.write_bytes(source.read_bytes())
    original = json.loads(original_path.read_text())
    value = copy.deepcopy(original); value['protocol_revision'] = 'v4-blinded-coverage-repair-1'
    value['sources'].update({name:dict(path='not-executed-in-metadata-test', sha256='f'*64)
                             for name in ('prepare', 'native_injections', 'worker_transport', 'attempt_equality')})
    audit_path = tmp_path/'coverage.json'
    audit_path.write_text(json.dumps(dict(prepare_source_sha256='f'*64, results=[])))
    ref = lambda path:dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    amendment = dict(amendment_id=value['protocol_revision'], scientific_outcomes_inspected=False,
                     candidate_reselection=False, refit=False, parents_replaced=False, observations_dropped=False,
                     cohort_and_seeds_unchanged=True, promotion_gates_unchanged=True,
                     original_freeze=ref(original_path), coverage_audit=ref(audit_path))
    path = tmp_path/'amendment.json'; path.write_text(json.dumps(amendment))
    value['provenance']['amendment'] = ref(path)
    return value


def test_same_physics_metadata_pass_without_native_pixels(tmp_path, monkeypatch):
    value = fixture(tmp_path); opened = Path.open
    def guard(path, *args, **kwargs):
        if path.suffix.lower() in ('.fits', '.fit', '.fts'): raise AssertionError('native pixels opened')
        return opened(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guard)
    freeze.check_amendment(value, tmp_path)


@pytest.mark.parametrize('change', ['gate', 'simulator', 'model', 'seed', 'center', 'exclusions', 'prepare'])
def test_amendment_rejects_scientific_changes_before_execution(tmp_path, change):
    value = fixture(tmp_path)
    if change in ('gate', 'simulator'):
        value['sources']['metrics' if change == 'gate' else 'simulate']['sha256'] = '0'*64
    elif change == 'model': value['models']['candidate']['artifact']['sha256'] = '0'*64
    elif change == 'seed': value['synthetic']['seeds'][0] += 1
    elif change == 'center': value['native']['parents'][0]['center_deg'][0] += .01
    elif change == 'exclusions': value['native']['excluded_physical_obsids'][0] = 'different'
    else: value['sources']['prepare']['sha256'] = '0'*64
    with pytest.raises(ValueError): freeze.check_amendment(value, tmp_path)
