"""Toy-only blinded equality tests; real attempt outputs are never opened."""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def consumer():
    path = Path(__file__).with_name('compare_attempts.py')
    assert path.is_file(), 'blinded attempt comparison has not been implemented'
    spec = importlib.util.spec_from_file_location('v4_test_attempt_comparison', path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def fields():
    return [dict(seed=3800802, candidate_ids=['a', 'b'], matches=[0, -1],
                 scores_v4=[.987654321, .123456789],
                 center_usable_flags=[True, False, True],
                 features_v4=[[1., 2.], [3., 4.]]),
            dict(seed=3800803, candidate_ids=[], matches=[], scores_v4=[],
                 center_usable_flags=[True, True, True], features_v4=[])]


KEYS = ['candidate_ids', 'matches', 'scores_v4', 'center_usable_flags', 'features_v4']


def test_exact_projection_reports_counts_and_hashes_without_field_values():
    module = consumer(); old = fields(); new = copy.deepcopy(old)
    proof = module.compare_projection(old, new, KEYS)
    assert proof['passes'] is True and proof['rows_compared'] == 2
    assert proof['old_sha256'] == proof['new_sha256']
    assert len(proof['old_sha256']) == 64
    text = json.dumps(proof)
    assert '0.987654321' not in text and '0.123456789' not in text
    assert old == new


@pytest.mark.parametrize('field,value', [('scores_v4', [.987654322, .123456789]),
    ('matches', [-1, -1]), ('center_usable_flags', [True, True, True]),
    ('candidate_ids', ['b', 'a']), ('features_v4', [[1., 2.], [3., 4.00000000001]])])
def test_mismatches_expose_only_identity_field_name_and_digests(field, value):
    module = consumer(); old = fields(); new = copy.deepcopy(old); new[0][field] = value
    proof = module.compare_projection(old, new, KEYS)
    assert proof['passes'] is False
    assert proof['mismatch']['seed'] == 3800802 and proof['mismatch']['field'] == field
    assert set(proof['mismatch']) == {'seed', 'field', 'old_sha256', 'new_sha256'}
    assert proof['mismatch']['old_sha256'] != proof['mismatch']['new_sha256']
    text = json.dumps(proof)
    assert '.9876543' not in text and '.1234567' not in text and '4.000000' not in text


@pytest.mark.parametrize('change', ['missing_seed', 'missing_row', 'reordered_seed', 'missing_field'])
def test_missing_or_reordered_identity_and_projection_fields_fail_closed(change):
    module = consumer(); old = fields(); new = copy.deepcopy(old)
    if change == 'missing_seed': del new[0]['seed']
    elif change == 'missing_row': new.pop()
    elif change == 'reordered_seed': new.reverse()
    else: del new[0]['scores_v4']
    proof = module.compare_projection(old, new, KEYS)
    assert proof['passes'] is False and 'mismatch' in proof


def test_decoded_boolean_is_not_accepted_as_integer_mask():
    module = consumer(); old = fields(); new = copy.deepcopy(old)
    new[0]['center_usable_flags'][0] = 1
    assert module.compare_projection(old, new, KEYS)['passes'] is False


def test_completion_gate_precedes_any_freeze_or_output_read():
    module = consumer()
    with pytest.raises(ValueError, match='both'):
        module.verify_attempts('missing-freeze', 'bad-anchor', 'missing-native', 'missing-synthetic')


@pytest.fixture
def toy_attempts(tmp_path, request):
    """Complete toy manifests exercise checked dispatch without real inputs."""
    module = consumer()
    def ref(path):
        return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == '.gz':
            with gzip.open(path, 'wt') as handle: json.dump(value, handle)
        else: path.write_text(json.dumps(value))
        return ref(path)
    validator = tmp_path / 'validator.py'
    validator.write_text('''import hashlib,json,sys
def validate_freeze(path,anchor):
    raw=open(path,'rb').read()
    if hashlib.sha256(raw).hexdigest()!=anchor: raise ValueError('toy freeze anchor differs')
    value=json.loads(raw)
    for ref in value['sources'].values():
        if hashlib.sha256(open(ref['path'],'rb').read()).hexdigest()!=ref['sha256']:
            raise ValueError('toy checked source differs')
    return value
def require_checked_execution(frozen,namespace,name):
    if namespace.get('__source_sha256__')!=frozen['sources'][name]['sha256']:
        raise ValueError('use checked equality source')
    if getattr(sys.modules.get('freeze'),'__source_sha256__',None)!=frozen['sources']['freeze']['sha256']:
        raise ValueError('use checked validator source')
''')
    executor = tmp_path / 'execute.py'
    executor.write_bytes(Path(__file__).with_name('execute.py').read_bytes())
    versions = {'toy': '1'}; old_anchor = '1' * 64
    old_freeze = tmp_path / 'old-freeze.json'
    old_ref = write(old_freeze, dict(versions=versions)); old_anchor = old_ref['sha256']
    seeds = list(range(3900000, 3903000))
    rows = [{**copy.deepcopy(fields()[0]), 'seed': seed} for seed in seeds]
    summary = dict(evaluation_complete=True, error_trials=0, planned=3000)
    def cache(kind, anchor, values, parent=None):
        result = dict(schema_version=4, kind=kind, scope='final', freeze_sha256=anchor,
                      versions=versions, fields=values,
                      summary=dict(evaluation_complete=True, error_trials=0, planned=len(values)))
        if parent: result['parent_id'] = parent
        return result
    def manifest(kind, anchor, outputs):
        return dict(schema_version=4, kind=kind, scope='final', freeze_sha256=anchor,
                    versions=versions, evaluation_complete=True, outputs=outputs)
    old_cache = tmp_path / 'old/synthetic.json.gz'
    old_cache_value = cache('synthetic', old_anchor, rows)
    old_cache_ref = {**write(old_cache, old_cache_value), 'summary': summary}
    old_manifest = tmp_path / 'old/run-synthetic-manifest.json'
    old_manifest_ref = write(old_manifest, manifest('synthetic', old_anchor, [old_cache_ref]))
    inventory = [ref(old_cache), old_manifest_ref]
    native_mode = getattr(request, 'param', 'none')
    if native_mode != 'none':
        old_native_rows = [dict(seed=3950001, trajectory_id=str(i), candidate_ids=[], scores_v4=[],
            matches=[], features_v4=[], center_usable_flags=[True]*8) for i in range(270)]
        old_native_cache = tmp_path / 'old/v4-final01.json.gz'
        old_native_value = cache('native', old_anchor, old_native_rows, 'v4-final01')
        old_native_summary = old_native_value['summary']
        if native_mode == 'partial_native':
            old_native_summary.update(evaluation_complete=False, error_trials=1)
            old_native_cache.write_bytes(b'partial cache is not decodable JSON')
            old_native_ref = ref(old_native_cache)
        else:
            old_native_ref = write(old_native_cache, old_native_value)
        output_ref = {**old_native_ref, 'parent_id':'v4-final01', 'summary':old_native_summary}
        old_native_manifest = tmp_path / 'old/run-native-manifest.json'
        native_manifest_ref = write(old_native_manifest, manifest('native', old_anchor, [output_ref]))
        inventory.extend([old_native_ref, native_manifest_ref])
    opaque = tmp_path / 'opaque.json'
    opaque_ref = write(opaque, dict(scope='toy opaque inventory', files=inventory))
    amendment = tmp_path / 'amendment.json'
    amendment_ref = write(amendment, dict(original_freeze=old_ref, opaque_first_attempt=opaque_ref,
        scientific_equality_projection=dict(field_keys=KEYS, required_synthetic_fields=3000)))
    parents = [dict(parent_id=f'v4-final{i:02}', seed=3950000+i) for i in range(1, 13)]
    frozen = dict(scope='final', versions=versions, native={'parents':parents}, synthetic={'seeds':seeds},
        provenance={'amendment':amendment_ref},
        _coverage_audit={p['parent_id']:{'finite_pixel_counts':[100]*8} for p in parents},
        sources=dict(freeze=ref(validator), execute=ref(executor),
                     attempt_equality=ref(Path(__file__).with_name('compare_attempts.py'))))
    freeze = tmp_path / 'new-freeze.json'; anchor = write(freeze, frozen)['sha256']
    module.__source_sha256__ = frozen['sources']['attempt_equality']['sha256']
    syn_cache = tmp_path / 'new/synthetic.json.gz'
    syn_cache_value = cache('synthetic', anchor, rows)
    syn_ref = {**write(syn_cache, syn_cache_value), 'summary': summary}
    syn_manifest = tmp_path / 'new/run-synthetic-manifest.json'
    syn_manifest_value = manifest('synthetic', anchor, [syn_ref]); write(syn_manifest, syn_manifest_value)
    native_outputs = []
    for parent in parents:
        native_rows = [dict(seed=parent['seed'], trajectory_id=str(i), candidate_ids=[], scores_v4=[],
                            matches=[], features_v4=[], center_usable_flags=[True]*8) for i in range(270)]
        value = cache('native', anchor, native_rows, parent['parent_id'])
        path = tmp_path / 'new' / (parent['parent_id'] + '.json.gz')
        native_outputs.append({**write(path, value), 'parent_id':parent['parent_id'], 'summary':value['summary']})
    native_manifest = tmp_path / 'new/run-native-manifest.json'
    native_manifest_value = manifest('native', anchor, native_outputs); write(native_manifest, native_manifest_value)
    return locals()


def test_checked_verifier_compares_all_toy_rows_and_complete_parent_manifests(toy_attempts):
    t = toy_attempts
    proof = t['module'].verify_attempts(t['freeze'], t['anchor'], t['native_manifest'], t['syn_manifest'],
                                       both_runs_finished=True)
    assert proof['passes'] is True and proof['synthetic']['rows_compared'] == 3000
    assert proof['native_parents_complete'] == 12 and proof['first_artifacts_checked'] == 2
    assert proof['unaffected_native_parents_compared'] == 0
    assert '.9876543' not in json.dumps(proof)


@pytest.mark.parametrize('domain', ['native', 'synthetic'])
def test_incomplete_new_manifest_rejects_before_any_cache_decode(toy_attempts, monkeypatch, domain):
    t = toy_attempts; module = t['module']
    path = t['native_manifest'] if domain == 'native' else t['syn_manifest']
    value = json.loads(path.read_text()); value['evaluation_complete'] = False
    t['write'](path, value)
    read = module._read_json
    def no_cache_reads(path):
        assert Path(path).suffix != '.gz', 'scientific cache decoded before both completion manifests'
        return read(path)
    monkeypatch.setattr(module, '_read_json', no_cache_reads)
    with pytest.raises(ValueError, match='incomplete'):
        module.verify_attempts(t['freeze'], t['anchor'], t['native_manifest'], t['syn_manifest'], both_runs_finished=True)


def test_verifier_rejects_altered_sealed_old_bytes_without_decoding(toy_attempts):
    t = toy_attempts; t['old_cache'].write_bytes(b'changed opaque cache bytes')
    with pytest.raises(ValueError, match='byte binding'):
        t['module'].verify_attempts(t['freeze'], t['anchor'], t['native_manifest'], t['syn_manifest'], both_runs_finished=True)


def test_unchecked_consumer_cannot_read_scientific_caches(toy_attempts):
    t = toy_attempts; del t['module'].__source_sha256__
    with pytest.raises(ValueError, match='checked equality source'):
        t['module'].verify_attempts(t['freeze'], t['anchor'], t['native_manifest'], t['syn_manifest'], both_runs_finished=True)


@pytest.mark.parametrize('toy_attempts', ['complete_native', 'partial_native'], indirect=True)
def test_only_complete_unaffected_native_parent_rows_are_decoded_and_compared(toy_attempts):
    t = toy_attempts
    proof = t['module'].verify_attempts(t['freeze'], t['anchor'], t['native_manifest'], t['syn_manifest'],
                                       both_runs_finished=True)
    assert proof['passes'] is True
    assert proof['unaffected_native_parents_compared'] == (1 if t['native_mode'] == 'complete_native' else 0)


def test_full_verifier_mismatch_proof_does_not_expose_scores(toy_attempts):
    t = toy_attempts; value = t['syn_cache_value']
    value['fields'][7]['scores_v4'][0] = .1111222233334444
    changed = t['write'](t['syn_cache'], value)
    manifest = t['syn_manifest_value']; manifest['outputs'][0].update(changed)
    t['write'](t['syn_manifest'], manifest)
    proof = t['module'].verify_attempts(t['freeze'], t['anchor'], t['native_manifest'], t['syn_manifest'],
                                       both_runs_finished=True)
    assert proof['passes'] is False and proof['synthetic']['mismatch']['seed'] == 3900007
    assert proof['synthetic']['mismatch']['field'] == 'scores_v4'
    assert '.11112222' not in json.dumps(proof) and '.9876543' not in json.dumps(proof)


def test_bootstrap_executes_only_the_source_bytes_whose_hash_was_checked(toy_attempts, monkeypatch):
    t = toy_attempts; module = t['module']; checked_ref = module._ref
    def replace_after_check(ref, base):
        path = checked_ref(ref, base)
        if path == t['executor']:
            path.write_text(path.read_text() + "\nraise AssertionError('unchecked bootstrap executed')\n")
        return path
    monkeypatch.setattr(module, '_ref', replace_after_check)
    with pytest.raises(ValueError, match='bootstrap source'):
        module.verify_attempts(t['freeze'], t['anchor'], t['native_manifest'], t['syn_manifest'], both_runs_finished=True)
