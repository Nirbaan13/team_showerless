# Independent final aggregate review

Reviewer: detector/evaluation agent, after coordinator authorization to inspect completed FINAL outcomes. **PASS for the reported recovery gate and aggregate accounting. Promotion is not authorized by this review.** No fitting, reselection, simulation, FITS parsing, or frozen source/input/model edits were performed.

Reviewed summary: `../../artifacts/v3-final-331c6b1/summary.json`, SHA256 `3c0be474cc46488b159e72ebf56fd7a0862fea614a5d1de77c45925143386b9b`. Trusted freeze: `frozen-331c6b1/final-freeze.json`, SHA256 `2bb68024e0101164f7628074b23e82f07f91480fd5161208e2031c05942dfb75`.

## Independent verification

All 44 compressed output-cache hashes and both run-manifest hashes match the summary. A separate cache recount used stable score ordering, unique matched truth identities, and independent grouping; it did not call the summary's aggregation functions. For both primary and secondary profiles, all-planned, common-attributable, and common-finite-center cohorts match their reported trials, truths, candidate totals, detected/K1/K3 counts, macro/micro recalls, and macro differences. The 10,000-draw paired percentile intervals were independently reproduced using the predeclared seed 20261114 and matched to absolute tolerance 1e-12.

Native primary and secondary each contain all 2,700 derivatives: 270 per independent parent, ten parents. Synthetic profiles each contain all 2,000 independent fields and 3,998 truth objects. There are 1,600 synthetic fields containing truth; the 400 source-free fields remain included in trial/candidate accounting but have no recall denominator. Native derivative uncertainty is clustered by ten parents; synthetic recall intervals resample whole positive fields, not individual objects or candidate rows. Slow and primary profiles share parents and must not be pooled as additional independent observations.

## Primary results

Counts below retain every planned derivative/field; the review budget is K1 or K3 per trial.

| Population | Truths | Detected, baseline → candidate | K1, baseline → candidate | K3, baseline → candidate |
|---|---:|---:|---:|---:|
| Native-background injections | 2,700 | 488 → 575 | 264 → 330 | 367 → 437 |
| Synthetic fields | 3,998 | 1,064 → 1,303 | 398 → 483 | 674 → 831 |

Primary native attribution removes five shared ambiguous trials only in the separately reported common cohort: 2,695 remain; K1/K3 counts are unchanged. Common finite-center coverage retains 2,650 trials. Synthetic common cohorts retain all 2,000 fields/3,998 truths.

The immutable recovery gate uses **common-attributable macro recall differences**, requiring nonnegative differences for both budgets in both populations and at least one positive difference. Independently recomputed values are native K1 +0.0246051712, K3 +0.0260307477; synthetic K1 +0.0192708333, K3 +0.0385416667. They satisfy that exact gate. No confidence-interval or additional post-final criterion was introduced.

For all-planned native primary results, the paired parent intervals for recall differences are K1 [-0.0062963, 0.0585185] and K3 [0.0081481, 0.0466667]. K1 uncertainty includes zero. Native improvement is heterogeneous: final01 K3 changes 48→47; final05 K1/K3 changes 2→0 and 6→2. Ten deliberately selected parent fields do not establish uniform improvement over all astronomical backgrounds.

## Material limits and outstanding gates

- Native primary candidate rows increase 55,412→184,701 (3.333×); synthetic rows increase 66,649→104,549 (1.569×). Equal K1/K3 review budgets do not mean equal detector burden. Native primary detector CPU stage sums increase 445.7→1,336.8 seconds across 2,700 derivatives; model CPU sums increase 5.29→11.80 seconds. These are offline stage sums, not service latency.
- All recorded trial errors and peak-cap flags are zero across all four profile/system combinations. Maximum recorded worker RSS is 289.15 MiB native and 227.76 MiB synthetic. These paired-worker peaks include shared process state and do not isolate model memory or prove deployed service latency/concurrency behavior.
- Unmodified native controls remain UNKNOWN: primary candidate rows are 196 baseline and 673 candidate across ten controls. Their identity labels cannot establish a real false-positive rate or precision. Scores remain uncalibrated ranking values.
- Primary native all-planned K3 recovery remains 437/2,700 (16.19%). Many injected sources remain unrecovered. Slow-profile and truth-span≥3-pixel results are separately reported diagnostics; unresolved spatial recovery does not establish measured astrophysical motion or distant-object completeness.
- The reported runtime and integration gates remain pending coordinator review. This audit verifies the existing scientific recovery gate and its accounting, not promotion, deployment, universal non-regression, real-source discovery, or confidence calibration.

Reviewed summary implementation SHA256 `bd17f13bef0d846bed629fad4c46343549f83a38c8f00933e14ea7cec2f5a697`; geometry-validator SHA256 `17939ab1cc5bcf1bf63df5018455436f4ad7a622f08c14c351d26339c9640cb7`. Before FINAL analysis, 26 summary/geometry guard tests and the declared DEVELOPMENT end-to-end smoke passed; the earlier metadata-only audit confirmed the disjoint 43 train, 77 validation, and 80 final physical observation IDs.
