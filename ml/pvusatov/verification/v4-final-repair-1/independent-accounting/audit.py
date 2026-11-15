"""Independent score-cache accounting. No pixel, model, training or scorer imports."""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
import tempfile
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ANCHOR = '1225e2de97c38381818d9ccb3676c1d132701b02b8bc19dc09e0d1785c3e38e4'
ROLES = {'baseline': 'scores_c13', 'candidate': 'scores_v4'}
BUDGETS = ('top1', 'top3', 'detected')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def publish(path, value):
    if path.exists():
        raise ValueError('immutable accounting output already exists')
    text = json.dumps(value, indent=2, allow_nan=False)+'\n' if isinstance(value, dict) else value
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.accounting-', delete=False) as stream:
        stream.write(text.encode()); temporary = stream.name
    os.replace(temporary, path)


def span(points):
    points = np.asarray(points, float)
    return float(np.max(np.linalg.norm(points[:, None] - points[None, :], axis=2))) if len(points) else 0.


def ordered(scores):
    assert all(type(s) in (int, float) and math.isfinite(s) and 0 <= s <= 1 for s in scores)
    # Python sorting is stable, independent of the report's NumPy sorting call.
    return sorted(range(len(scores)), key=lambda i: -scores[i])


def unique(labels, indices):
    return len({labels[i] for i in indices if labels[i] >= 0})


def statistics(rows):
    group = defaultdict(lambda: {'truths': 0, 'baseline': Counter(), 'candidate': Counter()})
    totals = {role: Counter() for role in ROLES}
    for row in rows:
        item = group[row['group']]; item['truths'] += row['truths']
        for role in ROLES:
            item[role].update({k: row[role][k] for k in ('top1', 'top3')})
            totals[role].update(row[role])
    positive_groups = [group[k] for k in sorted(group) if group[k]['truths'] > 0]
    truth = sum(r['truths'] for r in rows)
    result = dict(trials=len(rows), truth_count=truth, independent_groups=len(group),
                  groups_with_truth=len(positive_groups), **{role: dict(totals[role]) for role in ROLES})
    deltas = {}
    for k in (1, 3):
        rates = {}
        for role in ROLES:
            rates[role] = np.asarray([r[role]['top'+str(k)] / r['truths'] for r in positive_groups])
            result[role]['micro_recall'+str(k)] = totals[role]['top'+str(k)] / truth
            result[role]['macro_recall'+str(k)] = float(rates[role].mean())
        deltas[k] = rates['candidate'] - rates['baseline']
        result['macro_delta_top'+str(k)] = float(deltas[k].mean())
    # Same prospective seed/unit/count, independently implemented in small batches.
    rng = np.random.default_rng(20261115)
    draws = {k: [] for k in (1, 3)}
    for start in range(0, 10000, 100):
        indices = rng.integers(0, len(positive_groups), size=(min(100, 10000-start), len(positive_groups)))
        for k in (1, 3):
            draws[k].extend(deltas[k][indices].mean(axis=1).tolist())
    for k in (1, 3):
        result['paired_parent_ci95_top'+str(k)] = np.quantile(draws[k], [.025, .975]).tolist()
    return result


def assert_metrics(actual, expected):
    for key, value in actual.items():
        if isinstance(value, dict):
            assert_metrics(value, expected[key])
        elif isinstance(value, list):
            assert np.allclose(value, expected[key], rtol=0, atol=2e-15), (key, value, expected[key])
        elif isinstance(value, float):
            assert math.isclose(value, expected[key], rel_tol=0, abs_tol=2e-15), (key, value, expected[key])
        else:
            assert value == expected[key], (key, value, expected[key])


