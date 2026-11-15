"""Independent numeric-cache audit. No producer imports, pixels, models or rescoring.

Usage: python check.py --repair DIR --run RUN.json --report REPORT.json --output OUT.json
Requires only Python standard library and NumPy. References in manifests identify
the original immutable caches, which must remain available at their recorded paths.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import resource
import sys
import time

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
resource.setrlimit(resource.RLIMIT_AS, (4*1024**3, 4*1024**3))
resource.setrlimit(resource.RLIMIT_CPU, (900, 900))
import numpy as np

ROLES = ('legacy', 'learned_pair')
EXPECTED_R2 = 'ae981b56f43c8a14cd6dee9ce61c48853ea7c90b63eca8ddcf586e0a3e3dbbdd'
VOLATILE = {'prediction_wall_seconds', 'prediction_cpu_seconds', 'parity_cpu_seconds',
            'worker_peak_rss_mib', 'full_pool', 'freeze_sha256'}
ORIGINAL_REPO = Path('/home/usatovpavel/.codex/worktrees/spaceapps-zio-backend')
ORIGINAL_CACHE = Path('/tmp/spaceapps-association-validation')
REBASE = []


def relocated(path):
    p = Path(path)
    for original, replacement in REBASE:
        if p.is_relative_to(original):
            return replacement/p.relative_to(original)
    return p


def install_io_guard(args):
    """A Python open/list-event guard for the proof, not an OS sandbox."""
    assert args.repo_root and args.cache_root, 'I/O proof requires both relocated roots'
    repo, cache = args.repo_root.resolve(), args.cache_root.resolve()
    assert not repo.is_relative_to(ORIGINAL_REPO) and not cache.is_relative_to(ORIGINAL_CACHE)
    permitted = [repo, cache, args.output.resolve().parent]
    # NumPy is initialized above; lazy Python runtime/module reads remain permitted.
    permitted += [Path(sys.base_prefix).resolve()/'lib', Path(sys.prefix).resolve()/'lib']
    blocked = []
    def guard(event, event_args):
        if event not in ('open', 'os.listdir', 'os.scandir') or not isinstance(event_args[0], (str, bytes, os.PathLike)):
            return
        p = Path(os.fsdecode(event_args[0])).resolve()
        if p.is_relative_to(ORIGINAL_REPO) or p.is_relative_to(ORIGINAL_CACHE):
            blocked.append(str(p))
            raise PermissionError('portability proof denied original input: '+str(p))
        if not any(p.is_relative_to(root) for root in permitted):
            blocked.append(str(p))
            raise PermissionError('portability proof denied outside open: '+str(p))
    sys.addaudithook(guard)
    probes = [ORIGINAL_REPO/'ml/pvusatov/experiments/v4/association_validation/protocol.json',
              ORIGINAL_CACHE/'synthetic-repair-1/run-manifest.json', Path('/etc/passwd')]
    for p in probes:
        try:
            with p.open('rb') as stream:
                stream.read(1)
        except PermissionError:
            continue
        raise AssertionError('intentional forbidden-read probe was not rejected: '+str(p))
    return blocked


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    h = hashlib.sha256()
    with relocated(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def checked(ref, path=None):
    p = relocated(path or ref['path'])
    assert digest(p) == ref['sha256'], ('hash mismatch', str(p))
    if 'bytes' in ref:
        assert p.stat().st_size == ref['bytes'], ('size mismatch', str(p))
    return p


def read(path):
    p = relocated(path)
    with (gzip.open(p, 'rt') if p.suffix == '.gz' else p.open()) as stream:
        return json.load(stream)


def projection(field):
    return {k: v for k, v in field.items() if k not in VOLATILE}


def pruning(rows, role):
    key = 'baseline_score' if role == 'legacy' else 'score'
    order = sorted(range(len(rows)), key=lambda i: -rows[i][key])
    used = set()
    selected = []
    operations = 0
    for i in order:
        pairs = set(itertools.combinations(map(tuple, rows[i]['links']), 2))
        operations += len(pairs)
        assert operations <= 10_000_000
        if not (pairs & used):
            selected.append(i)
            used |= pairs
    return selected, dict(kept=len(selected), suppressed=len(rows)-len(selected),
                         budgeted_pair_keys=operations, complete=True)


def recount(rows, selected, labels, spans):
    order = sorted(selected, key=lambda i: -rows[i]['score'])
    result = {'candidate_rows': len(selected)}
    for name, ids in [('top1', order[:1]), ('top3', order[:3]), ('detected', order)]:
        found = {labels[i] for i in ids if labels[i] >= 0}
        resolved = {labels[i] for i in ids if labels[i] >= 0 and spans[i] >= 3.0}
        result[name] = len(found)
        result['resolved_'+name] = len(resolved)
        result['unresolved_'+name] = len(found-resolved)
    return result


def validate_field(full, compact):
    rows = full['candidates']
    assert full['error'] is None
    assert full['hypothesis_count'] == len(rows) <= 50_000
    assert full['hypothesis_work']['hypotheses'] == len(rows)
    assert full['hypothesis_work']['link_checks'] <= 2_000_000
    assert full['truth_count'] == len(full['expected_xy'])
    assert full['legacy_candidate_parity'] is True
    assert full['legacy_feature_score_parity'] is True
    assert all(0 <= n <= 100 for n in full['peaks_per_epoch'])
    assert full['peak_cap_reached'] == any(n >= 100 for n in full['peaks_per_epoch'])
    assert full['attribution_eligible'] is True
    assert full['preexisting_control_match'] == dict.fromkeys(ROLES, False)
    truth = np.asarray(full['expected_xy'], dtype=float)
    labels, spans = [], []
    for i, row in enumerate(rows):
        assert row['pool_index'] == i
        e = row['epochs']
        assert len(e) >= 3 and len(set(e)) == len(e)
        assert [link[0] for link in row['links']] == e
        assert len(row['links']) == len(row['positions_xy']) == len(e)
        assert all(type(epoch) is int and type(index) is int for epoch, index in row['links'])
        assert len(row['features_v4']) == 30
        assert math.isfinite(row['score']) and 0 <= row['score'] <= 1
        assert math.isfinite(row['baseline_score'])
        for epoch, index in row['links']:
            assert 0 <= epoch < len(full['peaks_per_epoch'])
            assert 0 <= index < full['peaks_per_epoch'][epoch]
        best, best_mean = -1, math.inf
        xy = np.asarray(row['positions_xy'], dtype=float)
        for target, path in enumerate(truth):
            distances = np.sqrt(np.sum((xy-path[e])**2, axis=1))
            if bool(np.all(distances <= 1.5)) and float(distances.mean()) < best_mean:
                best, best_mean = target, float(distances.mean())
        span = None
        if best >= 0:
            points = truth[best][e]
            # All actual matched epochs, including those farther apart than endpoints.
            span = float(np.sqrt(np.sum((points[:, None]-points[None, :])**2, axis=2)).max())
        assert best == row['match'], ('spatial label', full['case_id'], i)
        assert span == row['matched_truth_span_px'], ('truth span', full['case_id'], i)
        labels.append(best)
        spans.append(span)
    for role in ROLES:
        selected, work = pruning(rows, role)
        assert selected == full['kept'][role], ('pruning', full['case_id'], role)
        assert work == full['policy_work'][role]
        assert recount(rows, selected, labels, spans) == full['policies'][role]
    for key in full:
        if key != 'candidates':
            assert full[key] == compact[key], ('full/compact', full['case_id'], key)
    union = set(full['kept']['legacy']) | set(full['kept']['learned_pair'])
    retain = [row for i, row in enumerate(rows) if i in union or labels[i] >= 0]
    assert compact['candidates'] == retain
    assert compact['retained_union_count'] == len(union)
    assert compact['offline_matched_fullpool_rows'] == sum(x >= 0 for x in labels)
    assert compact['full_pool_recovered_truths'] == len({x for x in labels if x >= 0})
    assert compact['full_pool_resolved_truths'] == len({x for x, s in zip(labels, spans) if x >= 0 and s >= 3.0})
    assert compact['full_feature_matrix_sha256'] == hashlib.sha256(canonical([r['features_v4'] for r in rows])).hexdigest()
    return len(rows)


def aggregate(fields):
    # Synthetic fields are distinct resampling units. Empty fields remain workload.
    ordered = sorted(fields, key=lambda f: str(f['seed']))
    positive = [f for f in ordered if f['truth_count'] > 0]
    total_truth = sum(f['truth_count'] for f in ordered)
    result = dict(trials=len(fields), truth_count=total_truth, independent_groups=len(fields), groups_with_truth=len(positive))
    delta = {}
    for role in ROLES:
        totals = Counter()
        for f in ordered:
            totals.update(f['policies'][role])
        result[role] = dict(totals)
        for k in (1, 3):
            rate = np.array([f['policies'][role]['top'+str(k)]/f['truth_count'] for f in positive])
            result[role]['micro_recall'+str(k)] = totals['top'+str(k)]/total_truth
            result[role]['macro_recall'+str(k)] = float(rate.mean())
    for k in (1, 3):
        delta[k] = np.array([f['policies']['learned_pair']['top'+str(k)]/f['truth_count']-
                             f['policies']['legacy']['top'+str(k)]/f['truth_count'] for f in positive])
        result['macro_delta_top'+str(k)] = float(delta[k].mean())
    rng = np.random.default_rng(2026111502)
    draws = {1: [], 3: []}
    for _ in range(100):
        indexes = rng.integers(len(positive), size=(100, len(positive)))
        for k in (1, 3):
            draws[k].extend(delta[k][indexes].mean(axis=1))
    for k in (1, 3):
        result['paired_group_ci95_top'+str(k)] = np.quantile(draws[k], [.025, .975]).tolist()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('repair', 'run', 'report', 'output'):
        parser.add_argument('--'+arg, required=True, type=Path)
    parser.add_argument('--repo-root', type=Path, help='Rebase original repository provenance prefix only')
    parser.add_argument('--cache-root', type=Path, help='Rebase original scratch-cache provenance prefix only')
    parser.add_argument('--deny-original-inputs', action='store_true', help='Enable Python I/O portability proof guard, not an OS sandbox')
    args = parser.parse_args()
    for original, replacement in [(ORIGINAL_REPO, args.repo_root), (ORIGINAL_CACHE, args.cache_root)]:
        if replacement:
            REBASE.append((original, replacement.resolve()))
    denied_reads = install_io_guard(args) if args.deny_original_inputs else []
    started = time.perf_counter()
    frozen_path = args.repair/'freeze.json'
    assert digest(frozen_path) == EXPECTED_R2
    frozen = read(frozen_path)
    # Hash files only: no ONNX execution, NPZ deserialization or pixel access.
    freeze_refs = list(frozen['sources'].values()) + list(frozen['model'].values())
    freeze_refs += [frozen[k] for k in ('protocol', 'selection', 'calibration', 'native_plan', 'native_seed_amendment')]
    for ref in freeze_refs:
        checked(ref)
    assert frozen['model']['artifact']['sha256'] == 'c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
    assert frozen['model']['metadata']['sha256'] == '472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13'
    preserved = read(args.repair/'first-attempt-manifest.json')
    for ref in list(preserved['sources'].values()) + list(preserved['files'].values()):
        checked(ref, args.repair/ref['snapshot_path'])
    for ref in preserved['opaque_outputs']:
        checked(ref)
    first_freeze = read(args.repair/'first-attempt/freeze.json')
    assert set(first_freeze['sources']) == set(frozen['sources'])
    changed_sources = [name for name in frozen['sources']
                       if first_freeze['sources'][name]['sha256'] != frozen['sources'][name]['sha256']]
    assert changed_sources == ['runner']
    old_runner = (args.repair/preserved['sources']['runner']['snapshot_path']).read_text()
    new_runner = relocated(frozen['sources']['runner']['path']).read_text()
    old_text = 'links=[list(link)for link in links]'
    new_text = 'links=[[int(epoch),int(index)]for epoch,index in links]'
    assert old_runner.count(old_text) == 1
    assert old_runner.replace(old_text, new_text) == new_runner
    assert {k: v for k, v in first_freeze.items() if k != 'sources'} == {k: v for k, v in frozen.items() if k != 'sources'}
    first = read(args.repair/'first-attempt/run-manifest.json')
    run = read(args.run)
    assert run['complete'] is True and run['planned'] == 1000 and run['error_records'] == 0
    assert run['freeze_sha256'] == EXPECTED_R2 and run['kind'] == 'synthetic'
    old = {r['seed']: r for r in first['outputs']}
    new = {r['seed']: r for r in run['outputs']}
    assert len(old) == len(new) == 1000 and set(old) == set(new) == set(range(4100000, 4101000))
    fields, equality, candidates, empty_successes, errors = [], [], 0, 0, 0
    full_compact_hashes = []
    for seed in sorted(new):
        ref, before = new[seed], old[seed]
        identity = ['case_id', 'seed', 'kind', 'mode', 'cadence_family', 'simulation_metadata']
        preserved_identity = ['case_id', 'seed', 'kind']
        assert {k: ref[k] for k in preserved_identity} == {k: before[k] for k in preserved_identity}
        assert ref['case_id'] == 'synthetic-'+str(seed) and ref['error'] is None
        compact = read(checked(ref['compact']))
        full = read(checked(ref['full_pool']))
        assert compact['full_pool'] == ref['full_pool']
        assert all(compact[k] == ref[k] for k in identity)
        assert ref['truth_count'] == compact['truth_count']
        candidates += validate_field(full, compact)
        fields.append(compact)
        full_compact_hashes.append({'case_id': ref['case_id'], 'full': ref['full_pool']['sha256'], 'compact': ref['compact']['sha256']})
        if before['error'] is None:
            old_compact = read(checked(before['compact']))
            old_full = read(checked(before['full_pool']))
            assert old_full['hypothesis_count'] == 0
            assert projection(old_full) == projection(full), ('first success full equality', seed)
            assert projection(old_compact) == projection(compact), ('first success compact equality', seed)
            equality.append({'case_id': ref['case_id'], 'full_scientific_sha256': hashlib.sha256(canonical(projection(full))).hexdigest(),
                             'compact_scientific_sha256': hashlib.sha256(canonical(projection(compact))).hexdigest()})
            empty_successes += 1
        else:
            assert 'int64' in before['error']['message'] and 'JSON serializable' in before['error']['message']
            assert 'full_pool' not in before
            errors += 1
    assert empty_successes == 152 and errors == 848
    report = read(args.report)
    assert report['freeze_sha256'] == EXPECTED_R2 and report['production_promotion_authorized'] is False
    assert report['complete'] is False
    native = report['reports']['native']
    assert native['complete'] is False and native['missing_trials'] == native['planned_trials'] == 1620
    synthetic = report['reports']['synthetic']
    summary = aggregate(fields)
    assert synthetic['all_planned'] == synthetic['common_attributable'] == summary
    assert synthetic['complete'] is True and synthetic['planned_trials'] == 1000
    for key in ('error_trials', 'unknown_truth_trials', 'attribution_excluded_trials', 'control_records'):
        assert synthetic[key] == 0
    assert synthetic['bootstrap_samples'] == 10000 and synthetic['bootstrap_seed'] == 2026111502
    assert synthetic['peak_cap_trials'] == sum(f['peak_cap_reached'] for f in fields)
    assert synthetic['hypotheses_total'] == candidates
    for key in ('full_pool_recovered_truths', 'full_pool_resolved_truths', 'prediction_cpu_seconds', 'parity_cpu_seconds'):
        assert synthetic[key] == sum(f[key] for f in fields)
    assert synthetic['prediction_wall_seconds_sum'] == sum(f['prediction_wall_seconds'] for f in fields)
    for key in ('mode', 'cadence_family'):
        for value in {str(f[key]) for f in fields}:
            selected = [f for f in fields if str(f[key]) == value]
            strata = synthetic['strata'][key+':'+value]
            assert strata['planned'] == len(selected) and strata['truths'] == sum(f['truth_count'] for f in selected) and strata['errors'] == 0
            for role in ROLES:
                for metric in strata['policies'][role]:
                    assert strata['policies'][role][metric] == sum(f['policies'][role][metric] for f in selected)
    portable = checked(report['portable'])
    with gzip.open(portable, 'rt') as stream:
        header = json.loads(next(stream))
        assert header['freeze_sha256'] == EXPECTED_R2 and header['model'] == frozen['model']
        portable_fields = [json.loads(line) for line in stream]
    assert len(portable_fields) == 1000
    assert {x['field']['case_id']: x['field'] for x in portable_fields} == {f['case_id']: f for f in fields}
    assert all(x['domain'] == 'synthetic' and x['record'] == 'field' for x in portable_fields)
    outputs = dict(status='PASS', complete_synthetic=True, overall_research_complete=False,
        designation='Independent numeric accounting and constrained repeat-equality audit; research only',
        freeze_sha256=EXPECTED_R2, model=frozen['model'], first_attempt_manifest_sha256=digest(args.repair/'first-attempt-manifest.json'),
        run_manifest_sha256=digest(args.run), producer_report_sha256=digest(args.report), portable_sha256=digest(portable),
        checker_sha256=digest(__file__), producer_functions_imported=False, raw_pixels_read=False, model_execution=False,
        portability_rebased_roots={str(a): str(b) for a, b in REBASE},
        python_io_guard_enabled=args.deny_original_inputs, python_io_guard_is_os_sandbox=False,
        intentional_original_and_outside_read_probes_rejected=denied_reads,
        changed_frozen_sources=changed_sources, exact_publication_boundary_only_source_change=True,
        freeze_reference_hash_checks=len(freeze_refs), preserved_source_hash_checks=len(preserved['sources']),
        preserved_artifact_hash_checks=len(preserved['files']), preserved_opaque_hash_checks=len(preserved['opaque_outputs']),
        identity_equality_fields=1000, identity_equality_keys=['case_id', 'seed', 'kind'],
        original_error_metadata_absent=['mode', 'cadence_family', 'simulation_metadata'], scientific_projection_equality_fields=152,
        original_error_fields_without_complete_scientific_comparison=848,
        equality_excluded_keys=sorted(VOLATILE), root_inspected_incomplete_aggregate=True, fully_blinded_repair=False,
        audited_candidate_rows=candidates, zero_hypothesis_fields=sum(f['hypothesis_count'] == 0 for f in fields),
        zero_truth_fields=sum(f['truth_count'] == 0 for f in fields), peak_cap_fields=synthetic['peak_cap_trials'],
        link_check_max=max(f['hypothesis_work']['link_checks'] for f in fields),
        hypothesis_max=max(f['hypothesis_count'] for f in fields),
        pair_operation_max=max(f['policy_work'][r]['budgeted_pair_keys'] for f in fields for r in ROLES),
        synthetic=summary, native_missing_trials=1620, production_promotion_authorized=False,
        full_and_compact_hashes=full_compact_hashes, exact_successful_scientific_projections=equality,
        elapsed_seconds=time.perf_counter()-started, peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    args.output.write_text(json.dumps(outputs, indent=2, sort_keys=True, allow_nan=False)+'\n')
    print(json.dumps({k: outputs[k] for k in ('status', 'audited_candidate_rows', 'identity_equality_fields', 'scientific_projection_equality_fields', 'elapsed_seconds', 'peak_rss_mib')}))


if __name__ == '__main__':
    main()
