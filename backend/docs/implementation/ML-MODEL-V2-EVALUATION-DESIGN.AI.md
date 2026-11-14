# V2 model development and final evaluation protocol

This protocol is written before opening the newly reserved real observation field. Its purpose is to improve the learned ranker after v1's real-ePSF generalization failure, while preserving that negative result and keeping a genuinely independent next check.

## Fixed interface and scientific boundaries

The six production track features, their ordering, `random_forest_vote_fraction` score semantics and ONNX runtime interface remain unchanged. Model inference never fits. Public scores remain experimental, uncalibrated ranking values. V1, its SHA-256 and its synthetic/real/ePSF findings remain archived. Any selected v2 receives a new model ID, artifact hash and complete manifest.

M101 was independent when frozen v1 was first evaluated. After its failure informed v2 design, it and all derivatives are **development data for v2**. Previously selected comet/Vesta cutouts are also development/recovery cases. No tuning result on those sources will be presented as an independent v2 test. Unknown real candidates remain unlabeled in every evaluation.

## Physical simulation

Public instrument-only ePSF calibrations supply local responses for all six detectors. A compact bank contains 384 spatially distributed 33x33 stamps sampled five times relative to native pixels, with source product URLs, exact hashes and selected table rows. These calibration products contain instrument knowledge, not held-out observation pixels. Bank SHA-256: `793e05135438c95b8eaeace21948b34fe2eb49cd581be9e81dfff2b493e08d6d`.

Sources are sampled at native pixel centers from pixel-convolved responses, then bilinearly registered with varying orientation and pixel phase. Analytic core/wing profiles supplement the instrument templates. Fields cover three to eight epochs, short irregular arcs, separated groups, and short clusters followed by long gaps, with physical-hour times. Noise, registration residuals, masks, source flux variability and missing source epochs vary.

Integrated amplitudes for moving sources and transient artifacts use the same log-uniform law, 6..600 times the field noise scale. Source profiles and variability have overlapping support across source/artifact identities. These are intended nuisance variables, not label shortcuts. Post-detection positive/negative SNR, profile and epoch distributions are explicitly reported; selection effects can still make the observed distributions differ.

A controlled generator ablation compares per-epoch calibration PSF changes, extended static/blended backgrounds, and their combination. It targets the missing coherent multi-epoch residual patterns diagnosed in v1/v2 pilots. A separate feature ablation retains or suppresses epoch-count/shape splits while preserving the six-input contract. Neither diagnostic changes measured inference features or relabels unknown real tracks.

## Partitions and model selection

Entire independent simulated fields are the grouping unit. Initial training seeds start at 10000 and validation at 300000; the final synthetic test starts at 500000. Early development pilots use separate test seeds starting at 900000 and are explicitly development experiments. No candidate-level split, shared parent image or real-frame injection enters model fitting.

The forest family remains fixed. A limited grid varies leaf size, depth and feature subsampling. Selection uses synthetic validation macro cadence-family unique-object recovery at one review, then at three reviews, then candidate average precision. M101 development diagnostics can reveal a remaining design failure and motivate a new declared development experiment. They are not a final test or a population precision estimate. The manifest records exactly which evidence informed the final design and which parameters were selected.

## Freeze and reserved real-field evaluation

Before opening the new real field, freeze the selected artifact, metadata, training source hashes, calibration hash, training/validation partitions and evaluation code. Tell the coordinator the model ID and SHA-256. Do not change the model using the reserved field's observations, labels or scores. Any future use of a disappointing final field for development requires a new independent field for a subsequent final check.

The reserved observation group is a separate DR1 detector-1 field near ICRS (127.69444, -39.17760). All its frames, crops, injected images and trajectories remain together. There is one independent parent field, regardless of how many injection trials are derived from it.

The real-background evaluation uses the production FITS preparation, actual exposure midpoints, WCS, flags and pixel scale. It runs the unmodified control before source addition. It injects one sparse source per trial using the local native ePSF and the same interpolation/mask treatment as production; no expected coordinates enter detection or scoring.

The predeclared trial matrix is 30 trajectories: six deterministic random positions/directions at each speed 1, 4, 10, 25 and 50 pixels/hour, seed 932711. Five brightnesses per trajectory target projected peak/background pixel-MAD multipliers 3, 6, 12, 24 and 48, giving 150 correlated trials. Each trajectory uses actual physical times, and off-grid or masked points are not moved back into coverage. No photon-noise/variance update or raw detector forward simulation is claimed.

Predeclared reported endpoints are:

- Unique known-injection detection completeness before ranking, with all trials and finite-center coverage subsets stated.
- Known-injection retention at the same **one-review and three-review budgets** for heuristic and frozen model.
- Raw candidate counts, exposure coverage, peak caps and preparation warnings.
- Unmodified control candidate features, scores and heuristic/model ranks, with all control identities explicitly unknown.
- Brightness/speed subsets and per-trial match offsets, without treating derivatives as independent fields.

The key development requirement is to remove v1's systematic zero-score behavior on real ePSF positives and show credible ranking performance against the identical detector plus heuristic. Synthetic gains alone are insufficient. The final result will be reported honestly if model ranking is worse, equal or better. No real precision, false-positive rate, calibrated planet probability or survey-wide generalization claim follows from one field.
