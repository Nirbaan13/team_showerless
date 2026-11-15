# DEVELOPMENT association pilot — 2026-11-15

Utility ordering before the existing pair-exclusive pruning recovered more injected sources at the same top-three review budget, but its native gains were mainly spatial recoveries with less than three pixels of displacement across the actual matched epochs. It also required scoring the full hypothesis pool, approximately 4.5 times the measured native baseline CPU work. This is research evidence for an association bottleneck, not a promoted detector, a default change, calibrated confidence, or established slow-motion sensitivity.

## Prospective scope and unchanged comparator

The authoritative protocol was written before the first new simulation, native injection, or FITS reader call: `protocol.json`, SHA256 `afc9a5e27007fdf139728c31d8cfa7db34b8e1e9f8ad5e6a9d552e2380c2f8fe`. A superseded pre-draw draft is retained separately. All prospective source hashes remained unchanged through execution.

The study used 100 new independent synthetic fields, seeds 3806000–3806099, with the existing instrument bank, variable PSF, and extended simulation every third seed. The full denominator is 100 fields and 208 moving truths, including ten noise-only and ten artifact-only fields. Both thresholds use identical images, times, masks, and latent objects per field.

Native derivatives use existing TRAIN01 and TRAIN03 only, fresh seeds 3806201/3806203, eight epochs per parent, and 27 injections per parent: speeds 0.1/1/10 pixels per hour × three seeded directions × brightness 3/12/48. Each speed/direction shares its position and flux scaling across brightness variants. There is no recentering or geometry-based replacement. Native ePSF projection, original registered masks, physical times, supported-finite-centre amplitude rule, and median recentering follow the predeclared generator. These are 54 derivatives of **two independent backgrounds**, not 54 independent native fields. Their deterministic amplitudes are not measured source fluxes or a photon-noise validation.

Both thresholds, SNR 3 and 4, use PSF sigma 0.8, maximum 100 peaks per epoch, minimum three epochs, speed 0.5–60 pixels/hour, match radius 1.4 pixels, and minimum support 0.8. The hypothesis constructor is the unchanged frozen linker's prefix, with the same two-million-link-check and 50,000-hypothesis caps. The production linker was not edited.

Three policies were fixed before the draws:

1. **Legacy:** baseline-score ordering followed by the original pair-exclusive pruning.
2. **Learned pair:** fixed C596 utility ordering followed by that same pair-exclusive rule.
3. **Near duplicate:** baseline ordering; suppress only paths sharing at least three epochs and 80% of the shorter epoch set, with maximum common-position distance at most one pixel. This is a diagnostic grouping heuristic, not proven physical identity.

Every policy sees the same measured hypotheses. Both fixed C13 and C596 score the same truth-free feature matrix. The full 30-column extractor remains unchanged; C596 selects its bound 27 features. Expected positions are used to inject the declared signal and, after all predictions and policies finish, for offline matching at 1.5 pixels. They do not enter hypothesis construction, feature extraction, utility scoring, or pruning. No fitting or reselection occurred.

Policies have a ten-million budget for their declared pair/index operations; the diversity policy also has a one-million exact-comparison cap. These are bounded work counters, not identical CPU instructions. A cap withholds partial results and records an all-planned error. There were no work, hypothesis, or peak-cap hits in this pilot.

## Same-budget results

All-planned raw recovery counts are below. “Detected” counts distinct injected truths retained anywhere in a policy pool; K1/K3 count distinct truths within the ranked review budget. These are residual proposals, not a simulation of the full published BLOOM/classical output membership.

