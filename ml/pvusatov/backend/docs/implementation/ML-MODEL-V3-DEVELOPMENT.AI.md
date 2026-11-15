# V3 ranking development protocol

V2 remains the deployed frozen baseline. V3 aims to improve both one-review and three-review recovery on independent native parent fields, while retaining the six measured feature contract. No quarantined final pixels, injections, features or scores enter development or selection. This document records development, not final evidence.

## Boundaries and partitions

Production `ml_inference/`, existing `training/`, default models, archives and v2 reports are read-only. Experiment code is under `experiments/v3_ranker/`; scratch caches/logs are in `/tmp/spaceapps-v3-ranker`; candidate artifacts are under ignored `models/experiments/v3-*`.

Synthetic train seeds are 1300000..1302999 (3,000 independent fields), validation seeds 1400000..1400799 (800). Every field uses the v2 physically informed generator, calibration ePSFs, varying per-epoch PSFs and extended backgrounds every third seed. These new draws are separate from v1/v2 train, validation, development and final seeds, and from the detector researcher's 1200000..1299999 range. The initial experiment reuses the existing generator so the effect of native positive training can be isolated with the same latent draws and candidate matrix.

The native data agent predeclares 8 train, 3 validation and 4 quarantined final sky-field groups; its acquisition manifest is authoritative. A parent sky field and every epoch, injection brightness and trajectory stay in one partition. Native train seeds start at 1500000 and validation at 1600000. Per-parent sparse injection trials use native local ePSFs, production WCS/flags/interpolation and actual midpoint hours. Five brightness multipliers [3,6,12,24,48] share deterministic trajectories at [1,4,10,25,50] pixels/hour. These trials are correlated derivatives, never independent fields. Planned trials, finite-center coverage, ambiguous preexisting matches, detector completeness, peak caps and both fixed review budgets remain visible.

M101 and the former v2 final field (127.69444,-39.17760) are explicitly development-only for v3 if used. Neither can be called a fresh final field again. Initial selection does not need them. Unknown native controls remain unlabeled; they are never training negatives or false positives. A trial matching a control track before injection is excluded from attributable recovery.

## Fitting and model selection

Synthetic candidate matches provide known positive and negative labels. Native fitting uses only attributable injected positive matches; every unmatched native candidate is unknown and excluded. Native positive mass is a controlled ablation relative to synthetic positive mass, equalized across train parent fields. Negative synthetic epoch strata are weighted from train rows only, and total known class weight is balanced. No preprocessing is fitted on validation.

A bounded RF/ExtraTrees grid uses at most 192 trees, limited depth/leaves, one math thread per worker and at most ten CPU workers total. Candidate size must be <=32 MiB; CPU inference must fit the existing VPS budget. Resource use serves larger independent simulations and reused feature matrices, not merely larger forests. The shared interpreter is `/home/usatovpavel/edu/UtilsAI/.venv/bin/python`.

Selection uses validation macro-parent known-injection recovery at one review, then three reviews, with synthetic validation macro-cadence performance as the secondary safeguard. All grid outcomes, including both budgets, will be published. Native candidate AP/precision/false-positive metrics are not defined because unknown rows have no negative labels. No validation refit. The final artifact, training inputs/source hashes, manifests, evaluation code and parity probes must be frozen before root opens final fields. Root owns final evaluation and promotion.

## Current evidence

The first synthetic train cache contains 102,677 candidate rows and 1,668 positive rows from 3,000 independent fields; generation took approximately 62 seconds with ten workers. Protocol regression tests verify exclusion of unknown native rows and exclusion of preexisting control matches from attributable recovery. No v3 model is yet selected or final-tested.

## Expanded development and acquisition-domain audit

The coordinator subsequently predeclared six additional validation parents and six additional final parents. The current authoritative cohort is 8 train, 11 validation DEVELOPMENT and 10 quarantined final independent sky fields. No final reader has opened final pixels. The sole final synthetic reservation is **2000000..2001999**, 2,000 fields, unopened until full freeze. Earlier coordinator reservations at 1700000 and 1800000 were withdrawn before generation because these numbers were already used by independent-generator native stationary and slow-motion development draws; no final synthetic generation or evaluation occurred at either withdrawn range.

