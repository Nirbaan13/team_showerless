# V4 detector and observable-feature development

Development began 2026-11-15 05:52 UTC; coordinator target 12:50 UTC. Ownership is this detection directory only. Frozen v2/v3 scientific code, models, inputs, and reports remain unchanged. Old final results are published context, never selection/ablation data. New final parents remain quarantined.

## Initial implementation plan

1. Reproduce development fixture failures and quantify proposal multiplicity, morphology, mask support and moving/static evidence. Record D2/D6/Vesta controls as selected development cases; unmatched real detections remain UNKNOWN.
2. Implement and test `v4-physical-features-v1`: existing six features followed by 24 observable physical/support features. Candidate coordinates/epochs are measured detections; no truth, acquisition identity, or labels enter extraction. Separate root-owned generation/scoring assigns evaluation labels only afterward.
3. First compare rich and six-feature rankers on the identical sigma-0.8 proposal pool, same parent groups/injections and K1/K3 budgets. Separately investigate conservative candidate grouping or improved generation, reporting completeness, burden, CPU/RSS, caps and D6 preservation. Any deduplication keeps original proposals available for a paired ablation.
4. Coordinate ordered feature names/version/hash with the ranker before long caches. Keep new native train/validation parents disjoint and reserve the new final set for a later prospective freeze.

## Initial feature semantics

`extract_features(images, times, tracks, *, psf_sigma=.8, outlier=None, bloom=None, residuals=None)` returns an aligned finite `(N,30)` matrix, contract/source hashes, measured candidate identities and per-row missingness diagnostics. Empty candidate sets produce `(0,30)`. Inputs are bounded to 32 frames/512-pixel grids and 50,000 candidates.

The Gaussian-template measurements fit an amplitude plus local constant background using finite pixels in a radius-ceil(3 sigma) patch. Their noise scale is per-epoch image MAD. They are **relative image-unit fit coefficients and approximate SNR/shape proxies**, not absolute fluxes, calibrated probabilities, formal likelihood ratios, or independently calibrated motion significances. Registration/filtering and leave-one-out residuals correlate noise. A Gaussian approximates native ePSFs; PSF mismatch is itself a limitation to measure.

Moving/static coadd evidence compares signed fitted amplitudes at measured candidate positions and the mean measured position, using common valid matched epochs. Static-coordinate measurements are candidate-derived conditional photometry, never externally forced truth positions. Kinematic covariance uses a conservative 0.2-pixel centroid floor and PSF/SNR scaling, with lack-of-fit inflation. Its delta-chi-square and velocity SNR remain explicitly named proxies. No artificially perfect fitted positions replace measured peak features.

Undefined photometry uses finite zero sentinels only alongside explicit coverage/validity features and per-statistic missingness diagnostics. Quality-mask availability is recorded separately from measured flag fraction. Unprovided masks do not establish clean pixels. Original six features retain their original measured-peak semantics.

## Initial tests (TDD)

Hand-checked/controlled images test stable feature ordering, no mutation, empty rows, finite/masked support, quality-mask availability, signed negative photometry, coherent moving-versus-static evidence, shape mismatch, covariance support, and invalid inputs. Actual development fixtures then measure overhead and candidate/known-object outcomes without passing expected coordinates into extraction.

## First measured milestone, 06:07 UTC

The extractor passed eight controlled tests. The initial implementation retained full fit-statistic cubes; coordinator review correctly identified its worst-case memory problem. The revised implementation streams one epoch's 2D maps, samples moving/static candidate coordinates, and discards maps. All 140 saved development feature rows are bit-for-bit unchanged by streaming (maximum absolute delta zero). A separate nonempty 32-epoch/512×512 subprocess measured 566.58 MiB peak RSS and 30.16 seconds, leaving a reserved 150 MiB model allowance below 1 GiB. This is a maximum-image-shape check, not a universal concurrency/latency guarantee.

SOURCE-STABLE feature module SHA256: `8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282`; contract SHA256: `67ad2d61e3f26384860c313f69e916ab6b9ed1c46c6016012af0ae7144d3977b`. Ranker/root generators may now build caches against these hashes. The module is parked while those caches run. `FeatureContext` retains input/residual stacks; extraction streams fit maps per epoch. Measured 1,000-candidate extraction was 0.247–0.283 seconds on the first native 8-epoch/59-pixel-grid fields and 0.325 seconds on comet-D6, including streaming maps but excluding context construction.

Selected development cases reproduce the underlying failure:

| Case | sigma1.2/v2 proposals | sigma0.8/C13 proposals | Known target v2 → C13 rank |
|---|---:|---:|---|
| Comet D2 | 2 | 1 | 1 → 1 |
| Comet D6 | 10 | 36 | 3 → 4 |
| Vesta D3 | 25 | 112 | residual absent; flagged BLOOM recovered |
| Vesta D6 | 7 | 17 | residual absent; flagged BLOOM recovered |
| NEW train01 UNKNOWN control | 35 | 147 | UNKNOWN |
| NEW validation01 UNKNOWN control | 100 | 632 | UNKNOWN |
| NEW train02 UNKNOWN control | 11 | 40 | UNKNOWN |
| NEW train03 UNKNOWN control | 40 | 64 | UNKNOWN |

