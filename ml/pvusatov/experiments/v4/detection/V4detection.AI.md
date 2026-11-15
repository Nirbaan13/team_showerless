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

### Typed joint-search pilot, fixed before full image queries

The metadata-only protocol `/tmp/spaceapps-v4-detection/joint-pilot-protocol-v1.json` SHA256 `10e86b68b0a17b65dfe00997157b51dcfd19d5a6241bd8b1e674a0b053511134` fixes200 DEVELOPMENT synthetic fields3801000–3801199 and54 derivatives from NEW TRAIN01/TRAIN03. The native subset is direction0 across **all nine speeds**, brightness3/6/12, selected by metadata only; original stored paths/fluxes are replayed without latent draws. Native C13 candidate epochs/positions/original6 must reproduce the cache before typed search. The safe `main-v2` source caches have coordinator-approved SHA256 efff6a12… and008327a0…; earlier quarantined pilot caches are excluded.

Input-only windows comprise the full stack plus maximal contiguous clusters separated by>1.5h, keeping≥3epochs. Fixed integer endpoint grid, min/max speeds0.5/60px/h, endpoint components≤64px, minimum fitted displacement1.5px. The431 windows cover3,194,788 velocity hypotheses and6,372,460,552 anchor/velocity tests; both statistics together plan65,329,388,080 pixel/epoch tests. Largest window303,111,648 is below the600M per-window fail-before-pixels cap. Every window is declared; no target coordinates, source recovery or learned score choose it. Portable C++ uses Float64 accumulation, no velocity cube, no native CPU flags or fast-math. Hypotheses remain explicitly fitted, not measured epoch peaks, with null learned scores and no six-feature conversion. Greedy fitted-path suppression is only proposal suppression, not proven source-identity deduplication.

The first fixed variants are signed temporal-mean-projected sum and a robust positive statistic dropping the largest contribution. Thresholds5/6/7 and100 published hypotheses per method were fixed before the three-field smoke. Null-only fields retain the unconditional maximum statistic, even below proposal threshold. Search completion, exact work, hypothesis count, support, proposal caps and unpublished boundary statistic are separate diagnostics. At most six single-thread workers are used; the main run uses four.

The mean projection uses available finite reference pixels (minimum3), whereas its simple Gaussian response normalization uses the full epoch count. Missing reference samples, unequal per-epoch noise, overlapping selected windows, sources also present outside a short selected window, interpolation correlations, native ePSF differences and temporal covariance prevent calibrated significance or a claim of proper subtraction. The scalar variance-study ratio is not applied as a correction: that study used another estimator and excludes nonlinear/shared residual temporal covariance.

The3-field smoke completed in9.91s without errors: C13 recovered1/2 truths with K3=1; simple sum recovered0 and capped2/3fields; robust recovered1 with K3=0 and no caps. These are explicitly negative early results. Both variants continue unchanged on the full planned subset.

### Separate follow-ups motivated by the development smoke/negative gate

`joint_competitor.py/.cpp` compare coherent positive moving-template evidence against the strongest positive single-epoch point-artifact alternative under the same simplified static projection. For equal independent Gaussian noise and response overlap R, sampled-path covariance is C_ab=delta_ab−R_ab/N; moving response=C·1. Thus Z_move=sum(z)/sqrt(1ᵀC1), while the single-epoch alternative has Z_j=z_j/sqrt(1−1/N). The experimental statistic is sqrt(max(0,max(0,Z_move)^2−max_j(max(0,Z_j)^2))). It tests extra evidence over **one** transient, not all coherent artifacts, and remains uncalibrated under the limits above. Two controlled tests reject an isolated impulse and retain a coherent separated three-epoch signal. This is a DEVELOPMENT follow-up motivated by the observed smoke, not an untouched evaluation. Its own source-bound protocol fixes the same254 fields/windows and thresholds before full follow-up queries.

`information_gate.py` is a separate support ablation of the preserved negative pre-link gate. Under equal independent noise, Gaussian amplitude+constant-background Fisher information on finite pixels is sum((p−mean(p))²). The new rule requires≥80% of the full-patch information,≥6finite pixels and finite center, replacing uniform≥80% pixel coverage. Three controlled RED→GREEN tests establish that missing faint wings can retain information, missing the core fails, and a full patch reproduces the analytic amplitude SNR proxy. The exact old gate thresholds2/3/4 and same200 synthetic/120 native TRAIN derivatives will be reused; no feature843 changes or fitting on these diagnostic outcomes occur.

### Exact counter-type guard before final closure