The six new validation fields have eight physical epochs and 21–47 hour spans, selected from metadata with three Galactic-plane and three high-latitude centers. Their predeclared matrix is six directions at each speed `[0.01,0.03,0.1,0.3,1,4,10,25,50]` pixels/hour and five brightnesses, or 270 correlated derivatives per parent. RNG seeds are 1610006..1610011. Coordinates are never moved into coverage. Both detector sigmas 1.2 and 0.8 are compared at the identical primary minimum speed 0.5, with a separately cached identical secondary minimum speed 0.005. Flux brightness normalization uses the median projected peak among finite covered centers, with documented positive-support/field-center fallback when all centers are outside; this avoids erasing a source visible in early epochs solely because it leaves later coverage. Every planned trial and finite-center geometry remains reported. Matched-epoch displacement is preserved for the prospective descriptive >=3-pixel resolved-motion diagnostic; unresolved coincidences remain in all-planned counts.

A known-positive-only acquisition-domain classifier, fitted on synthetic/native train positives and evaluated on separate synthetic/native validation positives, attains domain AUC **0.8734** using all features, **0.8306** without epoch count and **0.7103** using epoch count alone. This is a real shortcut risk for native-positive-only augmentation. It does not prove the motion forest uses that shortcut; all zero-native-mass motion ablations are retained. Audit input rows are all known positive, and unknown controls are never labeled. Raw results are `/tmp/spaceapps-v3-ranker/domain-audit-sigma12.json`.

A separate native TRAIN-only stationary-source audit injects fixed sky sources through actual native WCS/ePSFs, sharing moving-source brightness support and constant-flux assumptions. No imposed velocity or registration jitter makes an artificial linear negative. Strict matching and pre-injection control exclusion identify attributable apparent moving residuals as known stationary-source artifacts; every other real track stays unknown. Eight train fields ×300 correlated derivatives yield **0** known artifact rows at sigma1.2 and **92** at sigma0.8 across seven parents. The sigma0.8 branch therefore compares native positive-only versus equal native-positive/known-artifact-negative weight mass while preserving total class balance. Its 84 predeclared configurations comprise 12 forest profiles ×(one zero-native-mass control plus three nonzero masses ×two artifact-mass settings). No new raw observation enters model fitting unless already in TRAIN. The native group without attributable artifacts remains a positive-only subgroup and is a residual limitation.

## Complete first-stage sigma1.2 grid: five-parent validation DEVELOPMENT

All 48 first-stage configurations fitted the same frozen 3,000 synthetic fields and eight native train parents. This stage reports five validation parents (750 correlated injection derivatives), **not** final evidence or the prospective eleven-parent winner. Additional validation scoring reuses unchanged cached estimators without refitting. No final winner is selected before all eleven validation parents are available.

| Comparator | Native K1 | Native K3 | Synthetic K1 | Synthetic K3 |
| --- | ---: | ---: | ---: | ---: |
| Heuristic | 108 | 143 | 118 | 205 |
| Frozen v2 | 139 | 156 | 177 | 299 |