The D6 known target has residual-template median SNR proxy 52.0, template correlation 0.874, and signed moving-minus-static coadd proxy 12,116. C13 ranks 1–3 have median proxies 9.09, 3.08, and 1.88, and coadd proxies 348, 5.76, and 11.48. This exposes useful measured image evidence missing from the original forest contract. However, the target also has template reduced-chi-square proxy 15.66 and outlier fraction 0.571: blind point-shape or outlier rejection risks rejecting the real selected extended object. Native/synthetic quality-mask availability is a domain indicator; ranker preregistered exclusions for availability alone and all three quality channels, without fabricating synthetic instrument flags.

All tested fields had zero pairs with at least three common epochs and every measured position within one pixel. This conservative overlap diagnostic therefore provides **no evidence that simple spatial deduplication can reduce the measured burden**. It removed no proposals. New native control identities stay UNKNOWN; proposal counts do not establish false-positive precision.

Evidence: `results/initial-development-diagnostics.json`, `results/streaming-development-diagnostics.json`, `results/maximum-shape-memory.json`. The first snapshot is preserved with its original source hash; subsequent performance uses the streamed version.

## Primary-source basis and limits

[Zackay & Ofek, optimal source detection/coaddition](https://arxiv.org/abs/1512.06872) derives PSF-matched per-image statistics and appropriate weighted combinations under its stated image/noise assumptions. This motivates comparing PSF-fit/coadd evidence rather than relying solely on individual smoothed peaks. [Zackay, Ofek & Gal-Yam, proper image subtraction](https://arxiv.org/abs/1601.02655) treats background noise and registration/PSF effects explicitly. The present Gaussian/MAD/local-background feature proxies do not implement that paper's proper subtraction or claim its optimality/calibrated significance. Native ePSFs, changing passbands, masks, interpolation, and self-subtraction remain measurable limitations.

## Pre-link physical gate: preserved negative result

The prospective small grid retained the original sigma-0.8 Gaussian-filter peaks and measured six statistics, then required local Gaussian-plus-constant-background template SNR proxy ≥2, ≥3, or ≥4 **before** linking. It never used target coordinates, a learned score, or a desired output count. Its initial finite-support rule required 80% of a uniform 7×7 patch; all thresholds were declared before querying the pilot. Four controlled gate tests pass, including exact no-gate equivalence and a surviving strong mover.

On the same approved DEVELOPMENT seeds 3801000–3801199 (200 independent fields, 385 truth objects), threshold 2 reduced candidate rows 8,933→8,203 but detected truths 129→128 and C13 K1 49→47; K3 stayed79. On 120 existing native TRAIN injections from four parents, rows fell603→418 but detected32→25, K1 25→19, K3 30→25, and detector CPU sums1.36→2.47 seconds. Allplanned rows remain present; common attribution is reported separately; no runtime errors or reached peak caps occurred. Therefore this gate is **not eligible for promotion**. Counts on four native parents are an exploratory training pilot, not a new independent final evaluation.

The selected real cases alone look more favorable: D2 stays rank1; D6 improves4→2 as proposals36→13 at threshold2. Eight NEW TRAIN UNKNOWN controls total1,573→754 proposals. Vesta BLOOM targets remain unscored and recovered. These selected-case/control reductions do not override the injection losses or establish real precision. Identical native losses at thresholds2/3/4 point to the uniform patch-support rule rather than useful SNR discrimination; any future PSF-information support variant is a separate ablation, not a reinterpretation of this negative result.

Evidence: `results/prelink-psf-gate-pilot.json` and `results/prelink-gate-controls.json`.

## Prospective preset eligibility and new model loader

`results/preset-feature-cache.json` SHA256 `0acd2fff5d0427cc2179641606db9d918c78725af3c6ae127940b08410dabf3d` contains **all** 1/36/112/17 residual rows for D2/D6/VestaD3/D6: original6, full30, candidate IDs, epochs, positions, C13 scores and source/input hashes. All four proposal pools/features/predictions completed before expected coordinates were opened for evaluation. Unmatched tracks stay UNKNOWN=-2. BLOOM tracks have null learned scores and preserve the existing first3/reserve-BLOOM/100-entry policy. These two selected object groups are eligibility-only, never fitting labels; coordinator preregistered D2 rank1 and D6≤4 (prefer≤3), plus retained unscored Vesta evidence, before candidate selection.

NEW `runtime_model.py` is inference-only and leaves the v3 loader untouched. It binds external metadata, actual ONNX structure/metadata, and installed feature version/source/contract. The full float32 X[N,30] graph must Gather the declared ordered subset and return one finite bounded score[N]. ExtraTrees uses actual binary class0/1 weighted-leaf fractions; HGB/RankNet/ListNet use an explicit one-target summed-tree utility followed by sigmoid, with distinct truthful uncalibrated score kinds. Training-objective provenance remains bound by metadata/source evidence; a tree graph alone does not prove its historical fitting procedure.

Guards reject external tensors, custom operators, subgraphs, functions, training graphs, huge tensors, unsupported opsets/topology, cyclic/shared/unreachable trees, invalid feature/class/axis selectors, nonfinite/misaligned scores, and stale feature hashes. Limits:64MiB artifact,250,000 tree nodes,512 trees,50,000 input rows; ORT CPU-only with intra/inter-op threads1,2048-row batches. Runtime imports official ONNX/ORT, NumPy and standard libraries; fitting packages occur only in separate development verification. Official [ONNX serialization](https://onnx.ai/onnx/api/serialization.html), [checker](https://onnx.ai/onnx/api/checker.html), [external-data](https://onnx.ai/onnx/repo-docs/ExternalData.html), and [ORT session options](https://onnxruntime.ai/docs/api/python/api_summary.html) documentation informed the guards (Context7 unavailable; actual installed ONNX1.23.2/ORT1.30.0 tested).

Eleven actual toy-graph policy tests plus eight feature/four gate tests pass. Independent verification loaded four real research artifacts (not selected/released), compared their actual ORT outputs with trusted fitted-estimator outputs on all1,000 NEW synthetic DEVELOPMENT fields/49,286 rows, and reproduced every ordered K1/K3 ID. Maximum absolute score differences are ExtraTrees5.59e-7, HGB3.32e-7, RankNet1.99e-7, ListNet2.30e-7, within2e-6 absolute/relative tolerance. Native validation parity and the eventual selected artifact still require separate checks.

Loader SOURCE-STABLE SHA256 `9a59769f2e3c876188bacf16d28eb04cabe5e39e9679b0f5c6c211a917b944ce`; proof `results/runtime-family-parity.json` SHA256 `414abcca304d97891f605815c73cdc194d1bda4dde58f1d697aba1dc3baf23f5`. No further loader edits planned pending independent review.

### Review correction before any final freeze: bounded Float32 roundoff

Coordinator review requested a real160-tree pure-class leaf edge. The actual ranker exporter produced reference scores[0,1] and raw ONNX scores[0,1.0000015497207642]. The initial strict loader rejected this semantically valid finite mean-leaf result during its warm probe. The initial source and parity proof are preserved under `source_history/runtime-before-roundoff` and `results/runtime-family-parity-pre-roundoff.json`.

Coordinator approved one exact, artifact-bound policy: `score_numerics={"dtype":"float32","unit_interval_roundoff_tolerance":2e-6,"roundoff_action":"clip"}`. It is required in external and embedded metadata. Comparisons use Float32-rounded inclusive bounds; the upper bound is1.0000020265579224, its next representable Float32 value rejects. Only accepted tiny roundoff is clipped to[0,1]; genuine overshoot, nonfinite or misaligned values fail closed. This numerical correction does not calibrate a score or change a fitting objective. A nested Boolean/int metadata impersonation also received canonical-JSON type-preserving binding, without changing valid model behavior.

Real pure-leaf/zero/boundary/nextafter/1e-4 overshoot/missing-policy tests observed RED→GREEN. The complete detection suite now passes33tests plus9subtests. Post-policy real4-family verification again covers1,000NEW synthetic DEV fields/49,286 rows and every full preset pool, with exact orderedK1/K3 reference agreement. No raw-versus-adapter top100 or quota99 membership changes occurred in those specimens; their clip counts are zero. D2 stays1; D6 ranks are2/2/2/1 for ExtraTrees/HGB/RankNet/ListNet. GraphProto bytes/weights are bit-identical between pre/post-policy specimens; only bound numerical metadata changes. These remain research specimens, not a selected release. New native validation parity is still mandatory.

Revised loader SOURCE-STABLE SHA256 `5bce7283ff344ada62f4864f164c8d87266941ad70462d7ecc0d4163f1174e7d`; post-policy proof `results/runtime-family-parity-numerics-v2.json` SHA256 `ffc1dd2c0bf0ab9e9f1425c5ac82d2ee17c2919e7756a5690b04b30b19343c6b`; pure-leaf proof `results/forest-160-pure-leaf-roundoff.json` SHA256 `724739ef90c3e1153e07d4bca234980b752286044eb3a00a1e58b22d14cc8df3`. Feature source843… remains unchanged.

## Next separately typed detection research, declared before querying

Coordinator approved revisiting bounded track-before-detect for new eight-epoch cadences, retaining the original negative v3 evidence and leaving the30-feature/same-pool model study unchanged. New hypotheses will be explicitly typed fitted trajectories, **not independently measured epoch peaks**, with no fabricated six-feature rows or zero-RMS learned scores. Fixed pilot remains3801000–3801199; no new final access.

Motion observability is distinct from spatial injected-source recovery. Under the separate3-pixel engineering span criterion,0.01px/h requires300h(12.5days),0.03 requires100h, and0.1 requires30h. Current native3.3–45.7h spans yield<0.46px at0.01px/h. Validated subpixel astrometry could in principle contain information, but current integer-peak/template-grid methods and proxy covariance do not establish that calibration or an orbit. Fast Vesta recovery does not establish PlanetX readiness.