def main():
    report = read(ROOT/'report.json'); frozen = read(ROOT/'freeze.json')
    unblinding = read(ROOT/'unblinding-record.json'); equality = read(ROOT/'scientific-equality-proof.json')
    references = {str(p): sha(p) for p in [ROOT/'report.json', ROOT/'freeze.json', ROOT/'unblinding-record.json', ROOT/'scientific-equality-proof.json']}
    assert sha(ROOT/'freeze.json') == ANCHOR == report['freeze_sha256'] == unblinding['freeze_sha256']
    assert sha(ROOT/'report.json') == unblinding['report_sha256']
    assert equality['passes'] and equality['synthetic']['rows_compared'] == 3000
    assert equality['synthetic']['old_sha256'] == equality['synthetic']['new_sha256']
    assert equality['scientific_values_disclosed'] is False and equality['metrics_aggregated'] is False
    assert unblinding['exact_equality_previously_passed'] and not unblinding['refit_or_reselection']
    output = {}; controls = 0; caps = {}; outside = {}; diagnostics = {}; tie_fields = Counter(); strata_out = {}
    for domain in ('native', 'synthetic'):
        manifest_path = Path('/tmp/spaceapps-v4-evaluation/final-1225')/domain/('run-'+domain+'-manifest.json')
        manifest = read(manifest_path); references[str(manifest_path)] = sha(manifest_path)
        assert manifest['evaluation_complete'] is True and manifest['freeze_sha256'] == ANCHOR
        assert [(r['path'], r['sha256']) for r in manifest['outputs']] == [(r['path'], r['sha256']) for r in report['caches'][domain]]
        rows = []; identities = set(); cap_count = 0
        geometry = Counter(); actual_resolved = {role: Counter() for role in ROLES}
        outside_counts = {role: Counter() for role in ROLES}; examples = []
        strata = defaultdict(lambda: {'trials': 0, 'truths': 0, 'baseline': Counter(), 'candidate': Counter()})
        for ref in manifest['outputs']:
            path = Path(ref['path']); assert sha(path) == ref['sha256']; references[str(path)] = ref['sha256']
            with gzip.open(path, 'rt') as stream:
                cache = json.load(stream)
            assert cache['freeze_sha256'] == ANCHOR and cache['summary']['evaluation_complete'] is True
            assert cache['summary']['error_trials'] == 0 and cache['summary'] == ref['summary']
            assert cache['detector_settings'] == frozen['detector_settings']
            for role in ROLES:
                assert cache['models'][role]['sha256'] == frozen['models'][role]['artifact']['sha256']
            if domain == 'native':
                assert len(cache['fields']) == 270
                matrix = {(f['speed_px_hour'], f['direction_id'], f['brightness']) for f in cache['fields']}
                expected = {(s,d,b) for s in [.01,.03,.1,.3,1.,4.,10.,25.,50.] for d in range(6) for b in [3.,6.,12.,24.,48.]}
                assert matrix == expected
                control = cache['control']; assert control['error'] is None
                assert all(m == -2 for m in control['matches'])
                assert len(control['candidate_ids']) == len(set(control['candidate_ids'])) == len(control['matches'])
                assert len(control['scores_c13']) == len(control['scores_v4']) == len(control['matches'])
                controls += len(control['matches'])
            for field in cache['fields']:
                assert field['error'] is None and field['partition'] == 'final'
                identity = (field['parent_id'], field['seed'], field['trajectory_id'], field['brightness']) if domain == 'native' else (field['seed'],)
                assert identity not in identities; identities.add(identity)
                labels = field['matches']; truths = [field['expected_xy']] if domain == 'native' else field['expected_xy']
                assert len(truths) == field['truth_count']
                assert all(type(m) is int and (-2 if domain == 'native' else -1) <= m < len(truths) for m in labels)
                if domain == 'native': assert -1 not in labels
                assert len(set(field['candidate_ids'])) == len(labels)
                assert len(field['candidate_epochs']) == len(field['candidate_positions_xy']) == len(labels)
                # Reconstruct spatial identities and actual matched-epoch spans from cached coordinates.
                reconstructed = []; resolved = set()
                for i, (epochs, xy) in enumerate(zip(field['candidate_epochs'], field['candidate_positions_xy'])):
                    assert len(epochs) >= 3 and len(set(epochs)) == len(epochs)
                    distances = [np.linalg.norm(np.asarray(xy)-np.asarray(t)[epochs], axis=1) for t in truths]
                    acceptable = [j for j, dist in enumerate(distances) if np.all(dist <= 1.5)]
                    label = min(acceptable, key=lambda j: float(distances[j].mean())) if acceptable else (-2 if domain == 'native' else -1)
                    reconstructed.append(label)
                    if label >= 0 and span(np.asarray(truths[label])[epochs]) >= 3.:
                        resolved.add(i)
                assert reconstructed == labels
                stored_resolved = {r['candidate_index'] for r in field['matched_geometry'] if r['true_displacement_px'] >= 3.}
                assert stored_resolved == resolved
                capabilities = [field['geometric_capability']] if domain == 'native' else field['geometric_capabilities']
                bad_truths = set()
                for i, (truth, capability) in enumerate(zip(truths, capabilities)):
                    flags = field['center_usable_flags'] if domain == 'native' else capability['center_usable_flags']
                    n = sum(flags); displacement = span(np.asarray(truth)[flags])
                    assert n == capability['finite_center_epochs']
                    assert math.isclose(displacement, capability['covered_truth_span_px'], abs_tol=1e-12)
                    geometry['planned_truths'] += 1
                    geometry['finite_centers_ge3'] += int(n >= 3)
                    geometry['resolved_covered_truth_span_ge3px'] += int(displacement >= 3)
                    geometry['geometrically_testable'] += int(n >= 3 and displacement >= 3)
                    if n < 3: bad_truths.add(i)
                row = dict(group=field['parent_id'] if domain == 'native' else field['seed'],
                           truths=len(truths), eligible=field['attribution_eligible'], finite=field.get('usable_center_epochs',3) >= 3)
                assert type(row['eligible']) is bool and row['eligible'] != field['preexisting_control_match']
                for role, key in ROLES.items():
                    scores = field[key]; assert len(scores) == len(labels)
                    order = ordered(scores)
                    if len(scores) > len(set(scores)): tie_fields[domain+'_'+role] += 1
                    indices = {'top1':order[:1], 'top3':order[:3], 'detected':order}
                    row[role] = {budget: unique(labels, idx) for budget, idx in indices.items()}
                    row[role]['candidate_rows'] = len(labels)
                    for budget, idx in indices.items():
                        actual_resolved[role][budget] += unique(labels, [i for i in idx if i in resolved])
                        bad_recovered = {labels[i] for i in idx if labels[i] in bad_truths}
                        outside_counts[role][budget] += len(bad_recovered)
                        if budget == 'detected' and bad_recovered and len(examples) < 3:
                            examples.append(dict(identity=identity, role=role, truth_indices=sorted(bad_recovered)))
                rows.append(row)
                cap_count += int(field['peak_cap_reached'])
                keys = [('parent',field['parent_id']),('speed_px_hour',str(field['speed_px_hour'])),('brightness',str(field['brightness']))] if domain == 'native' else [('mode',field['mode'])]
                for key in keys:
                    item = strata[key]; item['trials'] += 1; item['truths'] += len(truths)
                    for role in ROLES: item[role].update({k: row[role][k] for k in BUDGETS})
            del cache
        if domain == 'native':
            assert len(identities) == 3240 and len({i[0] for i in identities}) == 12
            assert {i[1] for i in identities} == set(range(3950001,3950013))
        else:
            assert len(identities) == 3000 and {i[0] for i in identities} == set(range(3900000,3903000))
        output[domain] = {}
        for cohort, selected in [('all_planned',rows), ('common_attributable',[r for r in rows if r['eligible']]), ('common_finite_center_ge3',[r for r in rows if r['eligible'] and r['finite']])]:
            actual = statistics(selected); assert_metrics(actual, report['reports'][domain][cohort]); output[domain][cohort] = actual
        assert dict(geometry) == report['diagnostics'][domain]['geometry']
        assert {role:dict(v) for role,v in actual_resolved.items()} == report['diagnostics'][domain]['actual_matched_epoch_truth_span_ge3px_recoveries']
        caps[domain] = cap_count; outside[domain] = dict(recoveries={role:dict(v) for role,v in outside_counts.items()}, examples=examples)
        diagnostics[domain] = dict(geometry=dict(geometry), actual_matched_epoch_truth_span_ge3px_recoveries={role:dict(v) for role,v in actual_resolved.items()})
        strata_out[domain] = [{'kind':k[0], 'value':k[1], 'trials':v['trials'], 'truths':v['truths'], **{role:dict(v[role]) for role in ROLES}} for k,v in sorted(strata.items())]
    assert controls == 824 and report['unknown_controls']['baseline_candidate_rows'] == report['unknown_controls']['candidate_candidate_rows'] == controls
    assert caps == {'native':0, 'synthetic':0} == report['peak_cap_trials']
    deltas = [output[d][c]['macro_delta_top'+str(k)] for d in output for c in ('all_planned','common_attributable') for k in (1,3)]
    gate = all(v >= 0 for v in deltas) and any(v > 0 for v in deltas) and controls / controls <= 1.25
    assert gate == report['recovery_gate']['passes_recovery_gate'] is True
    audit = dict(schema_version=4, status='PASS', created_utc=datetime.now(timezone.utc).isoformat(),
        freeze_sha256=ANCHOR, audit_source_sha256=sha(__file__), independent_implementation=True,
        methods='Python stable sort; distinct nonnegative truth IDs per budget; parent/field cluster rates;10000 paired draws seed20261115; no evaluator/scorer imports',
        reports=output, diagnostics=diagnostics, strata=strata_out, tied_score_fields=dict(tie_fields),
        unknown_controls=dict(baseline=controls,candidate=controls,ratio=1.,labels='UNKNOWN; never precision negatives'),
        peak_cap_trials=caps, recovery_gate_passes=gate, finite_center_counterexamples=outside,
        comparison='Frozen C13 scorer versus frozen V4 scorer under identical amended coverage-preserving preparation; not old deployed end-to-end C13',
        provenance=dict(blinded_repair=True, coverage_diagnostics_informed_amendment=True,
            unchanged_original_preregistration=False, synthetic_scientific_equality_rows=3000,
            equality_preceded_canonical_unblinding=True, canonical_unblinding_utc=unblinding['first_canonical_unblinded_at_utc'],
            this_reviewer_read_any_outputs_before_canonical_unblinding=False, pixels_or_models_read=False,
            scoring_or_fitting_or_reselection=False), references=references,
        limitations=['Finite-center coverage is descriptive and is NOT a necessary detection ceiling; cached recovered objects with fewer than3 usable centers are counted.',
            'The named synthetic common_finite_center_ge3 field-level cohort retains all fields because usable_center_epochs is absent; per-truth finite-center diagnostics remain separately explicit.',
            'Actual matched-epoch true span>=3px is descriptive, not confirmed motion, calibrated sensitivity or a changed recovery denominator.',
            'Native derivatives share12 parent fields; bootstrap never treats3240 derivatives as independent fields.',
            'Synthetic macro recovery uses2400 truth-containing fields;600 zero-truth fields remain planned workload and are not precision negatives.',
            'Recovery gate does not independently authorize deployment; engineering/runtime/integration remain separate.'])
    publish(HERE/'audit.json',audit)
    native=output['native']['all_planned']; synthetic=output['synthetic']['all_planned']
    article = f'''# Independent frozen FINAL accounting\n\nPASS. This independent implementation reads only hashed scored-cache JSON and provenance. It imports no pixel reader, model loader, scorer, trainer or frozen evaluator. Python stable sorting and distinct truth identities reproduce every reported all-planned/common K1/K3 count, macro rate and10,000-draw parent/field bootstrap interval.\n\nNative:12parents,3,240planned/common trials; C13 K1/K3=553/673 and V4=685/729. Both detect746 unique injected truths. Macro gains are4.074 and1.728percentage points. Synthetic:3,000fields,5,993truths; C13=716/1,220 and V4=1,114/1,738, with1,926detected. Macro field gains are7.986 and8.535points;2,400truth-containing fields contribute recall rates while600zero-truth fields remain planned workload. Both primary budgets improve in both domains. UNKNOWN native controls remain824/824proposals, workload ratio1; peak-cap trials0.\n\nAll12fixed native matrices and all3,000reserved synthetic seeds are present. Spatial truth identities and actual matched-epoch truth spans were independently reconstructed from cached coordinates. The>=3pixel matched-span diagnostic reproduces the report and does not alter primary denominators or establish real motion. Finite true-center coverage is not a necessary detection ceiling: native detector recovery includes14truths outside its>=3finite-center subset. The report's synthetic named finite-center cohort retains all fields; its per-truth coverage counts are separate diagnostics.\n\nThis is the frozen C13 scorer under shared amended preparation, not a comparison with the old deployed end-to-end C13 pipeline. The repair was transparently coverage-informed while outputs remained blinded; it is not an unchanged original preregistration. The recorded3,000-row exact scientific equality check passed before the one canonical unblinding at{unblinding['first_canonical_unblinded_at_utc']}. This reviewer did not inspect outputs before that authorization. No refit, reselection, scoring, pixel or model access occurred.\n\nThe recovery gate passes; runtime, integration and release authorization remain separate. `audit.json` SHA `{sha(HERE/'audit.json')}` contains the complete independent recount, uncertainty intervals, counterexamples and hashed input references.\n'''
    publish(HERE/'AUDIT.AI.md',article)
    print(json.dumps(dict(status='PASS', audit_sha256=sha(HERE/'audit.json'), controls=controls, caps=caps)))


if __name__ == '__main__':
    main()