| Family | Leaf | Depth | Feature subsampling | Native positive mass | Native K1 | Native K3 | Synthetic K1 | Synthetic K3 |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| extra | 4 | 12 | 1.0 | 0 | 144 | 160 | 181 | 305 |
| extra | 4 | 12 | 1.0 | 0.5 | 142 | 166 | 175 | 292 |
| extra | 4 | 12 | 1.0 | 2 | 130 | 166 | 154 | 279 |
| extra | 4 | 12 | 1.0 | 8 | 131 | 162 | 139 | 253 |
| extra | 4 | 12 | sqrt | 0 | 150 | 168 | 185 | 305 |
| extra | 4 | 12 | sqrt | 0.5 | 158 | 167 | 173 | 300 |
| extra | 4 | 12 | sqrt | 2 | 147 | 166 | 155 | 279 |
| extra | 4 | 12 | sqrt | 8 | 141 | 163 | 133 | 240 |
| extra | 12 | 16 | 1.0 | 0 | 147 | 161 | 177 | 305 |
| extra | 12 | 16 | 1.0 | 0.5 | 142 | 165 | 158 | 290 |
| extra | 12 | 16 | 1.0 | 2 | 138 | 166 | 146 | 270 |
| extra | 12 | 16 | 1.0 | 8 | 134 | 166 | 142 | 256 |
| extra | 12 | 16 | sqrt | 0 | 150 | 164 | 182 | 307 |
| extra | 12 | 16 | sqrt | 0.5 | 152 | 166 | 168 | 297 |
| extra | 12 | 16 | sqrt | 2 | 145 | 166 | 148 | 270 |
| extra | 12 | 16 | sqrt | 8 | 143 | 163 | 132 | 238 |
| extra | 32 | None | 1.0 | 0 | 139 | 161 | 165 | 293 |
| extra | 32 | None | 1.0 | 0.5 | 141 | 166 | 153 | 270 |
| extra | 32 | None | 1.0 | 2 | 133 | 165 | 141 | 257 |
| extra | 32 | None | 1.0 | 8 | 133 | 164 | 135 | 245 |
| extra | 32 | None | sqrt | 0 | 137 | 161 | 169 | 290 |
| extra | 32 | None | sqrt | 0.5 | 146 | 165 | 154 | 280 |
| extra | 32 | None | sqrt | 2 | 139 | 164 | 137 | 253 |
| extra | 32 | None | sqrt | 8 | 140 | 164 | 127 | 230 |
| rf | 4 | 12 | 1.0 | 0 | 147 | 153 | 186 | 292 |
| rf | 4 | 12 | 1.0 | 0.5 | 120 | 167 | 172 | 297 |
| rf | 4 | 12 | 1.0 | 2 | 120 | 162 | 167 | 295 |
| rf | 4 | 12 | 1.0 | 8 | 129 | 163 | 156 | 274 |
| rf | 4 | 12 | sqrt | 0 | 147 | 158 | 180 | 304 |
| rf | 4 | 12 | sqrt | 0.5 | 137 | 166 | 174 | 304 |
| rf | 4 | 12 | sqrt | 2 | 131 | 168 | 173 | 299 |
| rf | 4 | 12 | sqrt | 8 | 129 | 168 | 151 | 286 |
| rf | 12 | 16 | 1.0 | 0 | 142 | 155 | 182 | 290 |
| rf | 12 | 16 | 1.0 | 0.5 | 134 | 165 | 180 | 298 |
| rf | 12 | 16 | 1.0 | 2 | 119 | 159 | 165 | 296 |
| rf | 12 | 16 | 1.0 | 8 | 125 | 160 | 150 | 265 |
| rf | 12 | 16 | sqrt | 0 | 144 | 156 | 179 | 302 |
| rf | 12 | 16 | sqrt | 0.5 | 141 | 166 | 174 | 298 |
| rf | 12 | 16 | sqrt | 2 | 138 | 166 | 169 | 297 |
| rf | 12 | 16 | sqrt | 8 | 132 | 168 | 162 | 289 |
| rf | 32 | None | 1.0 | 0 | 143 | 157 | 173 | 282 |
| rf | 32 | None | 1.0 | 0.5 | 137 | 166 | 166 | 280 |
| rf | 32 | None | 1.0 | 2 | 122 | 166 | 157 | 262 |
| rf | 32 | None | 1.0 | 8 | 125 | 165 | 128 | 237 |
| rf | 32 | None | sqrt | 0 | 138 | 159 | 170 | 290 |
| rf | 32 | None | sqrt | 0.5 | 143 | 166 | 164 | 290 |
| rf | 32 | None | sqrt | 2 | 130 | 166 | 159 | 271 |
| rf | 32 | None | sqrt | 8 | 137 | 166 | 138 | 255 |

All per-parent, coverage-cohort, average-precision and full configuration outcomes remain in `models/experiments/v3-main-five-validation/validation-evaluation.json`; cached research estimators stay under `/tmp/spaceapps-v3-ranker/forest-cache-main` and will never ship in runtime. The current five-parent leading eligible candidate is ExtraTrees (160 trees, minimum leaf4, depth12, sqrt feature subsampling, native-positive mass0.5), retaining **158/167** at K1/K3 versus v2 **139/156** and heuristic **108/143**. These counts are selection evidence, not held-out estimates. Native detection is 174/750 before ranking. The unknown Cygnus control tracks remain unlabeled even when known-injection retention changes.

## Prospective development amendment before eleven-parent scoring

The coordinator approved strengthening synthetic validation eligibility to **>= both frozen v2 and the heuristic at both macro-cadence K1 and K3**, as well as protecting both native macro-parent budgets. This is an explicit development amendment motivated by the observed five-parent ablation, not an untouched original preregistration. It was recorded before expanded eleven-parent scoring and before any final access. The matched ExtraTrees ablation shows native-mass0 already achieves native150/168 and synthetic185/305, while mass0.5 achieves native158/167 and synthetic173/300 versus frozen v2 synthetic177/299; positive-only augmentation thus trades a synthetic first-review regression for some native gain. Final selection will maximize native K1, then K3 only among models passing all four validation safeguards. The final no-regression gate remains unchanged. A regression test first failed against the weaker gate and now protects this rule.

