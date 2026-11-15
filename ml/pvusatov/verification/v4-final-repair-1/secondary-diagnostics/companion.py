"""Post-hoc per-truth coverage accounting from immutable scored JSON only."""
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
import tempfile
import numpy as np

HERE = Path(__file__).resolve().parent
REPAIR = HERE.parent
BASE = REPAIR.parents[1]
ANCHOR = '1225e2de97c38381818d9ccb3676c1d132701b02b8bc19dc09e0d1785c3e38e4'
ROLES = {'baseline': 'scores_c13', 'candidate': 'scores_v4'}
BUDGETS = {'top1': 1, 'top3': 3, 'detected': None}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, text):
    if path.exists():
        raise ValueError('new immutable output required')
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.secondary-', delete=False) as stream:
        stream.write(text.encode()); temporary = stream.name
    os.replace(temporary, path)


def eligible_counts(labels, scores, eligible):
    """Eligibility changes truth counting, never competitor order or budget."""
    assert len(labels) == len(scores)
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    return {budget: len({labels[i] for i in (order if k is None else order[:k])
                        if labels[i] in eligible}) for budget, k in BUDGETS.items()}


def cohort_statistics(rows):
    eligible_rows = [r for r in rows if r['eligible_truths']]
    denominator = sum(r['eligible_truths'] for r in rows)
    result = dict(planned_fields=len(rows), fields_with_eligible_truth=len(eligible_rows),
        empty_eligible_fields=len(rows)-len(eligible_rows),
        original_truths=sum(r['original_truths'] for r in rows), eligible_truths=denominator,
        original_truth_containing_but_empty_eligible_fields=sum(r['original_truths'] > 0 and r['eligible_truths'] == 0 for r in rows),
        original_zero_truth_fields=sum(r['original_truths'] == 0 for r in rows),
        original_candidate_rows=sum(r['candidate_rows'] for r in rows),
        original_candidate_rows_in_empty_eligible_fields=sum(r['candidate_rows'] for r in rows if r['eligible_truths'] == 0))
    if not eligible_rows:
        result['recall_defined'] = False
        return result
    d = np.asarray([r['eligible_truths'] for r in eligible_rows], float)
    counts = {role: {b: np.asarray([r[role][b] for r in eligible_rows], float) for b in BUDGETS} for role in ROLES}
    for role in ROLES:
        result[role] = {b: int(counts[role][b].sum()) for b in BUDGETS}
        result[role]['micro_recall'] = {b: float(counts[role][b].sum()/denominator) for b in BUDGETS}
        result[role]['field_macro_recall'] = {b: float(np.mean(counts[role][b]/d)) for b in BUDGETS}
    result['recall_defined'] = True
    result['delta'] = {}
    boot = {b: {'field_macro': [], 'micro': []} for b in ('top1', 'top3')}
    rng = np.random.default_rng(20261115)
    for start in range(0, 10000, 100):
        draws = rng.integers(0, len(eligible_rows), size=(min(100, 10000-start), len(eligible_rows)))
        for budget in boot:
            difference = counts['candidate'][budget]-counts['baseline'][budget]
            boot[budget]['field_macro'].extend((difference/d)[draws].mean(axis=1).tolist())
            boot[budget]['micro'].extend((difference[draws].sum(axis=1)/d[draws].sum(axis=1)).tolist())
    for budget in boot:
        difference = counts['candidate'][budget]-counts['baseline'][budget]
        result['delta'][budget] = dict(field_macro=float(np.mean(difference/d)), micro=float(difference.sum()/denominator),
            field_macro_paired_field_ci95=np.quantile(boot[budget]['field_macro'], [.025,.975]).tolist(),
            micro_paired_field_ci95=np.quantile(boot[budget]['micro'], [.025,.975]).tolist())
    result['uncertainty'] = dict(unit='whole field with at least one eligible truth; paired counts and denominators resampled together',
        empty_eligible_fields='retain workload; undefined recall, excluded from conditional field-macro resampling',
        samples=10000, seed=20261115, interval='percentile 2.5/97.5; post-hoc descriptive, no multiplicity adjustment')
    return result


