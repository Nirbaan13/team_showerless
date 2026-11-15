"""Validate complete paired outputs before reporting a frozen V4 comparison.

This consumer never loads FITS pixels, a simulator or a scoring session. Native
derivatives stay clustered by parent; synthetic uncertainty uses whole fields.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
from types import ModuleType


def _compiled(path, name):
    module = ModuleType(name)
    exec(compile(Path(path).read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _spatial_labels(field, truth, *, native):
    import numpy as np
    truth = [np.asarray(points, dtype=float) for points in truth]
    result = []
    for epochs, xy in zip(field['candidate_epochs'], field['candidate_positions_xy']):
        distances = [np.linalg.norm(np.asarray(xy) - points[epochs], axis=1) for points in truth]
        matches = [i for i, distance in enumerate(distances) if np.all(distance <= 1.5)]
        result.append(min(matches, key=lambda i:float(distances[i].mean())) if matches else (-2 if native else -1))
    return result


def validate_control(control, times, geometry_validator):
    labels = control.get('matches'); ids = control.get('candidate_ids')
    if (control.get('error') is not None or not isinstance(labels, list)
            or any(type(label) is not int or label != -2 for label in labels)
            or not isinstance(ids, list) or len(ids) != len(labels) or len(set(ids)) != len(ids)
            or any(not isinstance(value, str) or not value for value in ids)):
        raise ValueError('UNKNOWN control identity, completion or label alignment differs')
    for key, width in (('features', 6), ('features_v4', 30)):
        values = control.get(key)
        if (not isinstance(values, list) or len(values) != len(labels)
                or any(not isinstance(row, list) or len(row) != width
                       or any(not _number(value) for value in row) for row in values)):
            raise ValueError('UNKNOWN control feature alignment differs')
    if any(a != b[:6] for a, b in zip(control['features'], control['features_v4'])):
        raise ValueError('UNKNOWN control legacy features differ')
    for key in ('scores_c13', 'scores_v4'):
        values = control.get(key)
        if (not isinstance(values, list) or len(values) != len(labels)
                or any(not _number(value) or not 0 <= value <= 1 for value in values)):
            raise ValueError('UNKNOWN control score alignment differs')
    geometry_validator({**control, 'truth_count': 0, 'expected_xy': [], 'matched_geometry': []}, times, native=False)


def validate_latent(field, domain, times, shape, control=None):
    import numpy as np
    if field.get('truth_count_known', True) is not True:
        raise ValueError('unknown truth cannot enter a planned recovery denominator')
    eligible = field.get('attribution_eligible'); preexisting = field.get('preexisting_control_match')
    if type(eligible) is not bool or type(preexisting) is not bool or eligible is preexisting:
        raise ValueError('attribution flags must be explicit boolean complements')
    if domain == 'native':
        origin = np.asarray(field.get('origin_xy'), dtype=float)
        velocity = np.asarray(field.get('velocity_xy_hour'), dtype=float)
        positions = np.asarray(field['expected_xy'], dtype=float)
        speed = field.get('speed_px_hour'); flux = field.get('injected_flux')
        flags = field.get('center_usable_flags')
        if (origin.shape != (2,) or velocity.shape != (2,) or not np.isfinite(origin).all()
                or not np.isfinite(velocity).all() or not _number(speed) or speed <= 0
                or not _number(flux) or flux <= 0 or field.get('coverage_known') is not True
                or not isinstance(flags, list) or len(flags) != len(times) or any(type(v) is not bool for v in flags)
                or type(field.get('usable_center_epochs')) is not int or sum(flags) != field['usable_center_epochs']
                or not math.isclose(float(np.linalg.norm(velocity)), speed, rel_tol=1e-12, abs_tol=1e-12)
                or not np.allclose(positions, origin + np.asarray(times)[:, None] * velocity, rtol=1e-12, atol=1e-9)):
            raise ValueError('native origin, velocity, flux or coverage contradicts the recorded truth')
        if control is not None:
            actual = any(value >= 0 for value in _spatial_labels(control, [positions], native=True))
            if preexisting is not actual:
                raise ValueError('native attribution differs from spatial matches in the UNKNOWN control')
        return
    seed = field.get('seed'); metadata = field.get('metadata'); n = len(times)
    if type(seed) is not int: raise ValueError('synthetic seed must be an exact integer')
    mode = 'noise_only' if seed % 10 == 0 else 'artifacts_only' if seed % 10 == 1 else 'injected'
    if (type(seed) is not int or field.get('mode') != mode or eligible is not True or preexisting is not False
            or not isinstance(metadata, dict) or metadata.get('epoch_count') != n or not 3 <= n <= 8
            or shape != [n, 80, 80] or type(metadata.get('cadence_family')) is not int
            or metadata['cadence_family'] not in range(4)
            or metadata.get('label_nuisance_policy') != 'shared flux law, field PSF and overlapping variability for source/artifact identities'):
        raise ValueError('synthetic seed, mode or generator metadata differs')
    positives = metadata.get('positive_fluxes'); artifacts = metadata.get('artifact_fluxes')
    if (not isinstance(positives, list) or len(positives) != field['truth_count']
            or not isinstance(artifacts, list) or any(not _number(v) or not 6 <= v <= 600 for v in positives + artifacts)
            or (mode == 'injected' and not 1 <= len(positives) <= 4)
            or (mode != 'injected' and positives)
            or (mode == 'noise_only' and artifacts)
            or (mode != 'noise_only' and not 8 * n <= len(artifacts) <= 21 * n)):
        raise ValueError('synthetic flux or truth metadata differs')
    gaps = np.diff(times); family = metadata['cadence_family']
    bounds = [(0.3, 1.5)] * (n - 1) if family == 0 else [(0.015, 0.065)] * (n - 1)
    if family == 2: bounds = [(0.02, 0.07)] * (n - 2) + [(2., 7.)]
    if family == 3:
        bounds = [(0.02, 0.10)] * (n - 1); bounds[max(0, (n - 1) // 2)] = (1., 6.)
    if abs(times[0]) > 1e-12 or any(not lo - 1e-12 <= gap <= hi + 1e-12 for gap, (lo, hi) in zip(gaps, bounds)):
        raise ValueError('synthetic physical cadence differs from the declared family')
    if mode == 'noise_only': return
    jitter = np.asarray(metadata.get('registration_jitter_xy'), dtype=float)
    if (jitter.shape != (n, 2) or not np.isfinite(jitter).all()
            or type(metadata.get('detector')) is not int or metadata['detector'] not in range(1, 7)
            or metadata.get('psf_family') not in ('calibration', 'analytic_core_wing')
            or type(metadata.get('psf_bank_row')) is not int or metadata['psf_bank_row'] < 0
            or not isinstance(metadata.get('epoch_psf_rows'), list) or len(metadata['epoch_psf_rows']) != n
            or any(type(row) is not int or row < 0 for row in metadata['epoch_psf_rows'])
            or type(metadata.get('extended_stationary_sources')) is not int
            or (not 3 <= metadata['extended_stationary_sources'] <= 8 if seed % 3 == 0 else metadata['extended_stationary_sources'] != 0)):
        raise ValueError('synthetic PSF, registration or extended-source metadata differs')
    for path in field['expected_xy']:
        unjittered = np.asarray(path) - jitter
        velocity = (unjittered[1] - unjittered[0]) / (times[1] - times[0])
        if (not .5 - 1e-9 <= np.linalg.norm(velocity) <= 60. + 1e-9
                or not np.allclose(unjittered, unjittered[0] + np.asarray(times)[:, None] * velocity, rtol=1e-12, atol=1e-9)):
            raise ValueError('synthetic underlying linear trajectory contradicts registration metadata')


def validate_field(field, domain, *, times=None, shape=None, geometry_validator=None, control=None):
    """Fail closed on unaligned scores, missing truth rows or false geometry."""
    if domain not in ('native', 'synthetic') or not isinstance(field, dict) or field.get('error'):
        raise ValueError('invalid or failed scientific field')
    labels = field.get('matches'); count = field.get('truth_count')
    if (type(count) is not int or count < 0 or (domain == 'native' and count != 1)
            or not isinstance(labels, list)
            or any(type(item) is not int or item < (-2 if domain == 'native' else -1)
                   or item >= count or (domain == 'native' and item == -1) for item in labels)):
        raise ValueError('truth count or UNKNOWN/known-negative convention differs')
    n = len(labels)
    identifiers = field.get('candidate_ids')
    if (not isinstance(identifiers, list) or len(identifiers) != n
            or any(not isinstance(item, str) or not item for item in identifiers)
            or len(set(identifiers)) != n):
        raise ValueError('candidate identities are missing or duplicated')
    for name, width in (('features', 6), ('features_v4', 30)):
        rows = field.get(name)
        if (not isinstance(rows, list) or len(rows) != n
                or any(not isinstance(row, list) or len(row) != width
                       or any(not _number(value) for value in row) for row in rows)):
            raise ValueError('finite feature matrix differs: ' + name)
    if any(a != b[:6] for a, b in zip(field['features'], field['features_v4'])):
        raise ValueError('physical features changed the original six-feature prefix')
    for name in ('scores_c13', 'scores_v4'):
        scores = field.get(name)
        if (not isinstance(scores, list) or len(scores) != n
                or any(not _number(value) or not 0 <= value <= 1 for value in scores)):
            raise ValueError('finite aligned scores differ: ' + name)
    times = times if times is not None else field.get('times_hours')
    shape = shape if shape is not None else field.get('registered_shape')
    if (not isinstance(shape, list) or len(shape) != 3
            or any(type(value) is not int or value <= 0 for value in shape)
            or not isinstance(times, list) or len(times) != shape[0] or shape[0] < 3):
        raise ValueError('registered shape and time dimensions differ')
    if geometry_validator is None:
        path = Path(__file__).resolve().parents[3] / 'verification/final/summary_geometry.py'
        geometry_validator = _compiled(path, 'v4_geometry_test_helper').validate_matched_geometry
    geometry_validator(field, times, native=domain == 'native')
    if domain == 'native' and control is not None:
        validate_control(control, times, geometry_validator)
    # Independently recompute even missing/negative labels. Checking only stored
    # positive geometry would silently permit an erased recovery and denominator.
    truth = [field['expected_xy']] if domain == 'native' else field['expected_xy']
    if _spatial_labels(field, truth, native=domain == 'native') != labels:
        raise ValueError('recorded match labels differ from independently measured spatial geometry')
    validate_latent(field, domain, times, shape, control)


def diagnostics(fields, left, right, domain):
    """Descriptive strata retain all planned truths and fixed review budgets."""
    import numpy as np
    groups = {}
    geometry = dict(planned_truths=0, finite_centers_ge3=0, resolved_covered_truth_span_ge3px=0,
                    geometrically_testable=0)
    recovered_resolved = {role:dict(top1=0, top3=0, detected=0) for role in ('baseline', 'candidate')}
    for field, baseline, candidate in zip(fields, left, right):
        capabilities = [field['geometric_capability']] if domain == 'native' else field['geometric_capabilities']
        geometry['planned_truths'] += field['truth_count']
        for capability in capabilities:
            geometry['finite_centers_ge3'] += int(capability['finite_centers_ge_min_epochs'])
            geometry['resolved_covered_truth_span_ge3px'] += int(capability['resolved_truth_span_ge3px'])
            geometry['geometrically_testable'] += int(capability['geometrically_testable'])
        keys = [('parent', str(field['parent_id'])), ('speed_px_hour', str(field['speed_px_hour'])),
                ('brightness', str(field['brightness']))] if domain == 'native' else [('mode', str(field['mode']))]
        labels = np.asarray(field['matches'], dtype=int)
        resolved = {row['candidate_index'] for row in field['matched_geometry'] if row['true_displacement_px'] >= 3.}
        counts = {}
        for role, scores in (('baseline', baseline), ('candidate', candidate)):
            order = np.argsort(-np.asarray(scores), kind='stable')
            counts[role] = {name:len({int(labels[index]) for index in indices if labels[index] >= 0})
                            for name, indices in (('top1', order[:1]), ('top3', order[:3]), ('detected', order))}
            for name, indices in (('top1', order[:1]), ('top3', order[:3]), ('detected', order)):
                recovered_resolved[role][name] += len({int(labels[index]) for index in indices if index in resolved})
        for kind, value in keys:
            key = kind + ':' + value
            group = groups.setdefault(key, dict(kind=kind, value=value, planned_trials=0, truth_count=0,
                                               attributable_trials=0, baseline=dict(top1=0, top3=0, detected=0),
                                               candidate=dict(top1=0, top3=0, detected=0)))
            group['planned_trials'] += 1; group['truth_count'] += field['truth_count']
            group['attributable_trials'] += int(field.get('attribution_eligible', True))
            for role in ('baseline', 'candidate'):
                for name in ('top1', 'top3', 'detected'): group[role][name] += counts[role][name]
    return dict(geometry=geometry, strata=list(groups.values()),
                actual_matched_epoch_truth_span_ge3px_recoveries=recovered_resolved,
                interpretation='descriptive only; three-pixel spans do not confirm motion; no primary denominator filtering')


def _slim(field):
    names = ('parent_id', 'seed', 'trajectory_id', 'brightness', 'truth_count', 'matches',
             'attribution_eligible', 'usable_center_epochs', 'speed_px_hour', 'direction_id',
             'mode', 'geometric_capability', 'geometric_capabilities', 'matched_geometry')
    return {key: field[key] for key in names if key in field}


def summarize(path, anchor, native_manifest, synthetic_manifest, *, both_runs_finished=False):
    if both_runs_finished is not True:
        raise ValueError('both frozen runs must finish before any output is read')
    from freeze import validate_freeze, exact_module, digest, read_json, checked_ref, require_checked_execution
    frozen = validate_freeze(path, anchor)
    require_checked_execution(frozen, globals(), 'report')
    base = Path(path).resolve().parent
    paired = exact_module('v4_checked_report_pairing', frozen['sources']['paired'], base)
    metrics = exact_module('v4_checked_report_gate', frozen['sources']['metrics'], base)
    geometry = exact_module('v4_checked_report_geometry', frozen['sources']['geometry_validation'], base)
    expected_sources = {name: ref['sha256'] for name, ref in frozen['sources'].items()}
    expected_models = {role: model['_metadata'] for role, model in frozen['models'].items()}
    capability = exact_module('v4_checked_coverage_diagnostics', frozen['sources']['geometry'], base)
    binding = exact_module('v4_checked_report_data_binding', frozen['sources']['data_binding'], base)
    output = {}; cache_refs = {}; controls = 0; capped = {}; diagnostic_reports = {}
    for domain, manifest_path in (('native', native_manifest), ('synthetic', synthetic_manifest)):
        manifest_path = Path(manifest_path).resolve(); manifest = read_json(manifest_path)
        if (manifest.get('schema_version') != 4 or manifest.get('kind') != domain
                or manifest.get('scope') != frozen['scope'] or manifest.get('freeze_sha256') != anchor
                or manifest.get('versions') != frozen['versions'] or manifest.get('evaluation_complete') is not True):
            raise ValueError('run manifest is incomplete or differs from the frozen comparison')
        refs = manifest.get('outputs')
        if not isinstance(refs, list) or len(refs) != (len(frozen['native']['parents']) if domain == 'native' else 1):
            raise ValueError('missing or extra cache outputs')
        fields = []; left = []; right = []; seen = set(); cap_count = 0
        cache_refs[domain] = []; paths = set()
        for ref in refs:
            location = checked_ref({key: ref[key] for key in ('path', 'sha256')}, manifest_path.parent,
                                   maximum_bytes=2 * 1024**3)
            if str(location) in paths: raise ValueError('duplicate cache path')
            paths.add(str(location))
            with gzip.open(location, 'rt') as handle: cache = json.load(handle)
            if (cache.get('schema_version') != 4 or cache.get('kind') != domain
                    or cache.get('scope') != frozen['scope'] or cache.get('freeze_sha256') != anchor
                    or cache.get('versions') != frozen['versions'] or cache.get('models') != expected_models
                    or cache.get('source_sha256') != expected_sources
                    or cache.get('detector_settings') != frozen['detector_settings']
                    or cache.get('feature_contract_sha256') != expected_models['candidate']['feature_contract_sha256']
                    or cache.get('summary') != ref['summary'] or cache['summary'].get('evaluation_complete') is not True
                    or cache['summary'].get('error_trials') != 0):
                raise ValueError('cache provenance, model pair or completion differs')
            rows = cache.get('fields')
            if not isinstance(rows, list) or len(rows) != cache['summary']['planned']:
                raise ValueError('cache planned row count differs')
            if domain == 'synthetic' and (cache.get('generator') != dict(extended_every_nth_field=3, varying_psf=True)
                    or cache.get('calibration_bank') != frozen['synthetic']['calibration_bank']
                    or cache.get('parent_field_seeds') != frozen['synthetic']['seeds']):
                raise ValueError('synthetic calibration, generator or seed declaration differs')
            if domain == 'native':
                parent = next((p for p in frozen['native']['parents'] if p['parent_id'] == cache.get('parent_id')), None)
                if parent is None or parent['parent_id'] in seen or ref.get('parent_id') != parent['parent_id']:
                    raise ValueError('native parent missing, aliased or duplicated')
                seen.add(parent['parent_id'])
                if (cache.get('seed') != parent['seed'] or cache.get('center_deg') != parent['center_deg']
                        or cache.get('downloads_manifest') != parent['downloads_manifest']
                        or cache.get('preparation_options') != frozen['native']['region']
                        or {row['sha256'] for row in cache['input_sources']} != {row['sha256'] for row in parent['_observations']}):
                    raise ValueError('native acquisition or preparation differs')
                binding.validate_prepared_frames(frozen['_native_expected'][parent['parent_id']],
                                                 cache['frames'], cache['times_hours'])
                expected_trials = {(speed, direction, brightness) for speed in (.01, .03, .1, .3, 1., 4., 10., 25., 50.)
                                   for direction in range(6) for brightness in (3., 6., 12., 24., 48.)}
                actual_trials = {(row.get('speed_px_hour'), row.get('direction_id'), row.get('brightness')) for row in rows}
                if len(rows) != 270 or actual_trials != expected_trials:
                    raise ValueError('native fixed injection matrix is incomplete')
                control = cache.get('control', {})
                if (control.get('error') or any(label != -2 for label in control.get('matches', [0]))
                        or len(control.get('candidate_ids', [])) != len(control.get('matches', []))
                        or len(control.get('scores_c13', [])) != len(control.get('matches', []))
                        or len(control.get('scores_v4', [])) != len(control.get('matches', []))):
                    raise ValueError('native UNKNOWN control is incomplete or relabeled')
                controls += len(control['matches'])
            for row in rows:
                if domain == 'native' and (row.get('parent_id') != parent['parent_id'] or row.get('seed') != parent['seed']):
                    raise ValueError('native field identity differs')
                validate_field(row, domain, times=cache.get('times_hours') if domain == 'native' else None,
                               shape=cache.get('registered_shape') if domain == 'native' else None,
                               geometry_validator=geometry.validate_matched_geometry,
                               control=control if domain == 'native' else None)
                times = cache['times_hours'] if domain == 'native' else row['times_hours']
                truths = [row['expected_xy']] if domain == 'native' else row['expected_xy']
                capabilities = [row.get('geometric_capability')] if domain == 'native' else row.get('geometric_capabilities')
                if not isinstance(capabilities, list) or len(capabilities) != len(truths):
                    raise ValueError('missing coverage geometry diagnostics')
                for truth, stored in zip(truths, capabilities):
                    flags = row.get('center_usable_flags') if domain == 'native' else stored.get('center_usable_flags')
                    actual = capability.geometry_capability(truth, times, flags)
                    if stored != actual and stored != {**actual, 'center_usable_flags': flags}:
                        raise ValueError('stored coverage geometry differs from independently recomputed diagnostic')
                if domain == 'synthetic':
                    if row.get('seed') in seen: raise ValueError('duplicate synthetic field')
                    seen.add(row.get('seed'))
                fields.append(_slim(row)); left.append(row['scores_c13']); right.append(row['scores_v4'])
                cap_count += int(row.get('peak_cap_reached') is True)
            cache_refs[domain].append(dict(path=str(location), sha256=digest(location)))
            del cache
        expected = {p['parent_id'] for p in frozen['native']['parents']} if domain == 'native' else set(frozen['synthetic']['seeds'])
        if seen != expected: raise ValueError('run identities do not cover the exact frozen plan')
        output[domain] = paired.paired_report(fields, fields, left, right, bootstrap_samples=10000, bootstrap_seed=20261115)
        capped[domain] = cap_count; diagnostic_reports[domain] = diagnostics(fields, left, right, domain)
    validate_freeze(path, anchor)
    return dict(schema_version=4, scope=frozen['scope'], freeze_sha256=anchor,
                comparison='C13 and one frozen V4 scorer on identical measured proposals',
                reports=output, recovery_gate=metrics.recovery_gate(output['synthetic'], output['native'],
                    baseline_controls=controls, candidate_controls=controls),
                unknown_controls=dict(baseline_candidate_rows=controls, candidate_candidate_rows=controls,
                                      truth_labels='UNKNOWN; workload is not precision'),
                peak_cap_trials=capped, caches=cache_refs, diagnostics=diagnostic_reports,
                limitations=['injection recovery is not real-object sensitivity or survey precision',
                             'three-pixel geometry is a diagnostic, not an astrometric detection limit',
                             'model scores are uncalibrated', 'runtime/integration gates remain separate'])