A read-only review found that `max_peaks:100.0` and `min_epochs:3.0` satisfied the loader's numeric equality check but violate the detector's actual integer counter requirement. Both malformed bound toy artifacts reached ORT before rejection in the RED test. Coordinator authorized requiring exact Python integers for these two metadata fields. Valid model scoring/numerics are unchanged; all16 loader tests and11subtests pass, and all four actual numerics-v2 family specimens load and score. No fitting or feature edits occurred. Previous5b source/tests are preserved under `source_history/runtime-before-counter-guard`; updated loader SOURCE-STABLE SHA256 is `cd7154e2bbba3595b656c4207e9a6afe890a35e1f12ffa4203ab0b7cf6a74598`. `results/runtime-counter-guard-fixtures.json` records actual artifact/metadata/source hashes and acceptance; the earlier full validation score/order proof remains applicable because only malformed counters are newly rejected.

### Replay guard correction preserves the cache producer's representation

The first typed pilot deliberately fails closed if replayed C13 candidates differ. Epochs/positions agreed, but the original guard wrongly compared fresh Float64 statistics to cache values at1e-10: the actual cache producer explicitly serializes these statistics as Float32. Typical differences were one Float32 rounding unit (~6e-8 relative). Therefore native injected typed searches were withheld, and all54 errors remain in each v1 report. The separate v2 native-only replays use `replay_guard.py`: **exact candidate epochs/positions and exact Float32 six-feature arrays**, matching `cache_native._record_measurement`; no spatial/truth tolerance is loosened. Two controlled RED→GREEN tests accept the actual Float32 representation and reject a one-ULP feature change or tiny coordinate change. The v1 protocol/source/results remain preserved; no running source was edited.

## Completed detector pilots: preserve negative transfer evidence

All separately typed joint-search variants failed to improve the small human review budgets on the structured DEVELOPMENT backgrounds. Threshold5 results below use actual published ordering; hypotheses have fitted positions and null learned scores. Candidate caps remain explicit, so raw proposal counts are bounded outputs rather than complete false-candidate counts.

| Fixed cohort | Truth denominator / independent units | C13 K3 | Joint sum K3 | Robust-positive K3 | Transient-competitor K3 |
|---|---|---:|---:|---:|---:|
| Structured synthetic pilot |385 truths / 200 fields |79 |22 |45 |70 |
| Native moving-injection pilot |54 correlated derivatives / 2 TRAIN parents |11 |0 |1 |4 |
| Ideal Gaussian/white-noise stress, eight epochs/ 7 h, nominal amplitude 3 |100 sources / 100 shared-noise parents |2 |98 |91 |93 |

The corrected native replay verified exact candidate epochs/positions and exact producer-Float32 six-feature arrays before any injected typed search. All54 derivatives completed without science errors. The transient competitor found15 spatial matches versus C13's12, but only 9 had actual matched-epoch truth span≥3px (C13:8), and its K1/K3 fell7/ 11→0/ 4. Extra raw recovery therefore does not establish useful review performance. Sum/robust publication caps affected all 54 native derivatives at threshold 5. Native unmatched control tracks remain UNKNOWN; none are negative ground truth.

The PSF-information gate also remains ineligible. On the same 200 synthetic fields, thresholds 2/ 3 modestly changed detected129→130 and K3 79→80, while native120 derivatives from four OLD TRAIN parents changed detected32→31 and K1/K3 25/ 30→24/ 29; rows603→602. Fixing the uniform-patch coverage mistake explained most of the earlier support-driven loss, but did not produce useful native burden reduction or recovery no-regression.

Compact immutable evidence index: `results/detector-pilot-evidence-index.json`, SHA256 `db9b44fb10ac4cc5e76a9886bee7d9739b3eda8dad3d95965e52f5514e4c799a`. It binds five compact summaries, full raw report/protocol/source hashes, original representation-guard failures, corrected attempts, actual fitted-epoch geometry checks, independent parent grouping, null maxima and timing/RSS. Full raw reports remain hashed in `/tmp/spaceapps-v4-detection`.

## Idealized observability stress is diagnostic, excluded from selection

Coordinator reserved100 new engineering parents 3802000–3802099. The exact source-bound protocol was written before draws, SHA256 `efdcc9dd715269dced753923da4424d347feb3f48c99c27ac8039398080d4a8f`. Each parent's same eight white-Gaussian noise images, source angle and midpoint are reused across3/ 8 epochs, short 0.35 h/long 7 h cadence, and known simulation template amplitudes 0/ 2/ 3/ 4/ 6:2,000 correlated derivatives, not 2,000 independent fields. Three-epoch subsets use original epochs 0/ 3/ 7. The whole64×64 grid is searched blindly, with the unchanged declared typed statistics and thresholds 5/ 6/ 7.

At long cadence/eight epochs/amplitude 2, C13/joint-sum/robust/competitor K3 recoveries were0/ 51/ 7/ 14 of100. At amplitude 3 they were2/ 98/ 91/ 93. This verifies conditional subthreshold sensitivity when PSF/noise assumptions match. It does not establish native performance: structured synthetic and real-background pilots above remain negative. Noise-only long/eight-epoch controls generated0/ 257/ 1/ 4 published rows, in0/ 89/ 1/ 4 of100 fields. The proxy thresholds have different null distributions; these values are not equivalent calibrated Gaussian significance levels.

