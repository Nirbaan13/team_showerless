# Fixed V4 ranker: canonical amended evaluation

The frozen RankNetTreeBoost artifact improves review-budget injection recovery over the frozen C13 scorer on the same measured sigma0.8 proposals and shared preparation. Both all-planned and common-attributable primary gates pass. This evaluates controlled injection ranking, not real-object discovery precision or calibrated probabilities.

| Domain | Independent units / truths | C13 top1 → V4 | C13 top3 → V4 | Macro top1 delta,95% paired CI | Macro top3 delta,95% paired CI |
| --- | --- | --- | --- | --- | --- |
| Native SPHEREx backgrounds |12 parents /3,240 injections|553→685|673→729|+4.074pp [2.315,5.926]|+1.728pp [.802,2.716]|
| Controlled synthetic fields |3,000 fields /5,993 truths|716→1114|1220→1738|+7.986pp [7.104,8.886]|+8.535pp [7.681,9.378]|

Native all-planned and common-attributable contain all 3,240 trials; synthetic cohorts also agree. The bootstrap uses12 physical native parent fields or whole synthetic fields with nonempty truth denominators,10000 paired resamples, seed20261115. Derivatives never become independent observations. Intervals are nominal for the fixed candidate and declared cohort.

The measured proposal pool remains identical between scorers. Uninjected native controls have 824 candidate rows in each system, workload ratio 1.0; their truth labels remain UNKNOWN. There are zero peak-capped trials in both final domains. The original two budgets stay fixed at top1/top3.

Actual matched-epoch truth displacement≥3pixels is a separate descriptive check: native top1 407→511 and top3 498→532; synthetic598→920 and990→1430. The three-pixel criterion does not establish a physical astrometric detection limit. Finite truth-centre coverage is an engineering subset, not a necessary condition or strict detectability ceiling: PSF wings can produce an offset matched peak when the exact centre is masked. The independent audit found 14 recovered native truths outside the≥3 finite-centre subset. See detection/results/FINITE-CENTRE-INTERPRETATION.AI.md and the hash-bound counterexample.

The frozen synthetic common_finite_center_ge3 aggregate uses the legacy field-level fallback and duplicates the common cohort. Use the explicitly post-hoc per-truth companion in secondary-diagnostics for that secondary question; the primary all-planned/common gate and original report stay unchanged.

## Blinded repair and interpretation

The original1896 freeze failed before any complete native result: one exposure in final04 has zero usable requested coverage, and a private Python exception could not be unpickled by the parent. The completed first synthetic artifact remained unopened. Preparation-only diagnostics disclosed coverage, not recovery scores. The globally defined repair retains every original12×8 exposure and timestamp, representing an empty epoch as all-NaN, requiring≥3nonempty physical epochs. Every nonempty frame must retain positive finite injection-reference MAD. No parents, frames, trials, origins, seeds or thresholds were replaced or dropped.

For the other 11 final parents, preparation arrays/masks/times/metadata are bitwise equal to the original. Independent actual TRAIN04 comparisons verify all 270 original injection fluxes/positions/images; a marked TRAIN-only masked derivative verifies the real ePSF path retains the empty epoch. Models, features, proposal policy, gates and confidence procedure remain fixed.

New freeze 1225e2de97c38381818d9ccb3676c1d132701b02b8bc19dc09e0d1785c3e38e4 was committed/pushed before both amended runs. Before canonical unblinding, the checked equality consumer proved all 3,000 synthetic scientific rows identical, including latents, candidates,30features, both score vectors, truth labels and geometry. First and second scientific projection SHA8b884475d7863c52c9c2e0f6cdb2e5678b9168d4e723f19b1507dd0db41e52f5 match. One canonical report was then opened at 09:45 UTC. There was no refit or candidate reselection.

The comparator is C13 **under common amended preparation**. The original deployed end-to-end C13 pipeline errors on the unsupported input; the generic coverage repair's benefit must not be credited to the V4 learner's ranking gain.

## Artifact and engineering evidence

Selected experiment fc3378f486961a8c has 27 selected non-quality columns,19 actually used,120 boosted trees / 1,792 nodes. It trains on 2,004 informative synthetic queries / 68,582 active rows / 109,852 within-field known positive-negative pairs; no native, DEV or FINAL fitting rows. Instrument calibration PSFs remain part of synthetic generation. Runtime uses official bounded ONNX parsing and CPU inference, with no fitting libraries imported.

Graph: c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35; metadata: 472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13. Scores are sigmoid pairwise utility. The original V3 source/weights/final evidence stay immutable.

The optimized residual median preserves exact output bytes on random/masked/extreme/stride cases and all real presets; all 20 family/preset cases preserve 1,710 PNG bytes. In the actual one CPU/one GiB/no-swap VPS cgroup, current maximum 32 × 512 × 512 engineering job completed in 19.89 s with 672.90 MiB whole-cgroup peak. Four real presets used 6.21 s / 110.55 MiB; a native four-exposure engineering case with one missing footprint used 1.27 s / 94.41 MiB and retained all four IDs plus an explicitly black zero-coverage frame. These bounds concern the measured workload (maximum test min SNR 10 / cap 3 / one measured track), not every possible candidate density.

The 44.10 s / 727.15 MiB comparison is the same-weight V4 prototype before the median optimization, not deployed V3. Local timings fluctuate; the recorded paired CPU experiment, rather than a universal latency claim, quantifies that optimization.

Packaged CLI, fresh application CI and deployed HTTP/gRPC/PNG/UI/Swagger/version/latest checks remain distinct release gates. This recovery report alone does not authorize promotion.