def main():
    report = read(REPAIR/'report.json'); unblinding = read(REPAIR/'unblinding-record.json')
    assert sha(REPAIR/'report.json') == unblinding['report_sha256']
    assert sha(REPAIR/'freeze.json') == report['freeze_sha256'] == ANCHOR
    manifest_path = Path('/tmp/spaceapps-v4-evaluation/final-1225/synthetic/run-synthetic-manifest.json')
    manifest = read(manifest_path)
    assert manifest['evaluation_complete'] is True and manifest['freeze_sha256'] == ANCHOR
    assert [(r['path'],r['sha256']) for r in manifest['outputs']] == [(r['path'],r['sha256']) for r in report['caches']['synthetic']]
    references = {str(p):sha(p) for p in [REPAIR/'report.json',REPAIR/'freeze.json',REPAIR/'unblinding-record.json',manifest_path]}
    definitions = {
        'finite_true_centers_ge3': ('finite_center_epochs>=3', lambda c: c['finite_center_epochs'] >= 3),
        'finite_true_centers_ge3_and_covered_span_ge3px': ('finite_center_epochs>=3 AND covered_truth_span_px>=3',
                                                        lambda c: c['finite_center_epochs'] >= 3 and c['covered_truth_span_px'] >= 3),
        'fewer_than3_finite_true_centers_counterexample_cohort': ('finite_center_epochs<3', lambda c: c['finite_center_epochs'] < 3),
    }
    rows = {name: [] for name in definitions}; seeds = set(); competing_ineligible_top1 = {name:dict(baseline=0,candidate=0) for name in rows}
    for ref in manifest['outputs']:
        cache_path = Path(ref['path']); assert sha(cache_path) == ref['sha256']; references[str(cache_path)] = ref['sha256']
        with gzip.open(cache_path,'rt') as stream:
            cache = json.load(stream)
        assert cache['summary']['evaluation_complete'] is True and cache['summary']['error_trials'] == 0
        assert cache['freeze_sha256'] == ANCHOR
        for field in cache['fields']:
            seed = field['seed']; assert seed not in seeds; seeds.add(seed)
            labels = field['matches']; capabilities = field['geometric_capabilities']; n = field['truth_count']
            assert len(capabilities) == n and field['error'] is None
            for name, (_, predicate) in definitions.items():
                eligible = {i for i,c in enumerate(capabilities) if predicate(c)}
                row = dict(seed=seed, original_truths=n, eligible_truths=len(eligible),candidate_rows=len(labels))
                for role,key in ROLES.items():
                    scores = field[key]
                    assert len(scores) == len(labels) and all(np.isfinite(scores))
                    row[role] = eligible_counts(labels,scores,eligible)
                    if eligible and scores:
                        index = min(range(len(scores)), key=lambda i: -scores[i])
                        competing_ineligible_top1[name][role] += int(labels[index] >= 0 and labels[index] not in eligible)
                rows[name].append(row)
    assert seeds == set(range(3900000,3903000))
    cohorts = {name: dict(eligibility=definitions[name][0], **cohort_statistics(value),
                         ineligible_injected_truth_occupies_original_top1=competing_ineligible_top1[name]) for name,value in rows.items()}
    assert cohorts['finite_true_centers_ge3']['eligible_truths'] == report['diagnostics']['synthetic']['geometry']['finite_centers_ge3'] == 5780
    counterexample = BASE/'experiments/v4/detection/results/finite-centre-diagnostic-counterexample.json'
    interpretation = BASE/'experiments/v4/detection/results/FINITE-CENTRE-INTERPRETATION.AI.md'
    for p in [counterexample,interpretation]: references[str(p)] = sha(p)
    assert sha(counterexample).startswith('6591aba0')
    result = dict(schema_version=4, designation='POST-HOC DESCRIPTIVE per-truth coverage companion; not a gate or selection input',
        created_utc=datetime.now(timezone.utc).isoformat(), source_sha256=sha(__file__), freeze_sha256=ANCHOR,
        canonical_unblinding_utc=unblinding['first_canonical_unblinded_at_utc'],
        ranking_policy='Original stable full-pool order and original K1/K3 positions; all ineligible competitors remain; unique eligible truth IDs counted only after taking each original budget',
        denominator_policy='Eligible injected truth IDs per whole field; sum for micro, average within-field eligible recall over nonempty eligible fields for macro',
        cohorts=cohorts, references=references,
        primary_report_sha256_before=sha(REPAIR/'report.json'), primary_report_sha256_after=sha(REPAIR/'report.json'),
        no_pixels_models_scoring_fitting_or_reselection=True, no_primary_or_promotion_gate_change=True,
        legacy_field_level_fallback='Original synthetic common_finite_center_ge3 defaults missing usable_center_epochs to3, retaining all3000fields and reproducing common_attributable. This companion applies per-truth eligibility only for discussion.',
        interpretation='Finite true-center counts and three-pixel truth spans are engineering descriptors, not necessary detection ceilings, confirmed motion or real survey sensitivity.',
        native_corroboration='Independent primary accounting finds14 native recovered injected truths outside the>=3finite-center subset.',
        limitations=['Truth eligibility is post-hoc and may select different scene/flux/speed distributions; these conditional rates do not replace all-planned recovery.',
            '600 original zero-truth fields and additional zero-eligible-truth fields retain candidate workload without fabricated recall denominators.',
            'Bootstrap units are whole paired fields, never individual truths or candidate rows.',
            'Cache labels and geometry are reused; no pixels, feature recomputation, model reads or score calls occur.'])
    output=HERE/'diagnostics.json'; atomic(output,json.dumps(result,indent=2,allow_nan=False)+'\n')
    finite=cohorts['finite_true_centers_ge3']; resolved=cohorts['finite_true_centers_ge3_and_covered_span_ge3px']; outside=cohorts['fewer_than3_finite_true_centers_counterexample_cohort']
    article=f'''# Post-hoc per-truth coverage companion\n\nThis descriptive companion corrects the interpretation of the original synthetic cohort named `common_finite_center_ge3`. That legacy field-level cohort falls back to3 when `usable_center_epochs` is absent, so it retains all3,000fields and duplicates common-attributable recovery. Frozen primary counts, gates, source files and model selection remain unchanged.\n\nEligibility here applies to injected truth IDs: `geometric_capabilities.finite_center_epochs >= 3`. Each scorer retains its original stable ranking, all competitors and the original top1/top3 budget. Only then are unique eligible truth identities counted. Ineligible candidates are never removed or reranked.\n\n| Descriptive truth subset | Eligible truths | Fields with eligible truth | C13 K1/K3 | V4 K1/K3 |\n|---|---:|---:|---:|---:|\n| At least3finite true centers | {finite['eligible_truths']:,} | {finite['fields_with_eligible_truth']:,} | {finite['baseline']['top1']:,}/{finite['baseline']['top3']:,} | {finite['candidate']['top1']:,}/{finite['candidate']['top3']:,} |\n| Same, plus covered truth span at least3px | {resolved['eligible_truths']:,} | {resolved['fields_with_eligible_truth']:,} | {resolved['baseline']['top1']:,}/{resolved['baseline']['top3']:,} | {resolved['candidate']['top1']:,}/{resolved['candidate']['top3']:,} |\n\nMicro recall divides unique recovered eligible truths by all eligible truths. Field-macro recall averages each whole field's eligible-truth recovery fraction over fields with nonempty eligible truth sets. Paired percentile intervals use10,000 whole-field resamples with seed20261115; the same field draws retain each scorer's counts and truth denominators. Empty eligible fields have undefined recall rather than fabricated zero denominators and remain in workload totals. The finite-center cohort has{finite['empty_eligible_fields']}such fields, including600original zero-truth fields, and{finite['original_candidate_rows_in_empty_eligible_fields']:,}candidate proposals in those fields. Full original workload remains{finite['original_candidate_rows']:,}proposals.\n\nFinite-center eligibility is not a necessary detection ceiling. The complement contains{outside['eligible_truths']}truths, of which{outside['baseline']['detected']}are detected; V4 retains{outside['candidate']['top1']}/{outside['candidate']['top3']}at K1/K3 under the unchanged competitor pool. Independent native accounting likewise finds14detected truths outside its finite-center subset. The controlled mask-hole counterexample and interpretation erratum are hash-bound in `diagnostics.json`. Covered spans are engineering descriptors rather than confirmed motion or a physical sensitivity limit.\n\nThese post-hoc conditional rates are not promotion evidence, a new selection rule, or a replacement for all-planned recovery. No pixels, models, fitting, feature extraction or scoring were accessed. The machine-readable companion contains every count, macro/micro rate, paired interval and input hash; SHA `{sha(output)}`.\n'''
    atomic(HERE/'DIAGNOSTICS.AI.md',article)
    print(json.dumps(dict(status='PASS',output=str(output),sha256=sha(output),cohorts={k:{'truths':v['eligible_truths'],'baseline':[v['baseline']['top1'],v['baseline']['top3']],'candidate':[v['candidate']['top1'],v['candidate']['top3']]} for k,v in cohorts.items()})))


if __name__ == '__main__':
    main()