Short-cadence true displacement is1.4px. Joint sum can spatially recover49/ 100 amplitude 6 sources with eight epochs, but **every** such recovery is correctly unresolved under the3px matched-epoch criterion. This is not evidence of confirmed slow motion. Known amplitude/noise units are simulated, not measured physical flux or native covariance calibration. No model/detector promotion is selected from this idealized stress.

All2,000 derivatives completed without errors in1,033.37 s using four single-thread workers; peak worker RSS192.94 MiB. Compact per-field metric matrix/protocol/noise-pair hashes: `results/idealized-observability-v1-compact.json`, SHA256 `7ee29fe2186e17a4a99039bc226b223683ddcd7484d6a48697835704bf144f4b`,431,641 bytes. The matching protocol bytes are preserved under `results/idealized-observability-protocol-v1.json`.

## Exact median-order-statistic performance research

`median_reference.py` is a NEW experimental helper; it does not modify frozen or V4 runtime sources. It sorts finite values once per pixel and derives each removed epoch's odd/even central order statistics. Columns with finite zeros, subnormals or magnitudes>Float64max/ 4 deliberately call the immutable reference, as do non-Float64 arrays. This preserves signed-zero/tie/overflow behavior rather than asserting universal equivalence from ordinary random values.

Initial108 tests passed:100 reserved engineering random/masked/permuted cases3803000–3803099, all finite counts 0..32, ties, infinities, signed zeros, subnormal/extreme permutations, noncontiguous/Fortran layouts, Float32 fallback, and all four actual prepared presets. A further broad IEEE754 bit-pattern test passed; results remain version-bound to the installed NumPy implementation.

On one pinned CPU with32×512×512 Float64 images, complete output-byte SHA256 parity held. Unmasked legacy 18.672 s/ 608.73 MiB versus sorted 0.554 s/ 299.55 MiB;12%masked legacy 15.955 s/ 569.22 MiB versus sorted 0.673 s/ 299.14 MiB. The measured standalone residual-stage speedups are33.68× and 23.72×. These are **not** whole-pipeline speedups or a production change. Exceptional fallback-heavy images can retain legacy cost. Proof `results/median-reference-maximum-v1.json`, SHA256 `91700bf6a597e686484ac6da64feb51a32a9f6387c3e6b5dc6121ff0f7d23807`; prototype source SHA256 `39d65fc5890f99cc3a04a138bf800cd9345056f4c8afa4bc97e693e3f6e14976`.

### Subsequent median integration and exceptional-buffer correction

The coordinator authorized copying the numerically equivalent function into the NEW V4 runtime; original/frozen sources and final-evaluation snapshots remain unchanged. The first copied helper retained fast-path buffers while running its legacy exceptional-column fallback. A maximum all-zero probe measured827.68MiB versus607.37MiB legacy despite exact output-byte parity. Both old sources and that negative resource result are preserved.

An arithmetic-preserving scheduling correction now detects exceptional columns first, runs their reference calculation before allocating sort buffers, and returns directly through legacy when every column is exceptional. Two scheduling tests observed RED→GREEN. Together with broad IEEE754 bit patterns and a whole-empty-epoch case,112 median tests pass; combined median/runtime/root-coverage verification is139 tests. New prototype SHA256 is `64d1b79ff119bdee70ac769f9c05fd9db541bbf83473fbe394da80025079d172`; runtime function body is identical.

Updated maximum output-byte hashes still match reference. Ordinary unmasked22.05s/609.12MiB versus0.666s/300.09MiB;12%masked34.65s/569.38MiB versus1.260s/299.59MiB. The corrected all-zero fallback uses607.71MiB versus607.82MiB reference, and a half-zero stack uses429.70MiB versus607.84MiB,25.40s→12.68s. New proofs: `results/median-reference-maximum-v2.json` SHA256 `c03f915f0e97e2ebc232c27a4c2801ee575ba0b893fef6a0f4ce8e41f4430494`; `results/median-exception-resource-v2.json` SHA256 `8439b6883526d6eb5d906847a1b4246168e211b49d0ed3c988492810c6ee3590`.

The separate versioned-runtime integration records exact full30Float64 feature bits, candidate IDs, score/order/result equality and1,710PNG bytes across20 real development preset/family cases. Its actual nonempty32×512×512 worker used638.01MiB. Local wall-time variation is substantial; observed sequential helper+worker CPU totals94.97→43.31s and wall93.03→38.25s are measurements, not a universal latency claim. The coordinator owns the fresh hard1CPU/1GiB gate and scientific promotion decision.
