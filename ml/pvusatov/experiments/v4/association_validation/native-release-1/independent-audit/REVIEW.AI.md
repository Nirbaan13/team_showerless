# Independent native numeric audit

The independent native audit passes. All 1,620 fixed injections and 12 controls are present, with no errors or unknown truth counts. The checker independently verifies all 6,349,758 full-pool candidate rows, both policy decisions, spatial labels and matched spans, control attribution, primary counts, strata, and paired bootstrap intervals against the closed combined report. The fixed learned policy improves geometric retrieval in this evaluation. Most of its net improvement is unresolved under the three-pixel matched-span diagnostic, so this result does not establish improved confirmed-motion recovery.

The exact checker prepared before native outcomes were inspected was executed unchanged: SHA-256 `5b6105c10bfbdca1ea5e6ba4218d8cc357e3c9d10be2fc52cb527c20bd9bb8ca`. The original preparation files and `SHA256SUMS` remain unchanged. Frozen R2 is `ae981b56f43c8a14cd6dee9ce61c48853ea7c90b63eca8ddcf586e0a3e3dbbdd`; the released handoff is `6005fd136cdab828cac9c786c18fce2c4977289924f7ff94df3a3ddf92671abb`. C596 model and metadata digests remain bound by the frozen graph. The audit imports no producer accounting functions, opens no raw FITS, and executes no scoring, simulation, feature extraction, or training.

The all-planned cohort contains 1,620 truths, 135 per parent. The common-attributable cohort contains 1,615 truths across the same 12 parents. Five trials are excluded by the predeclared requirement that neither policy's retained control pool spatially match that injection truth. The checker recomputes these matches from retained control XY positions at the actual candidate epochs for both policies. Its retained geometry is independent of the injected field's candidate selection.

| All-planned native outcome | Baseline order | Fixed learned order |
| --- | ---: | ---: |
| Retained candidate rows | 131,473 | 130,345 |
| Truths recovered at K=1 | 304 | 400 |
| Truths recovered at K=3 | 316 | 467 |
| Truths recovered over retained pool | 328 | 511 |
| Resolved truths at K=1 | 232 | 233 |
| Unresolved truths at K=1 | 72 | 167 |
| Resolved truths at K=3 | 241 | 261 |
| Unresolved truths at K=3 | 75 | 206 |
| Macro recall at K=1 | 18.7654% | 24.6914% |
| Macro recall at K=3 | 19.5062% | 28.8272% |

| Cohort and budget | Paired macro difference, percentage points | 95% paired interval |
| --- | ---: | ---: |
| All planned, K=1 | +5.9259 | [1.1111, 11.2346] |
| All planned, K=3 | +9.3210 | [4.2593, 15.0000] |
| Common attributable, K=1 | +5.9663 | [1.1515, 11.3343] |
| Common attributable, K=3 | +9.3661 | [4.3044, 15.0455] |

The intervals exactly reproduce 10,000 paired resamples of whole truth-positive parents using NumPy generator seed `2026111502`; both budgets share each resample's parent indices. There are 12 independent resampling units, rather than 1,620 independent injections. In the common cohort, unequal parent denominators make macro and micro rates slightly different. Both review-budget recovery counts remain 304/400 and 316/467 after the five exclusions.

The net K=1 improvement of 96 consists of one additional resolved truth and 95 additional unresolved truths. The net K=3 improvement of 151 consists of 20 additional resolved truths and 131 additional unresolved truths. Resolved means the maximum pairwise truth displacement across the candidate's actual matched epochs is at least three pixels. It remains descriptive, does not filter primary denominators, and does not prove motion. A spatial match requires at least three candidate epochs and at most 1.5 pixels separation at every one of those epochs. Stable ties and unique truth counting are independently reproduced.

Performance is heterogeneous. K=1 improves in nine parents and declines in three; K=3 improves in eleven and declines in one. At 50 px/hour, K=1 falls from 122 to 115 while K=3 rises from 125 to 128. All K<=3 matches in the 0.01–0.3 px/hour strata have unresolved spans. Parent, speed, and brightness strata are verified exactly and preserved in `audit.json`. The native schema has no cadence-family category; the audit instead records each parent's exact eight epoch times, time digest, spacing extrema, and span. Parent spans range from 9.70 to 45.75 hours, with closely spaced epoch clusters.

The injection full pools contain 6,304,448 hypotheses, including 930 recovered truths and 360 resolved truths before pair pruning. Controls contribute a further 45,310 hypotheses. Control retained workload is 950 baseline rows versus 942 learned rows. Native unmatched candidates and control candidates remain UNKNOWN; these counts do not measure false positives, survey precision, or calibrated utility.

Retained injection rows fall by 1,128, or 0.858%. This is a workload count, not a standalone runtime comparison. The experimental pipeline computes one shared pre-deduplication feature/score pool and both policies, with additional legacy feature/score parity work. Recorded injection prediction CPU totals are 5,132.30 seconds, including 951.38 seconds of parity work. Controls add 35.74 prediction CPU-seconds, including 6.64 parity CPU-seconds. The complete four-worker native job took 1,883.14 elapsed seconds. These timings exclude some preparation/setup costs and do not isolate baseline-policy versus learned-policy latency.

No capped or failed trial is dropped. Both injection and control peak-cap counts are zero. Across every native record, the largest measured workloads are 13,963 hypotheses against the 50,000 limit, 53,957 link checks against 2,000,000, and 82,385 pair operations against 10,000,000. Pair operations and pruning are independently reconstructed; link-search counts are checked against their recorded caps without rerunning detection/link generation. Cached baseline priorities and learned scores are bound and used in the recount without independent model inference.

The released inputs comprise 94 server cutouts and two full MEFs of the same selected physical observations. The root release documents metadata amendments after synthetic unblinding and before native inference. Old-TRAIN transport engineering restored 43 edge samples and changed a background median; it did not establish preparation byte parity, and no parity is claimed here. Both policies receive the same released inputs and fixed requested grids. These qualifications limit external generalization of the fixed comparison and do not authorize production promotion or policy reselection.

The closed combined report is complete for both synthetic and native domains. Its synthetic report matches the prior repaired synthetic report exactly; this execution independently recounts the native domain while preserving the earlier synthetic audit. The audit reads one full and compact field at a time, retains only summaries/digests and one parent's retained control geometry, and completes in 399.52 seconds with 640.36 MiB peak RSS. It uses one math thread and an eight-GiB address-space limit.

The machine-readable result is [audit.json](audit.json). [output-bindings.json](output-bindings.json) binds that result, this review, the unchanged preparation artifacts, the closed input manifests/report/portable evidence, and supplemental control/resource totals. This native execution does not invoke the checker's optional Python I/O guard and makes no original-path-denial or portability-proof claim; the separate portable-proof work has its own evidence. No raw data, original scientific output, model, or frozen source was modified.