| Cohort / SNR | Policy | Retained rows | Detected | C13 K1 / K3 | C596 K1 / K3 |
|---|---|---:|---:|---:|---:|
| Synthetic / 3 | Legacy | 6,895 | 90 | 28 / 53 | 47 / 78 |
| Synthetic / 3 | Learned pair | 6,610 | 105 | 26 / 55 | 55 / 95 |
| Synthetic / 3 | Near duplicate | 35,551 | 119 | 24 / 47 | 56 / 93 |
| Synthetic / 4 | Legacy | 5,310 | 87 | 28 / 53 | 44 / 76 |
| Synthetic / 4 | Learned pair | 5,076 | 104 | 26 / 58 | 52 / 95 |
| Synthetic / 4 | Near duplicate | 27,743 | 117 | 24 / 48 | 53 / 93 |
| Native / 3 | Legacy | 11,513 | 10 | 1 / 5 | 10 / 10 |
| Native / 3 | Learned pair | 11,860 | 21 | 5 / 7 | 10 / 16 |
| Native / 3 | Near duplicate | 376,793 | 26 | 2 / 2 | 11 / 12 |
| Native / 4 | Legacy | 5,797 | 9 | 3 / 4 | 9 / 9 |
| Native / 4 | Learned pair | 6,014 | 22 | 7 / 10 | 10 / 17 |
| Native / 4 | Near duplicate | 211,139 | 27 | 2 / 2 | 10 / 11 |

At SNR 4, the synthetic learned-pair C596 K3 gain is 19 objects over 208 planned truths, or 0.19 objects per independent field. A descriptive paired whole-field bootstrap with 5,000 resamples gives a percentile 95% interval of +0.10 to +0.29 objects per field. Eighteen fields improve, one worsens, and 81 tie. This interval describes this generator, not real-object precision or native-field generalization.

Native learned-pair K3 has nine improving derivatives, one worsening derivative, and 44 ties at SNR 4. Control attribution changes with the policy: all 54 derivatives are eligible under legacy, but three have preexisting matching control proposals under the learned policy. On the common 51 attributable derivatives, legacy detected/K1/K3 are 9/9/9; learned-pair values are 19/10/17. Thus the raw top-three gain survives the attribution audit. All 54 planned derivatives remain reported. No native confidence interval is offered for two backgrounds.

Keeping the policy pool fixed and comparing C13 with C596 isolates reranking. Keeping the ranker fixed and comparing policies isolates retention plus the effect of which competing hypotheses survive. The benefit is larger under C596 than C13; this is not a universal improvement independent of the ranking model.

## Motion and proposal-availability limits

The diagnostic uses maximum pairwise truth displacement over **actual matched epochs**, not the full injected trajectory. Three pixels is an engineering diagnostic, not a necessary detectability condition or proof of motion.

| SNR 4 cohort | Policy | Retained truths with matched span ≥3 px | C596 K3 with matched span ≥3 px |
|---|---|---:|---:|
| Synthetic | Legacy | 69 | 59 |
| Synthetic | Learned pair | 87 | 78 |
| Synthetic | Near duplicate | 98 | 76 |
| Native | Legacy | 8 | 8 |
| Native | Learned pair | 10 | 9 |
| Native | Near duplicate | 15 | 7 |

The native learned-pair raw K3 gain of eight includes only **one** extra recovery with matched span at least three pixels; the other seven are unresolved spatial recoveries. At SNR 3 the resolved native K3 count remains nine under both legacy and learned ordering. These data do not establish improved distant-object motion sensitivity.

The full unpruned native pool contains 45 spatially matching truths at SNR 4, but only 15 have an available matched hypothesis spanning three pixels. Those are offline proposal-availability diagnostics; they are not reviewed detector recovery or a rigorous physical detectability ceiling. The diversity policy retains all 15 resolved native candidates, yet only seven reach its top three. Retaining many aliases can crowd a fixed review budget.

An illustrative new TRAIN01 injection at speed 1, direction 0, brightness 3 shows matching measured hypotheses sharing at least two detections with legacy-retained UNKNOWN control-like arcs. The matching hypothesis has C596 utility about 0.98, while two overlapping legacy-retained hypotheses have utility about 0.19–0.27. Utility ordering changes which arc survives. The audit also preserves counterexamples where learned ordering loses a legacy recovery. Nonmatching native proposals are UNKNOWN, never asserted false objects.

