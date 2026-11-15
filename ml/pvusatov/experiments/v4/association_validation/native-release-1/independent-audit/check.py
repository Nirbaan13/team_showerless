"""Independent streaming native numeric-cache audit. No producer imports, pixels, models or rescoring.

Run only after root report-complete handoff: python check.py --freeze FREEZE --handoff HANDOFF --run RUN --report REPORT --output OUT
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
resource.setrlimit(resource.RLIMIT_AS, (8*1024**3, 8*1024**3))
resource.setrlimit(resource.RLIMIT_CPU, (3600, 3600))
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


HANDOFF_SHA = '6005fd136cdab828cac9c786c18fce2c4977289924f7ff94df3a3ddf92671abb'
METRICS = ('top1', 'top3', 'detected', 'resolved_top1', 'resolved_top3', 'unresolved_top1', 'unresolved_top3')


def spatial_match(epochs, xy, truth, missing=-2):
    best, mean = missing, math.inf
    xy = np.asarray(xy, dtype=float)
    for i, path in enumerate(truth):
        distances = np.sqrt(np.sum((xy-np.asarray(path)[epochs])**2, axis=1))
        if np.all(distances <= 1.5) and float(distances.mean()) < mean:
            best, mean = i, float(distances.mean())
    span = None
    if best >= 0:
        points = np.asarray(truth[best])[epochs]
        span = float(np.sqrt(np.sum((points[:, None]-points[None, :])**2, axis=2)).max())
    return best, span


def control_attribution(control, truth):
    return {role: any(spatial_match(e, xy, truth)[0] >= 0 for e, xy in control[role]) for role in ROLES}


def field_check(full, compact, control=None):
    rows, truth = full['candidates'], full['expected_xy']
    is_control = full['kind'] == 'native_control'
    assert full['error'] is None and full['truth_count'] == len(truth) == (0 if is_control else 1)
    assert full['hypothesis_count'] == len(rows) <= 50000
    assert full['hypothesis_work']['hypotheses'] == len(rows)
    assert full['hypothesis_work']['link_checks'] <= 2000000
    assert full['legacy_candidate_parity'] is True and full['legacy_feature_score_parity'] is True
    assert len(full['times_hours']) == len(full['peaks_per_epoch']) == 8
    assert len(full['registered_shape']) == 3 and full['registered_shape'][0] == 8
    assert all(0 <= n <= 100 for n in full['peaks_per_epoch'])
    assert full['peak_cap_reached'] == any(n >= 100 for n in full['peaks_per_epoch'])
    assert np.isfinite(full['times_hours']).all() and np.all(np.diff(full['times_hours']) > 0)
    labels, spans = [], []
    for i, row in enumerate(rows):
        assert row['pool_index'] == i and len(row['features_v4']) == 30
        epochs = row['epochs']
        assert len(epochs) >= 3 and len(set(epochs)) == len(epochs)
        assert [a for a, b in row['links']] == epochs
        assert len(row['positions_xy']) == len(row['links']) == len(epochs)
        assert np.isfinite(row['positions_xy']).all()
        assert math.isfinite(row['score']) and 0 <= row['score'] <= 1 and math.isfinite(row['baseline_score'])
        assert all(type(a) is int and type(b) is int and 0 <= a < 8 and 0 <= b < full['peaks_per_epoch'][a] for a, b in row['links'])
        label, span = spatial_match(epochs, row['positions_xy'], truth)
        assert label == row['match'] and span == row['matched_truth_span_px'], ('geometry mismatch', full['case_id'], i)
        labels.append(label)
        spans.append(span)
    for role in ROLES:
        kept, work = pruning(rows, role)
        assert kept == full['kept'][role] and work == full['policy_work'][role]
        assert recount(rows, kept, labels, spans) == full['policies'][role]
    for key in full:
        if key != 'candidates':
            assert full[key] == compact[key], ('full compact mismatch', full['case_id'], key)
    union = set(full['kept']['legacy']) | set(full['kept']['learned_pair'])
    assert compact['candidates'] == [row for i, row in enumerate(rows) if i in union or labels[i] >= 0]
    assert compact['retained_union_count'] == len(union)
    assert compact['offline_matched_fullpool_rows'] == sum(i >= 0 for i in labels)
    assert compact['full_pool_recovered_truths'] == len({i for i in labels if i >= 0})
    assert compact['full_pool_resolved_truths'] == len({i for i, s in zip(labels, spans) if i >= 0 and s >= 3})
    assert compact['full_feature_matrix_sha256'] == hashlib.sha256(canonical([r['features_v4'] for r in rows])).hexdigest()
    preexisting = dict.fromkeys(ROLES, False)
    if not is_control:
        assert control is not None, 'successful injection has no successful matching parent control'
        assert full['times_hours'] == control['times_hours'] and full['registered_shape'] == control['registered_shape']
        preexisting = control_attribution(control, truth)
    assert full['preexisting_control_match'] == preexisting
    assert full['attribution_eligible'] == (not any(preexisting.values()))
    geometry = None
    if is_control:
        geometry = {r: [(rows[i]['epochs'], rows[i]['positions_xy']) for i in full['kept'][r]] for r in ROLES}
        geometry.update(times_hours=full['times_hours'], registered_shape=full['registered_shape'])
    slim = {k: v for k, v in compact.items() if k not in ('candidates', 'expected_xy', 'times_hours', 'kept', 'simulation_metadata')}
    return slim, geometry


def summary(fields):
    groups = {}
    totals = {r: Counter() for r in ROLES}
    truths = 0
    for f in fields:
        group = groups.setdefault(f['parent_id'], dict(truths=0, **{r: Counter() for r in ROLES}))
        group['truths'] += f['truth_count']
        truths += f['truth_count']
        for r in ROLES:
            totals[r].update(f['policies'][r])
            group[r].update(f['policies'][r])
    positive = [groups[k] for k in sorted(groups, key=str) if groups[k]['truths'] > 0]
    result = dict(trials=len(fields), truth_count=truths, independent_groups=len(groups), groups_with_truth=len(positive), **{r: dict(totals[r]) for r in ROLES})
    deltas = {}
    for k in (1, 3):
        rates = {r: np.array([g[r]['top'+str(k)]/g['truths'] for g in positive]) for r in ROLES}
        for r in ROLES:
            result[r]['micro_recall'+str(k)] = totals[r]['top'+str(k)]/truths if truths else None
            result[r]['macro_recall'+str(k)] = float(rates[r].mean()) if positive else None
        deltas[k] = rates['learned_pair']-rates['legacy']
        result['macro_delta_top'+str(k)] = float(deltas[k].mean()) if positive else None
    rng = np.random.default_rng(2026111502)
    draws = {1: [], 3: []}
    if positive:
        for _ in range(100):
            indexes = rng.integers(len(positive), size=(100, len(positive)))
            for k in (1, 3):
                draws[k].extend(deltas[k][indexes].mean(axis=1))
    for k in (1, 3):
        result['paired_group_ci95_top'+str(k)] = np.quantile(draws[k], [.025, .975]).tolist() if positive else None
    return result


def expected_identities(groups):
    identities = {}
    for g in groups:
        p, seed = g['parent_id'], g['seed']
        identities[p+'-control'] = dict(case_id=p+'-control', parent_id=p, seed=seed, kind='native_control')
        for speed, direction, brightness in itertools.product((.01, .03, .1, .3, 1., 4., 10., 25., 50.), (0, 2, 4), (3., 6., 12., 24., 48.)):
            case = f'{p}-{speed:g}-{direction}-{brightness:g}'
            identities[case] = dict(case_id=case, parent_id=p, seed=seed, kind='native', speed_px_hour=speed, direction_id=direction, brightness=brightness)
    return identities


def descriptive_strata(fields):
    result = {}
    for key in ('parent_id', 'speed_px_hour', 'brightness'):
        for value in sorted({str(f.get(key)) for f in fields}):
            chosen = [f for f in fields if str(f.get(key)) == value]
            result[key+':'+value] = dict(planned=len(chosen), truths=sum(f.get('truth_count') or 0 for f in chosen), errors=sum(f.get('error') is not None for f in chosen),
                policies={r: {m: sum(f.get('policies', {}).get(r, {}).get(m, 0) for f in chosen) for m in METRICS} for r in ROLES})
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('freeze', 'handoff', 'run', 'report', 'output'):
        p.add_argument('--'+key, required=True, type=Path)
    p.add_argument('--repo-root', type=Path)
    p.add_argument('--cache-root', type=Path)
    args = p.parse_args()
    for original, replacement in [(ORIGINAL_REPO, args.repo_root), (ORIGINAL_CACHE, args.cache_root)]:
        if replacement:
            REBASE.append((original, replacement.resolve()))
    started = time.perf_counter()
    assert digest(args.freeze) == EXPECTED_R2 and digest(args.handoff) == HANDOFF_SHA
    frozen, handoff, run, report = map(read, (args.freeze, args.handoff, args.run, args.report))
    # The publisher writes this manifest only after every planned record closes.
    # Its complete flag means error-free, so failed trials must still be audited.
    assert run['planned'] == 1632 and run['complete'] == (run['error_records'] == 0)
    assert run['freeze_sha256'] == report['freeze_sha256'] == EXPECTED_R2
    assert run['kind'] == 'native'
    assert run['handoff']['sha256'] == HANDOFF_SHA
    checked(run['handoff'])
    assert report['production_promotion_authorized'] is False
    groups = sorted(handoff['groups'], key=lambda g: g['seed'])
    assert len(groups) == 12 and {g['seed'] for g in groups} == set(range(4110001, 4110013))
    plan = read(checked(frozen['native_plan']))
    amendment = read(checked(frozen['native_seed_amendment']))
    declared = {g['group_id']: g for g in plan['groups']}
    reservation = amendment['native_seed_reservation']
    assert amendment['original_plan_sha256'] == frozen['native_plan']['sha256']
    assert {g['parent_id'] for g in groups} == set(declared) == set(reservation)
    physical = []
    for g in groups:
        assert g['seed'] == reservation[g['parent_id']] and g['center'] == declared[g['parent_id']]['center']
        assert g['split'] == 'quarantined_association_holdout' and g['detector'] in (1, 2, 3) and len(g['images']) == 8
        physical.extend(r['obs_id'] for r in g['images'])
    assert len(physical) == len(set(physical)) == 96 and len(plan['excluded_physical_obsids']) == 438
    assert not (set(physical) & set(plan['excluded_physical_obsids']))
    expected = expected_identities(groups)
    assert len(run['outputs']) == len(expected) == 1632
    refs = {r['case_id']: r for r in run['outputs']}
    assert len(refs) == 1632 and set(refs) == set(expected)
    for key, identity in expected.items():
        assert all(refs[key].get(k) == v for k, v in identity.items()), ('identity mismatch', key)
    frozen_refs = list(frozen['sources'].values())+list(frozen['model'].values())+[frozen[k] for k in ('protocol', 'selection', 'calibration', 'native_plan', 'native_seed_amendment')]
    for ref in frozen_refs:
        checked(ref)
    fields, controls, hashes, cadence = [], [], [], {}
    compact_digests = {}
    candidates, max_hypotheses, max_link_checks, max_pair_ops = 0, 0, 0, 0
    error_records = []
    for group in groups:
        parent = group['parent_id']
        # A single parent's retained control geometry survives between field reads.
        control_geometry = None
        parent_ids = [parent+'-control']+[r['case_id'] for r in run['outputs'] if r['parent_id'] == parent and r['kind'] == 'native']
        for key in parent_ids:
            ref = refs[key]
            compact = read(checked(ref['compact']))
            assert all(compact.get(k) == v for k, v in expected[key].items())
            assert compact.get('error') == ref.get('error')
            compact_digests[key] = hashlib.sha256(canonical(compact)).hexdigest()
            binding = dict(case_id=key, compact=ref['compact']['sha256'], error=ref.get('error'))
            if ref.get('error') is not None:
                assert 'full_pool' not in ref
                slim = {k: v for k, v in compact.items() if k != 'candidates'}
                error_records.append(dict(case_id=key, error=ref['error']))
            else:
                full = read(checked(ref['full_pool']))
                assert compact['full_pool'] == ref['full_pool']
                assert all(full.get(k) == v for k, v in expected[key].items())
                slim, geometry = field_check(full, compact, control_geometry)
                binding['full_pool'] = ref['full_pool']['sha256']
                candidates += full['hypothesis_count']
                max_hypotheses = max(max_hypotheses, full['hypothesis_count'])
                max_link_checks = max(max_link_checks, full['hypothesis_work']['link_checks'])
                max_pair_ops = max(max_pair_ops, *(full['policy_work'][r]['budgeted_pair_keys'] for r in ROLES))
                if full['kind'] == 'native_control':
                    control_geometry = geometry
                    dt = np.diff(full['times_hours'])
                    cadence[parent] = dict(times_hours=full['times_hours'], time_sha256=hashlib.sha256(canonical(full['times_hours'])).hexdigest(),
                        epoch_count=8, minimum_spacing_hours=float(dt.min()), maximum_spacing_hours=float(dt.max()), span_hours=float(np.ptp(full['times_hours'])))
                del full
            (controls if ref['kind'] == 'native_control' else fields).append(slim)
            hashes.append(binding)
            del compact
        del control_geometry
    assert len(fields) == 1620 and len(controls) == 12
    domain = report['reports']['native']
    errors = sum(f.get('error') is not None for f in fields)
    unknown = sum(type(f.get('truth_count')) is not int or f['truth_count'] < 0 for f in fields)
    complete = errors == unknown == 0
    eligible = [f for f in fields if f.get('attribution_eligible') is True]
    assert domain['complete'] == complete and domain['planned_trials'] == 1620
    assert domain['error_trials'] == errors and domain['unknown_truth_trials'] == unknown
    assert domain['attribution_excluded_trials'] == 1620-len(eligible)
    assert domain['bootstrap_samples'] == 10000 and domain['bootstrap_seed'] == 2026111502
    all_summary = summary(fields) if complete else None
    common_summary = summary(eligible) if complete else None
    assert domain['all_planned'] == all_summary and domain['common_attributable'] == common_summary
    assert domain['strata'] == descriptive_strata(fields)
    for key in ('full_pool_recovered_truths', 'full_pool_resolved_truths', 'prediction_cpu_seconds', 'parity_cpu_seconds'):
        assert domain[key] == sum(f.get(key, 0) for f in fields)
    assert domain['hypotheses_total'] == sum(f.get('hypothesis_count', 0) for f in fields)
    assert domain['prediction_wall_seconds_sum'] == sum(f.get('prediction_wall_seconds', 0) for f in fields)
    assert domain['peak_cap_trials'] == sum(bool(f.get('peak_cap_reached')) for f in fields)
    assert domain['control_records'] == 12
    assert domain['controls'] == {r: sum(c.get('policies', {}).get(r, {}).get('candidate_rows', 0) for c in controls) for r in ROLES}
    assert run['error_records'] == len(error_records)
    assert report['complete'] == all(d['complete'] for d in report['reports'].values())
    portable = checked(report['portable'])
    seen = set()
    with gzip.open(portable, 'rt') as stream:
        header = json.loads(next(stream))
        assert header['freeze_sha256'] == EXPECTED_R2 and header['model'] == frozen['model']
        for line in stream:
            record = json.loads(line)
            if record['domain'] != 'native':
                continue
            f = record['field']
            assert record['record'] == 'field' and f['case_id'] not in seen
            assert hashlib.sha256(canonical(f)).hexdigest() == compact_digests[f['case_id']]
            seen.add(f['case_id'])
    assert seen == set(expected)
    result = dict(status='PASS' if complete and not error_records else 'INCOMPLETE', numeric_evidence_checks_passed=True,
        native_complete=complete, combined_report_complete=report['complete'], all_record_count=1632, injection_count=1620, control_count=12,
        error_records=error_records, unknown_truth_trials=unknown, freeze_sha256=EXPECTED_R2, handoff_sha256=HANDOFF_SHA,
        run_manifest_sha256=digest(args.run), report_sha256=digest(args.report), portable_sha256=digest(portable), checker_sha256=digest(__file__),
        model=frozen['model'], audited_candidate_rows=candidates, max_hypotheses=max_hypotheses, max_link_checks=max_link_checks, max_pair_operations=max_pair_ops,
        cap_fields=domain['peak_cap_trials'], native_all_planned=all_summary, native_common_attributable=common_summary,
        common_eligible_trials=len(eligible), attribution_excluded_trials=1620-len(eligible),
        per_parent={g['parent_id']: dict(all_planned=summary([f for f in fields if f['parent_id'] == g['parent_id']]) if complete else None,
            common_attributable=summary([f for f in eligible if f['parent_id'] == g['parent_id']]) if complete else None) for g in groups},
        native_cadence_by_parent=cadence, strata=domain['strata'], full_and_compact_bindings=hashes,
        control_workload=domain['controls'], controls_are_unknown_not_false_positives=True,
        raw_fits_opened=False, producer_functions_imported=False, scoring_or_simulation=False, production_promotion_authorized=False,
        full_cache_policy='one full field plus one compact field and one parent control geometry; only summaries/digests retained',
        elapsed_seconds=time.perf_counter()-started, peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+'\n')
    print(json.dumps({k: result[k] for k in ('status', 'all_record_count', 'audited_candidate_rows', 'error_records', 'elapsed_seconds', 'peak_rss_mib')}))


if __name__ == '__main__':
    main()


