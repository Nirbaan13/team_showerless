"""Blinded decoded-value equality; never expose scores, labels or rankings.

Real outputs may be opened only by root after both amended runs finish. This
module uses the standard library and never loads pixels, models or metrics.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _hash(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _mismatch(seed, field, old, new, count):
    return dict(passes=False, rows_compared=count, mismatch=dict(
        seed=seed if type(seed) is int else None, field=field,
        old_sha256=_hash(old), new_sha256=_hash(new)))


def compare_projection(old_fields, new_fields, field_keys):
    """Compare exact ordered JSON projections, returning only blinded proof."""
    if (not isinstance(field_keys, list) or not field_keys
            or any(not isinstance(key, str) or not key for key in field_keys)
            or len(set(field_keys)) != len(field_keys)):
        raise ValueError('invalid declared equality field names')
    old_hash = hashlib.sha256(); new_hash = hashlib.sha256()
    if len(old_fields) != len(new_fields):
        return _mismatch(None, 'row_count', len(old_fields), len(new_fields), 0)
    keys = ['seed'] + [key for key in field_keys if key != 'seed']
    for index, (old, new) in enumerate(zip(old_fields, new_fields)):
        if not isinstance(old, dict) or not isinstance(new, dict):
            raise ValueError('equality rows must be JSON objects')
        for key in keys:
            left = [key in old, old.get(key)]; right = [key in new, new.get(key)]
            if ((key == 'seed' and (type(old.get(key)) is not int or type(new.get(key)) is not int))
                    or _encoded(left) != _encoded(right)):
                return _mismatch(old.get('seed'), key, left, right, index)
        for row, digest in ((old, old_hash), (new, new_hash)):
            payload = _encoded({key: row[key] for key in keys if key in row})
            digest.update(str(len(payload)).encode() + b':' + payload)
    return dict(passes=True, rows_compared=len(old_fields),
                old_sha256=old_hash.hexdigest(), new_sha256=new_hash.hexdigest())


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate equality JSON key')
            result[key] = value
        return result
    def invalid(value): raise ValueError('nonfinite equality JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _read_json(path):
    path = Path(path)
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt') as handle:
        return _decode(handle.read())


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1048576), b''): result.update(chunk)
    return result.hexdigest()


def _ref(ref, base):
    if (not isinstance(ref, dict) or not isinstance(ref.get('path'), str)
            or not re.fullmatch('[0-9a-f]{64}', str(ref.get('sha256')))):
        raise ValueError('invalid equality artifact reference')
    path = Path(ref['path']); path = path.resolve() if path.is_absolute() else (base / path).resolve()
    if _digest(path) != ref['sha256'] or ('bytes' in ref and path.stat().st_size != ref['bytes']):
        raise ValueError('equality artifact byte binding differs')
    return path


def _bootstrap(path, anchor):
    path = Path(path).resolve(); raw = path.read_bytes()
    if not re.fullmatch('[0-9a-f]{64}', str(anchor)) or hashlib.sha256(raw).hexdigest() != anchor:
        raise ValueError('external equality freeze anchor differs')
    frozen = _decode(raw)
    source_path = _ref(frozen['sources']['execute'], path.parent)
    source = source_path.read_bytes()
    if (len(source) > 2 * 1024**2
            or hashlib.sha256(source).hexdigest() != frozen['sources']['execute']['sha256']):
        raise ValueError('checked bootstrap source differs')
    spec = importlib.util.spec_from_file_location('v4_equality_checked_bootstrap', source_path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, str(source_path), 'exec'), module.__dict__)
    return module.bootstrap(path, anchor)


def _manifest(path, domain, anchor, versions, count):
    path = Path(path).resolve(); value = _read_json(path)
    if (value.get('schema_version') != 4 or value.get('kind') != domain or value.get('scope') != 'final'
            or value.get('freeze_sha256') != anchor or value.get('versions') != versions
            or value.get('evaluation_complete') is not True
            or not isinstance(value.get('outputs'), list) or len(value['outputs']) != count):
        raise ValueError('equality run manifest is incomplete or differs from freeze')
    expected = 3000 if domain == 'synthetic' else 270
    for ref in value['outputs']:
        summary = ref.get('summary', {})
        if (summary.get('evaluation_complete') is not True or summary.get('error_trials') != 0
                or summary.get('planned') != expected):
            raise ValueError('equality cache completion declaration differs')
    return path, value


def _cache(ref, manifest_path, domain, anchor, versions, planned):
    path = _ref(ref, manifest_path.parent); cache = _read_json(path)
    if (cache.get('schema_version') != 4 or cache.get('kind') != domain or cache.get('scope') != 'final'
            or cache.get('freeze_sha256') != anchor or cache.get('versions') != versions
            or cache.get('summary') != ref['summary'] or not isinstance(cache.get('fields'), list)
            or len(cache['fields']) != planned):
        raise ValueError('equality cache provenance or row count differs')
    return cache


def verify_attempts(new_freeze_path, anchor, new_native_manifest, new_syn_manifest, *, both_runs_finished=False):
    """Read-only, checked comparison; caller owns writing the returned proof."""
    if both_runs_finished is not True:
        raise ValueError('both amended runs must finish before any output is read')
    frozen, validator = _bootstrap(new_freeze_path, anchor)
    sys.modules['freeze'] = validator
    validator.require_checked_execution(frozen, globals(), 'attempt_equality')
    base = Path(new_freeze_path).resolve().parent
    if frozen.get('scope') != 'final' or len(frozen['native']['parents']) != 12 or len(frozen['synthetic']['seeds']) != 3000:
        raise ValueError('equality requires the complete frozen FINAL cohort')
    # Check BOTH completion manifests before decoding any scientific field.
    native_path, native = _manifest(new_native_manifest, 'native', anchor, frozen['versions'], 12)
    syn_path, syn = _manifest(new_syn_manifest, 'synthetic', anchor, frozen['versions'], 1)
    parent_ids = [parent['parent_id'] for parent in frozen['native']['parents']]
    if sorted(ref.get('parent_id') for ref in native['outputs']) != sorted(parent_ids):
        raise ValueError('equality native manifest parent coverage differs')
    amendment_path = _ref(frozen['provenance']['amendment'], base)
    amendment = _read_json(amendment_path); projection = amendment['scientific_equality_projection']
    if projection.get('required_synthetic_fields') != 3000:
        raise ValueError('declared equality synthetic denominator differs')
    keys = projection['field_keys']
    opaque_path = _ref(amendment['opaque_first_attempt'], amendment_path.parent)
    opaque = _read_json(opaque_path)
    artifacts = {str(_ref(ref, opaque_path.parent)): ref for ref in opaque['files']}
    if len(artifacts) != len(opaque['files']): raise ValueError('duplicate first-attempt artifact')
    old_freeze_path = _ref(amendment['original_freeze'], amendment_path.parent)
    original = _read_json(old_freeze_path); old_anchor = amendment['original_freeze']['sha256']
    def old_manifest(name):
        candidates = [Path(path) for path in artifacts if Path(path).name == name]
        if len(candidates) > 1: raise ValueError('ambiguous first-attempt manifest')
        return candidates[0] if candidates else None
    old_syn_path = old_manifest('run-synthetic-manifest.json')
    if old_syn_path is None: raise ValueError('missing complete first synthetic manifest')
    old_syn_path, old_syn = _manifest(old_syn_path, 'synthetic', old_anchor, original['versions'], 1)
    for ref in old_syn['outputs']:
        path = _ref(ref, old_syn_path.parent)
        if str(path) not in artifacts or ref['sha256'] != artifacts[str(path)]['sha256']:
            raise ValueError('first synthetic cache is not in the sealed opaque inventory')
    old_cache = _cache(old_syn['outputs'][0], old_syn_path, 'synthetic', old_anchor, original['versions'], 3000)
    new_cache = _cache(syn['outputs'][0], syn_path, 'synthetic', anchor, frozen['versions'], 3000)
    if ([row.get('seed') for row in old_cache['fields']] != frozen['synthetic']['seeds']
            or [row.get('seed') for row in new_cache['fields']] != frozen['synthetic']['seeds']):
        raise ValueError('equality synthetic ordered seed coverage differs')
    synthetic = compare_projection(old_cache['fields'], new_cache['fields'], keys)
    del old_cache, new_cache
    native_results = []; old_native_path = old_manifest('run-native-manifest.json')
    old_native = _read_json(old_native_path) if old_native_path else None
    old_outputs = {}
    if old_native is not None:
        if (old_native.get('schema_version') != 4 or old_native.get('kind') != 'native'
                or old_native.get('freeze_sha256') != old_anchor or old_native.get('versions') != original['versions']):
            raise ValueError('first native manifest provenance differs')
        for ref in old_native.get('outputs', []):
            summary = ref.get('summary', {})
            if summary.get('evaluation_complete') is True and summary.get('error_trials') == 0 and summary.get('planned') == 270:
                if ref.get('parent_id') in old_outputs: raise ValueError('duplicate first native parent')
                old_outputs[ref['parent_id']] = ref
    for ref in native['outputs']:
        cache = _cache(ref, native_path, 'native', anchor, frozen['versions'], 270)
        parent = ref['parent_id']
        if cache.get('parent_id') != parent: raise ValueError('equality native cache parent differs')
        if parent in old_outputs and all(count > 0 for count in frozen['_coverage_audit'][parent]['finite_pixel_counts']):
            old_ref = old_outputs[parent]; path = _ref(old_ref, old_native_path.parent)
            if str(path) not in artifacts or old_ref['sha256'] != artifacts[str(path)]['sha256']:
                raise ValueError('first native cache is not in the sealed opaque inventory')
            old_cache = _cache(old_ref, old_native_path, 'native', old_anchor, original['versions'], 270)
            native_results.append(compare_projection(old_cache['fields'], cache['fields'], keys))
    # Recheck the externally anchored source/data closure and first artifacts.
    validator.validate_freeze(new_freeze_path, anchor)
    for ref in opaque['files']: _ref(ref, opaque_path.parent)
    return dict(schema_version=4, passes=synthetic['passes'] and all(row['passes'] for row in native_results),
                freeze_sha256=anchor, amendment_sha256=_digest(amendment_path),
                opaque_inventory_sha256=_digest(opaque_path), first_artifacts_checked=len(artifacts),
                native_parents_complete=len(native['outputs']), unaffected_native_parents_compared=len(native_results),
                synthetic=synthetic, native=native_results,
                scientific_values_disclosed=False, metrics_aggregated=False)