## Workload and cost

Native UNKNOWN control rows at SNR 3 are 441 legacy, 454 learned, and 14,082 diversity; at SNR 4 they are 211, 220, and 7,711. The fixed top-three review budget remains six reviews across two nonempty control fields. These counts measure workload, not native precision.

The ten synthetic noise-only fields yield four legacy/learned proposals in one field at SNR 3 and none at SNR 4. The ten artifact-only fields remain nonempty under all policies; at SNR 4 legacy/learned/diversity retain 180/167/5,449 rows. Diversity is a clear pool-explosion negative here.

At SNR 4 the 54 native derivatives generate 365,715 hypotheses in total, at most 8,709 per derivative. Actual legacy linking plus retained-pool rich features and both model scores takes 50.51 CPU seconds. Full-pool generation takes 38.53 seconds, full-pool feature extraction and both scores 186.43 seconds, and learned pruning 0.90 seconds: approximately **4.47×** baseline work before shared peak finding. The diagnostic baseline-parity replay and diversity policy are extra study overhead, not part of that ratio. The comparison is a local process-CPU measurement, not a hard VPS production benchmark.

The entire 156-record, two-threshold study completed in 280.90 wall seconds using four single-math-thread workers. Maximum worker RSS was 360.63 MiB. All 312 threshold records exactly match the unchanged baseline's candidate order, 30 feature values, and both score vectors before alternative pruning. There were zero task errors and zero policy/candidate/peak-cap hits. At SNR 4, 27 native derivative pools exceed 100 residual rows under legacy and learned policies; all 54 exceed 100 under diversity. Full publication quotas and BLOOM membership were not rerun.

## Evidence and reproducibility

Five tests cover reconstruction of the unchanged linker, recovery of a competing measured arc, cap rejection without partial output, policy-dependent native control attribution, UNKNOWN labels, and distinct-truth accounting. The full run independently checks baseline parity on every field and threshold.

- `results/run.json`: SHA256 `2b6aa9e711822cbd4be8acf6115c3eb6db699c7e142d54160dc2f86307d47d7e`.
- `results/summary.json`: SHA256 `51241d55796505f8b57845299877b7379e56972914a7d542c3d9e0ab90de7d87`.
- `results/matched-span-audit.json`: SHA256 `ddb538e2dcf893eeb3bfaa7654c5e79599a11c8b064a17603b1b300db749c5fa`.
- `results/retained-features.json.gz`: 11,866,654 bytes, SHA256 `a48aea1b418597e24cf610d79a8b3e9c130ad612a0ac03786c9df011d749eb84`.

The compact derived archive contains every legacy/learned retained row, both rankers' top-three diversity rows, and all offline-matched hypotheses. Other rows remain in SHA-bound full scratch caches listed in the run manifest. The original full-union archive, 124,976,226 bytes, is preserved only at `/tmp/spaceapps-v4-association-pilot/retained-features-full-union-v1.json.gz`, SHA256 `27788156088bb735f27bfb8fa0f2a7cf61d0c1b0bc7f3d194e3dc0eaa095ac04`; its packaging source and audit are retained. No image arrays, model weights, or final data are added to this evidence directory.

Reproduce from repository root with shared science Python and `PYTHONPATH=.:ml/pvusatov/backend/inference`, setting `OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1`. Run `python -m unittest discover -s ml/pvusatov/experiments/v4/association_pilot -p 'test_*.py'`, then invoke the `study`, `analyze`, `package_evidence`, and `span_audit` modules. The study's immutable native packets require a fresh scratch directory for a new execution; the prospective protocol and original fixed model snapshots must remain available. No quarantined association-holdout metadata, pixels, selection rows, scientific FINAL outputs, or FINAL metrics were opened for this work. Root owns any subsequent independent validation or selection.
