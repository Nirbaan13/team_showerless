# Post-hoc per-truth coverage companion

This descriptive companion applies coverage eligibility to individual injected truth IDs. It leaves the frozen primary report, model, original rankings, competitors, and review budgets unchanged. It is not a promotion or selection input.

The original synthetic cohort named `common_finite_center_ge3` uses a legacy field-level fallback: missing `usable_center_epochs` defaults to three. It therefore retains all 3,000 fields and repeats common-attributable recovery. This companion supplies the per-truth interpretation instead.

For each field, eligible truth IDs satisfy `geometric_capabilities.finite_center_epochs >= 3`. Each scorer first takes its original stable top 1 or top 3 from the complete candidate pool. Only then are distinct eligible truth identities counted. Ineligible competitors are never removed or reranked.

| Descriptive subset | Eligible truths | Fields with eligible truths | C13 K1 / K3 | V4 K1 / K3 |
|---|---:|---:|---:|---:|
| At least three finite true centers | 5,780 | 2,371 | 716 / 1,220 | 1,114 / 1,738 |
| Same, plus covered truth span of at least three pixels | 4,576 | 2,151 | 616 / 1,034 | 953 / 1,487 |

For the finite-center subset, C13 micro recall is 12.388% / 21.107%; V4 is 19.273% / 30.069%. Field-macro recall is 13.658% / 21.886% versus 21.847% / 30.592%. Paired field-macro gains are 8.189 percentage points (95% interval 7.300–9.107) and 8.706 points (7.855–9.599).

Micro recall divides recovered eligible truths by all eligible truths. Field-macro recall averages each field's eligible-truth recovery fraction over fields with nonempty eligible truth sets. The paired percentile intervals resample 10,000 whole fields with seed 20261115, retaining each scorer's counts and denominator together. Micro difference intervals use ratios of summed counts and truths on the same draws. These are post-hoc descriptive intervals, without multiplicity adjustment.

The finite-center subset leaves 629 fields with no eligible truth, including 600 originally zero-truth fields and 29 truth-containing fields. Their recall is undefined, rather than assigned a fabricated denominator; their 12,975 proposals remain workload. The original total workload remains 140,949 proposals. The optional span subset leaves 849 fields without eligible truths. Its covered truth-span condition is distinct from the primary report's *actual matched-epoch* span diagnostic.

The complement contains 213 truths with fewer than three finite centers; none were detected in this synthetic cohort. That observation does not establish a necessary detection ceiling. Independent native accounting finds 14 recovered truths outside the finite-center subset, and the controlled mask-hole counterexample recovers a track despite zero finite true-center pixels. The counterexample and interpretation erratum are hash-bound in the JSON. These coverage and span measures describe engineering geometry; they do not confirm physical motion or measure survey sensitivity.

No pixels, model artifacts, fitting, feature extraction, or scoring were accessed. The frozen report hash is unchanged. Machine-readable counts, rates, intervals, and input references are in [diagnostics.json](diagnostics.json), SHA `960f53f16218861198dcf7ca40fc144e5ce4c6ec52cb379a5597aab0ab58e242`; producer [companion.py](companion.py), SHA `0682286732478f17c13b67684b8af18575b319853945bb38e4c69245fc47ca21`. Three focused tests verify stable ties, duplicate truth identities, retained ineligible competitors, and undefined empty-set recall.
