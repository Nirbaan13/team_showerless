"""Opaque-byte preflight for the prospective V4 paired evaluation.

No FITS, simulator, detector, learner or model session is opened by validation.
Every final entry point must finish this preflight and model-policy validation
before importing a pixel reader. Module execution compiles the checked bytes.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path
import platform
import re
import sys

C13 = 'c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204'
PROFILE = dict(min_snr=4., max_peaks=100, psf_sigma=.8, min_speed=.5, max_speed=60.,
               match_radius=1.4, min_epochs=3, min_support=.8, leave_one_out=True)
SOURCES = dict(
    freeze='experiments/v4/evaluation/freeze.py',
    run_native='experiments/v4/evaluation/run_native.py',
    run_synthetic='experiments/v4/evaluation/run_synthetic.py',
    report='experiments/v4/evaluation/summarize.py',
    metrics='experiments/v4/evaluation/metrics.py',
    geometry='experiments/v4/evaluation/geometry.py',
    scene='experiments/v4/evaluation/scene.py',
    native_cache='experiments/v4/evaluation/cache_native.py',
    features='experiments/v4/detection/features.py',
    runtime_model='experiments/v4/detection/runtime_model.py',
    paired='backend/inference/experiments/v3_evaluation/paired.py',
    native_latents='backend/inference/experiments/v3_evaluation/run_native.py',
    simulate='backend/inference/training/simulate_v2.py',
    native_psf='backend/inference/training/evaluate_background.py',
    training_init='backend/inference/training/__init__.py',
    **{'legacy_' + name.strip('_'): 'backend/inference/ml_inference/' + name + '.py'
       for name in ('__init__', '__main__', 'cli', 'contracts', 'detector', 'model', 'pipeline', 'prepare', 'render')})


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON: ' + value)
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def versions():
    return {'python': platform.python_version(), **{name: importlib.metadata.version(name)
            for name in ('numpy', 'scipy', 'astropy', 'onnxruntime', 'onnx', 'pillow')}}


def checked_ref(ref, base, *, maximum_bytes=160 * 1024 * 1024):
    if (not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}
            or not isinstance(ref['path'], str)
            or not re.fullmatch('[0-9a-f]{64}', str(ref['sha256']))):
        raise ValueError('invalid opaque file reference')
    path = Path(ref['path'])
    path = path.resolve() if path.is_absolute() else (Path(base) / path).resolve()
    if not path.is_file() or not 0 < path.stat().st_size <= maximum_bytes:
        raise ValueError('missing or excessive referenced file: ' + str(path))
    if digest(path) != ref['sha256']:
        raise ValueError('reference byte hash mismatch: ' + str(path))
    ref['path'] = str(path)
    return path


def exact_module(name, ref, base):
    """The source bytes checked here are exactly those executed, never a pyc."""
    path = checked_ref(ref, base, maximum_bytes=2 * 1024 * 1024)
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != ref['sha256']:
        raise ValueError('module changed after source preflight')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(source, str(path), 'exec'), module.__dict__)
    module.__source_sha256__ = ref['sha256']
    return module


def validate_plan(value):
    if value.get('schema_version') != 4 or value.get('status') != 'frozen':
        raise ValueError('V4 evaluation must be frozen')
    scope = value.get('scope')
    if scope not in ('development', 'final') or value.get('authorized_final') is not (scope == 'final'):
        raise ValueError('freeze scope or explicit final authorization differs')
    runtime = value.get('runtime', {})
    if (set(runtime) != {'workers', 'math_threads', 'max_frames', 'max_grid'}
            or type(runtime.get('workers')) is not int or not 1 <= runtime['workers'] <= 6
            or runtime.get('math_threads') != 1 or runtime.get('max_frames') != 32 or runtime.get('max_grid') != 512):
        raise ValueError('freeze runtime bounds differ')
    if value.get('proposal_policy') != 'c13-sigma08-v1' or value.get('detector_settings') != PROFILE:
        raise ValueError('freeze does not preserve the declared C13 proposal pool')
    if value.get('models', {}).get('baseline', {}).get('artifact', {}).get('sha256') != C13:
        raise ValueError('strong deployed C13 baseline is required')
    parents = value.get('native', {}).get('parents', [])
    seeds = value.get('synthetic', {}).get('seeds', [])
    if scope == 'final':
        if ([parent.get('parent_id') for parent in parents] != ['v4-final%02d' % i for i in range(1, 13)]
                or [parent.get('seed') for parent in parents] != list(range(3950001, 3950013))
                or seeds != list(range(3900000, 3903000))):
            raise ValueError('FINAL parent or seed reservation differs')
    elif (not parents or not seeds or len(parents) > 12
          or any(type(seed) is not int or not 3800000 <= seed < 3900000
                 for seed in seeds + [parent.get('seed') for parent in parents])):
        raise ValueError('DEVELOPMENT reservation differs')
    if (not all(type(seed) is int for seed in seeds) or seeds != sorted(set(seeds))
            or len({parent.get('parent_id') for parent in parents}) != len(parents)):
        raise ValueError('duplicate or malformed evaluation identities')
    region = value['native'].get('region')
    if region != dict(width_arcmin=6., height_arcmin=6., pixel_scale_arcsec=6.15, mask_policy='motion'):
        raise ValueError('native preparation region differs')
    for parent in parents:
        center = parent.get('center_deg')
        if (not isinstance(center, list) or len(center) != 2
                or any(type(item) not in (int, float) or not math.isfinite(item) for item in center)
                or not 0 <= center[0] < 360 or not -90 < center[1] < 90):
            raise ValueError('native parent center differs')


def check_physical_ids(parents, excluded):
    seen = set()
    for parent in parents:
        local = [row['obs_id'] for row in parent['observations']]
        if (len(local) != len(set(local)) or seen.intersection(local)
                or set(local).intersection(excluded)):
            raise ValueError('physical observation reuse across parents or excluded fields')
        seen.update(local)
    return sorted(seen)


def check_selection(record, models, *, final=True):
    selected = record.get('selected_candidate', {})
    if (record.get('baseline_sha256') != C13 or record.get('selection_uses_final') is not False
            or (final and record.get('all_required_development_fields_complete') is not True)
            or selected.get('artifact_sha256') != models['candidate']['artifact']['sha256']
            or selected.get('metadata_sha256') != models['candidate']['metadata']['sha256']):
        raise ValueError('selection record does not bind the actual frozen candidate or completed development')


def validate_freeze(path, expected_sha256):
    path = Path(path).resolve()
    if not re.fullmatch('[0-9a-f]{64}', str(expected_sha256)) or digest(path) != expected_sha256:
        raise ValueError('external freeze SHA-256 differs')
    value = read_json(path)
    validate_plan(value)
    base = path.parent
    root = Path(value['source_root'])
    root = root.resolve() if root.is_absolute() else (base / root).resolve()
    if '/ml/pvusatov/' not in root.as_posix() + '/':
        raise ValueError('source root must be the namespaced study')
    if set(value.get('sources', {})) != set(SOURCES):
        raise ValueError('incomplete scientific source closure')
    for name, relative in SOURCES.items():
        source = checked_ref(value['sources'][name], base, maximum_bytes=2 * 1024 * 1024)
        if source != (root / relative).resolve():
            raise ValueError('scientific source path differs: ' + name)
    if value.get('versions') != versions():
        raise ValueError('scientific environment differs from freeze')
    for key in ('protocol', 'acquisition_plan', 'selection_record', 'data_audit'):
        checked_ref(value['provenance'][key], base)
    check_selection(read_json(value['provenance']['selection_record']['path']), value['models'], final=value['scope'] == 'final')
    for ref in value['provenance'].get('additional', []):
        checked_ref(ref, base)
    if set(value['models']) != {'baseline', 'candidate'}:
        raise ValueError('freeze requires baseline and one selected candidate')
    for role, model in value['models'].items():
        artifact_path = checked_ref(model['artifact'], base, maximum_bytes=64 * 1024 * 1024)
        metadata_path = checked_ref(model['metadata'], base, maximum_bytes=256 * 1024)
        if artifact_path.name != 'ranker.onnx' or metadata_path.name != 'metadata.json' or artifact_path.parent != metadata_path.parent:
            raise ValueError('hashed model files must match the directory actually loaded')
        metadata = read_json(metadata_path)
        if metadata.get('sha256') != model['artifact']['sha256']:
            raise ValueError('model metadata/artifact binding differs: ' + role)
        if role == 'candidate':
            if (metadata.get('schema_version') != 4 or metadata.get('full_feature_count') != 30
                    or metadata.get('feature_source_sha256') != value['sources']['features']['sha256']
                    or metadata.get('detector_profile') != PROFILE):
                raise ValueError('candidate feature/profile contract differs')
        model['_metadata'] = metadata
        model['_directory'] = str(artifact_path.parent)
    checked_ref(value['synthetic']['calibration_bank'], base)
    parents = []
    for parent in value['native']['parents']:
        manifest = checked_ref(parent['downloads_manifest'], base)
        rows = read_json(manifest)
        if not isinstance(rows, list) or len(rows) != (8 if value['scope'] == 'final' else len(rows)) or not 3 <= len(rows) <= 32:
            raise ValueError('frozen native exposure count differs')
        observations = []
        for row in rows:
            raw_path = Path(row['path'])
            raw_path = raw_path.resolve() if raw_path.is_absolute() else (manifest.parent / raw_path).resolve()
            if value['scope'] == 'development' and any(part.lower().startswith(('final', 'quarant')) for part in raw_path.parts):
                raise ValueError('development entry point cannot open quarantined pixels')
            native = checked_ref({key: row[key] for key in ('path', 'sha256')}, manifest.parent)
            if native.suffix.lower() not in ('.fits', '.fit', '.fts'):
                raise ValueError('frozen native reference is not FITS')
            observations.append({**row, 'path': str(native), 'frame_id': native.stem,
                                 'observation_id': row['obs_id'], 'access_url': row.get('url')})
        parent['_observations'] = observations
        parents.append(dict(parent_id=parent['parent_id'], observations=observations))
    excluded = value['native'].get('excluded_physical_obsids')
    if not isinstance(excluded, list) or len(excluded) != len(set(excluded)) or (value['scope'] == 'final' and len(excluded) < 338):
        raise ValueError('prior and development physical observation exclusions missing')
    value['_physical_ids'] = check_physical_ids(parents, set(excluded))
    value['_freeze_path'] = str(path)
    value['_sha256'] = expected_sha256
    return value