## Relocated selection integrity and complete-system comparator

All own ML code and documents now live under `ml/pvusatov/` with their prior internal hierarchy preserved. Run historical relative paths from that namespace root. The exact fifteen pre-audit experiment sources were snapshotted at `/tmp/spaceapps-v3-ranker/pre-selection-audit-source-snapshot/` before fixes; existing cache fitting manifests keep original byte hashes and historical paths. Source relocation is resolved by matching preserved suffixes and exact hashes, never by rewriting history.

`select_system.py` is the primary system-selection tool: it verifies every recorded fitting/cache byte hash and fitting source hash before loading candidate models, verifies all estimator hashes, requires all 48 sigma1.2 plus84 sigma0.8 primary outcomes, and requires all eleven independent validation parents. It compares the deployed sigma1.2/frozen-v2 system against each candidate profile on exact paired trials using the coordinator's `experiments/v3_evaluation/paired.py`. Same-detector frozen-v2 ablations remain separately labeled diagnostics. Raw all-planned spatial recovery, common-attributable recovery, finite-center coverage, both review budgets and independent-parent bootstrap remain visible. Legacy narrow caches that omitted origin/velocity metadata can recover these fields only from an exact byte-verified original source cache; candidate features, matches and attribution bits never change.

Before expanded model scoring, the coordinator further approved protecting **both the deployed heuristic and candidate-profile heuristic** at native macro-parent and synthetic macro-cadence K1/K3, alongside frozen-v2 protection. This is a stronger DEVELOPMENT safeguard, not a revised final gate. Primary selection uses only minimum speed0.5 caches. Equal minimum speed0.005 is a separate secondary diagnostic. Historical `select_cached.py` can only run explicit same-detector evaluation and is blocked from freezing release candidates. New regression tests first failed, then passed for cache tampering, verified metadata restoration, common-attribution accounting and the legacy freeze block. No final data has been opened or winner frozen.

## Shared cross-profile selection cohort correction before scoring

An independent pre-score review identified that profile-specific attribution exclusions could make absolute selection keys incomparable: the sigma1.2 profile had 2,370 eligible planned derivatives, while the sigma0.8 union cohort had 2,360. No expanded model scores had been computed. The coordinator authorized one shared sigma1.2∩sigma0.8 selection mask for **all132 alternatives**, including every heuristic/v2 safeguard. It excludes five trials in validation03 and five in validation06 from the selection-only cohort. All2,370 raw planned trials and each individual system pair's own attributable/coverage reports remain separately published. Features, labels, scores and stored attribution flags never change. Exact planned, per-profile eligible and shared denominators are recorded per independent parent. A regression test first failed without the shared mask, then passed after both candidate profiles used the same immutable trial-key set. This is a correction before first expanded scoring, not final-informed tuning.

## Single selected estimator and numerical export amendment before final

All132 alternatives completed on the same2,360-trial shared cohort across11 validation parents. There were49 eligible alternatives. The fixed rule selects **sigma0.8 +ExtraTreesClassifier**,160 trees, minimum leaf12, maximum depth16, sqrt feature subsampling, native-positive mass2 and attributable stationary-artifact-negative mass2 (cachedID `4650f3f2a39c496d`). Shared K1/K3 retention is410/438; full2,370 raw planned retention is412/440 versus frozen v2 258/320. Synthetic800-field validation retention is209/334 versus frozen v2 177/299. These are DEVELOPMENT selection results, not final estimates. All132 outcomes remain in the full system-validation report. No estimator is refitted for export.

The first standard float32 ONNX export was5,552,419bytes, SHA`50df7d8a7ac92aa3cdd6b88cb572e4a2a0a1b3b7252f0b966c40bc9fe2ec6fc2`. Its original strict full-order guard failed on one native trial at ranks99/100, whose sklearn score gap was3.72e-8. It changed no ordered K1/K3 selection and no top100 membership. The original export-failure JSON, artifact/hash and producer source are retained unchanged. Before any final access, root explicitly amended the DEVELOPMENT export guard to NumPy allclose with **rtol=2e-6 and atol=2e-6**, identical ordered top1/top3 candidate IDs and known retention in every field, and identical top100 membership. Other full-order changes must remain recorded with identities/ranks/score gaps and may never be called exact parity. Both native and synthetic diagnostics are collected even if one fails. No exotic graph, score quantization, model refit or second estimator is used.

The unchanged second export passed this protected policy on native2,370trials/161,892candidate rows (max absolute score error6.66e-7,one disclosed low-order swap) and synthetic800fields/38,717rows (max8.64e-7,no order changes). It remains historical development evidence because its broad source inventory captured an in-progress unrelated preset diagnostic scaffold; root will bind coherent final sources only after CORE-READY. Runtime memory measurement was also corrected prospectively: fork/exec can inherit parent rusage high-water, so the producer records fresh Linux process VmHWM as runtime peak and retains inherited rusage separately. A clean standalone probe measured128.9MiB; the model scores1,000rows in roughly12ms median on this laptop. The next coherent artifact will embed full detector_profile, accurate model_family and algorithm_version_proposal in ONNX custom properties, matching external metadata and binding profile to artifact bytes. Final data remains closed.

## Historical selection source versus guarded export/runtime source

Before adding optional trusted-freeze/preparation header checks to the root paired evaluator, root preserved all19 exact sources used for132-model selection under `ml/pvusatov/artifacts/v3-selection-source/`, with unchanged original invocation JSON and a byte-verified snapshot manifest. Export now accepts explicit `--selection-source-root`: it verifies every original hash in that immutable snapshot, verifies archived invocation bytes against the original invocation digest, and records this historical binding separately from current guarded export/runtime source hashes. Original hashes and model-selection results are never rewritten or rerun against final data. Fitting source/input hashes remain checked against their unchanged current3/4 source files. The final coherent graph embeds the full detector profile, model family and algorithm-version proposal, binding default sigma0.8 to artifact bytes; legacy v2 is archived self-contained under `releases/v2/` and retains its old behavior.

## Reviewed profile-bound development candidate and compatibility limitations

The coherent selected artifact is `models/experiments/v3-selected-candidate-profile-bound/ranker.onnx`, **5,552,706bytes**, SHA-256 `c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204`. Model ID is `spherex-track-extra-v3`; embedded/external family is ExtraTreesClassifier, full primary detector profile is sigma0.8/minimumspeed0.5 with the other frozen settings unchanged, and the proposed algorithm version is `motion-extra-v3-sigma08`. The weighted graph bytes are identical to the original selected export (graph SHA `672607f36d5258bfe8a9d3d0f935a4a8639466c0063fcada2a24ec9256969f07`); only profile/family/version binding properties changed. No refit or second candidate occurred. Metadata SHA is `983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04`; development-freeze SHA is `9f94d2ca715184b4dbc7e72147bfa9b505233b42277706154df65bba59156bff`. Root's separately trusted external freeze remains required for any final access.

Both complete numerical diagnostics pass the protected policy and actual validation eligibility: native2,370correlated trials (11independent parents)/161,892rows have maximum absolute error6.66e-7 and one disclosed ranks99/100 swap, while synthetic800fields/38,717rows have maximum8.64e-7 and no order changes. There are no ordered top1/top3 or top100-membership changes in either set. Fresh one-thread runtime probe on1,000rows measured17.8ms median,18.8ms p95 and **128.5MiB Linux VmHWM**; inherited rusage821MiB is separately recorded and is not called model-only memory. The active production and all experiment tests subsequently passed **161 tests in11.91s**. Current prospective final runner files are bound by root's external freeze; broad inventories in earlier development exports remain historical and are never silently rewritten.

A separate four-preset DEVELOPMENT diagnostic on the exact same chosen artifact found important limitations. CometD2 stays modelrank1; cometD6 moves from rank3 to rank4 as residual candidate count grows10→36, losing K3 recovery despite heuristicrank1 in both profiles. VestaD3 andD6 remain BLOOM-only, with null ML scores. VestaD3 has112narrow-filter residuals plus its known BLOOM at rank113, so the100-output cap evicts it (baseline25residuals plus BLOOMrank26 retains it); two candidate-profile epochs hit the peak cap. VestaD6 BLOOM remains retained but shifts rank8→18. These are compatibility regressions, not false-positive labels for unknown controls, not new independent survey objects and not grounds for picking another estimator after final. Native D1–3 selection cannot establish D4–6 transfer. Detailed report is `experiments/v3_evaluation/results/preset-compatibility.json`, SHA `6f98ce350160be88aa783aabf334a08f60020d1836d7e44c0dc25ffb0b9d48dd`. Root must consider these delivery limitations separately from the unchanged prospective final recovery gate. Final data is still unopened at this report update.
