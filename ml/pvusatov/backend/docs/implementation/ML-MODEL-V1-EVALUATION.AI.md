# Frozen motion-track model and evaluation

The v1 synthetic-trained Random Forest improves ranking in simulation but **fails to generalize to the independent native-ePSF injection check**: it retains zero of 67 detected injected tracks in a one-review budget, versus 65 for the heuristic. It must not be presented as an improvement to real ranking. Its frozen artifact and evaluations are preserved under `models/archive/v1/`. Scores are not calibrated planet probabilities, detection significance, object classes or discovery claims.

## Artifact and runtime

Model ID `spherex-track-rf-v1`; artifact `backend/inference/models/archive/v1/ranker.onnx`, 2,168,053 bytes. SHA-256:

```text
030c1edf972b76b3cb8fadcb4adadcc386a36eab9f2cdbcb65527c277c581ab9
```

Training-manifest SHA-256: `d0810c183507af13f12ff91d60aaabca66be0955c3a625dcfb9bb9dbeb9e83b0`. ONNX IR 8, standard operator set 17 and `ai.onnx.ml` operator set 1; dense class output without ZipMap. Runtime requires only `ranker.onnx` and `metadata.json`. No Python estimator pickle is shipped.

`ml_inference.model.load_ranker(model_dir=None)` validates SHA-256, schema, feature order, classes `[0, 1]`, embedded metadata, tensor shapes/types and graph label/probability consistency. CPU inference uses one intra-operation thread, one inter-operation thread, sequential execution and no spinning. It imports no sklearn or training module, performs no fitting, rejects non-finite/wrong-shaped features, and returns an empty vector for `(0, 6)` input.

Exact feature order: `epoch_count`, `fit_rms_px`, `median_snr`, `min_snr`, `snr_coefficient_of_variation`, `median_peak_ratio`. These come directly from production `Candidate.features()`. The positive class means a simulated track matching an injected trajectory. The required interface name `score_kind=random_forest_vote_fraction` numerically means the mean class-1 weighted leaf fraction across 150 trees (`predict_proba`). Mixed leaves and balanced class weighting mean this is neither a fraction of hard binary tree decisions nor a calibrated posterior.

## Provenance and reproduction

Training adapts the team's `ml/benchmark.py` at base revision `ca63aa4145f5a539b157f8bd25c237c8cca56148` and Ivan's `science/motion/ranker.py` at `2b6dc435b0f73a6f255e50ca795900acfd69cd33`. `models/archive/v1/training-manifest.json` records that base revision, versions, every seed, parameters and SHA-256 hashes of the actual new training/detector source used. Those hashes distinguish the trained implementation from its base revision. No real images, real labels, target names or expected coordinates enter fitting or feature construction.

Versions: Python 3.14.4, NumPy 2.5.3, SciPy 1.18.1, sklearn 1.9.1, skl2onnx 1.20.0, ONNX 1.23.2 and ONNX Runtime 1.30.0. Inference targets Python >=3.12; integration CI separately checks that environment. Cross-version bit-identical retraining is not promised.

From repository root, using the separate hashed training requirements:

```bash
PYTHONPATH=backend/inference python -m training.train --train-fields 300 --validation-fields 100 --test-fields 200 --output-dir /tmp/spherex-v1-reproduction
PYTHONPATH=backend/inference python -m training.statistics --model-dir backend/inference/models/archive/v1
PYTHONPATH=backend/inference python -m training.evaluate_real --model-dir backend/inference/models/archive/v1 --output /tmp/spherex-v1-selected-real.json
(cd backend/inference && python -m pytest -q)
```

The first command deliberately fits and replaces the model offline. It regenerates `field-candidates.json`, a 54 MB audit cache ignored by Git. Seeds and source make that cache reproducible. The other evaluation commands never fit. Production inference never invokes training. Training, export, synthetic evaluation and audit output took approximately 229 seconds on the development machine.

## Independent field groups and model selection

Partitions contain complete independent 96x96 simulated fields: 300 training seeds `0..299`, 100 validation seeds `100000..100099`, 200 test seeds `200000..200199`. All epochs and candidate rows stay with their parent field. There is no candidate-level random split, shared parent image or real-background reuse. Test feature generation happens before selection for computational convenience, but test rows/labels/metrics never enter selection.

Each field has six physical-hour times `[0, 1, 2.2, 3.1, 4.4, 5.3]`. Every tenth seed is noise only; the next is a zero-injection artifact field. Other fields contain one to three injected moving sources alongside variable stars, cosmic-ray-like pixels, transient blobs and a masked strip. Two thirds additionally vary noise scale (0.7..1.8), per-epoch PSF sigma (0.8..1.8 px), injected flux (up to 45% variation), one dropped source epoch in some cases, and registration residuals (Gaussian sigma 0.15 px per coordinate). These are synthetic stress conditions, not an empirically measured SPHEREx population. Simulated motion covers approximately 0.7..7 px/hour; the wider production speed range has limited training support.

Detector settings match production defaults: leave-one-out references; SNR 4; filter sigma 1.2 px; maximum 100 peaks per epoch; speed 0.5..60 px/hour; radius 1.4 px; minimum three epochs; filter support 0.8. A positive requires every linked point within 1.5 px of the injected path. Confused/partial/inaccurate tracks failing this definition are unmatched. Expected positions assign offline labels only after detection.

Training contains 122,994 candidate rows, only 182 positive. Three choices use 150 trees, balanced classes, seed 42 and one job: `(minimum leaf size, depth)` of `(2, 10)`, `(4, 12)`, `(8, unlimited)`. Validation selection prioritizes unique recoveries in three reviews per field, then fewer false selected tracks, then candidate average precision. Recoveries were 27, 26 and 35. The third model was frozen without refitting validation or consulting test metrics.

## Synthetic results at the same review budget

Both rankers receive identical tracks and at most three reviews per field. Recovery counts unique injected objects; average precision labels candidate rows, which can include multiple matches to one object.

| Independent test, 200 fields | Heuristic | Frozen forest |
| --- | ---: | ---: |
| Injected objects | 306 | 306 |
| Recovered before ranking | 101 (33.01%) | 101 (33.01%) |
| Recovered in top three per field | 0 (0%) | 58 (18.95%) |
| False selected candidate tracks | 540 | 482 |
| False selected tracks per field | 2.70 | 2.41 |
| Candidate average precision | 0.002380 | 0.384621 |

The model retains 58/101 (57.43%) detectable objects at the review budget. Bright variable-source residuals overwhelm the brightness-weighted heuristic in this artifact-dense construction; synthetic gains do not establish real-survey gains.

A paired bootstrap of whole test fields (10,000 draws, seed 274912) gives a 95% percentile interval of +14.97..+23.18 percentage points for forest-minus-heuristic top-three recall, and -0.360..-0.225 false selected tracks per field. These intervals address sampling variation within this generator, not its correspondence to real observations.

Validation had 159 injections and 60 detector recoveries; heuristic top-three recovered 1 and forest 35, with average precisions 0.003592 and 0.333683. Exact metrics/subsets are in `models/archive/v1/evaluation.json`; bootstrap output is `evaluation-statistics.json`.

| Zero-injection test control | Fields | Candidates | Heuristic false top-three | Forest false top-three |
| --- | ---: | ---: | ---: | ---: |
| Independent Gaussian noise | 20 | 0 | 0 | 0 |
| Variable stars plus pixels/blobs/masks | 20 | 9,048 | 60 | 60 |

Ranking cannot remove all false candidates under an unconditional top-three budget. No accepted/rejected score threshold, false-discovery control or calibrated cutoff is claimed.

The selected sklearn estimator and ONNX export agree on 1,350 deterministic training/held-out/random probe rows, maximum absolute error `1.3306278534575e-7` under `2e-6` absolute/relative tolerance. `parity-reference.json` preserves sklearn predictions without a Python pickle. Separate tests train a different small forest and compare its export on 1,250 rows.

## Selected real-object recovery

Four cutouts represent **two objects**, with correlated detector views. They are selected development/recovery cases, never training/selection/calibration data or independent survey gold fields. Production preparation/detection/scoring run before expected coordinates are loaded. Unmatched real candidates remain unlabeled; no real precision or false-candidate rate is computed.

| Cutout | Residual candidates | Known-target heuristic rank | Frozen forest rank | Maximum recovery offset |
| --- | ---: | ---: | ---: | ---: |
| 3I/ATLAS detector 6 | 10 | 1 | 1 | 0.539 px |
| 3I/ATLAS detector 2 | 2 | 1 | 2 | 0.604 px |
| Vesta detector 6 | 7 | No residual match | No residual match | Bloom centroid 0.281 px |
| Vesta detector 3 | 25 | No residual match | No residual match | Bloom centroid 0.382 px |

Vesta is recovered through a separate saturated-bloom mask track, one per detector, with **no ML score** and explicit non-photometric warnings. The forest worsens the detector-2 comet ranking. The heuristic remains available for review.

Shared-reference ablation gives 25 residual tracks with detector-6 comet first, but zero detector-2 comet tracks. Leave-one-out references recover detector-2 comet among two tracks: that real improvement belongs to classical reference construction, not ML. `models/archive/v1/real-evaluation.json` records settings, fixture hashes, source revision and bloom/shared-reference ablations. Its bloom rank is internal to that evidence stream, not a merged ML rank.

## Independent real-background injection: v1 failure

Four newly retrieved M101 DR1 detector-2 exposures were absent from all v1 training and comet/Vesta examples. They form **one independent parent field**, not 150 independent fields. `models/archive/v1/real-background-evaluation.json` records URLs, source SHA-256 hashes, model hash, WCS coordinates, masks, local ePSF selections, actual candidate features and per-trial metrics. Model v1 and native inputs remain unchanged.

Production preparation registers the four images onto a north-up 59x59 grid centered at ICRS (210.80227, 54.34895), with 6.15 arcsec pixels over a six-arcminute square. Midpoints are 2025-05-10 17:05:35.300, 17:07:44.231, 17:09:53.161 and 21:59:06.620 UTC: relative hours `[0, 0.03581417, 0.07162806, 4.89203333]`. Finite coverage ranges approximately 60%..95%. Early epochs cluster within 4.3 minutes, followed by a 4.82-hour gap. Passband variation and absent PSF matching remain warnings.

This uses **actual local native ePSFs**, not the Gaussian truth profiles used for training. The EPSF tables contain 441 local 33x33 pixel-convolved response stamps oversampled five times. Following the [official IRSA tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/), the evaluator uses CRPIX1A/CRPIX2A to obtain parent detector coordinates and select the closest local ePSF. It samples the supplied pixel-convolved response at native pixel centers without another convolution, applies native masks, and uses the same WCS, bilinear interpolation and support normalization as production. A rotated-WCS/masked-pixel test compares this response with independently changing a native FITS image and preparing it.

Thirty trajectories (seed 932711) combine six random directions/positions at each speed 1, 4, 10, 25 and 50 px/hour. Positions advance in actual hours on the tangent-plane grid and have recorded ICRS coordinates. Five brightnesses per trajectory give 150 sparse, one-source trials. Expected coordinates never enter detection or inference. Flux is constant in native image-pixel-sum units within a trial; the levels target median projected peaks 3, 6, 12, 24 and 48 times the robust unmodified background pixel MAD scale. This brightness convention is **not calibrated source SNR**. Pixel phase, masks and local ePSFs change actual epoch peaks; sources leaving coverage are not moved back into view.

The unmodified control has one candidate, score 0.065506, with unknown physical identity. None of the injected trajectories match it before injection. Of 150 trials, 135 have a finite center in at least three epochs. Detection recovers 67, or 44.67% of all trials and 49.63% of the center-coverage subset. Sparse-cadence self-subtraction, masking, blending and leaving the field all remain possible failure causes; this study does not identify every cause independently.

| Frozen v1, correlated injection trials | Heuristic | Forest |
| --- | ---: | ---: |
| Recovered before ranking | 67/150 | 67/150 |
| Retained in three reviews | 67/150 | 67/150 |
| Retained in one review | 65/150 | **0/150** |

No trial contains more than three candidates, so top-three cannot establish ranking benefit. The additional one-review diagnostic was introduced after observing this candidate-count limit; it is descriptive, not preregistered confirmatory evidence. It exposes systematic degradation. Fifty-two matched injections score exactly zero; the maximum matched score is 0.051489, below the unmodified control score. No peak cap is reached. Unknown other tracks remain unlabeled; no real-background precision or false-positive rate is computed.

| Peak/background-MAD multiplier | Trials | Detector recovery | Heuristic top one | Forest top one |
| --- | ---: | ---: | ---: | ---: |
| 3 | 30 | 3 | 3 | 0 |
| 6 | 30 | 9 | 8 | 0 |
| 12 | 30 | 17 | 16 | 0 |
| 24 | 30 | 19 | 19 | 0 |
| 48 | 30 | 19 | 19 | 0 |

These trials share four backgrounds, and five brightnesses reuse each trajectory; confidence intervals pretending all derivatives are independent fields would mislead. This is registered-real-background injection, not a raw detector forward simulation. No additional photon noise or variance update is applied, and fixed flux density across changing local passbands is approximate.

Reproduce from the read-only downloaded sources and their `downloads.json`:

```bash
PYTHONPATH=backend/inference python -m training.evaluate_background --input-dir /path/to/spaceapps-inference-real-data --model-dir backend/inference/models/archive/v1 --output /tmp/spherex-v1-real-background.json --designation initial-frozen-v1-check
PYTHONPATH=backend/inference python -m training.diagnose_domain --field-cache backend/inference/models/archive/v1/field-candidates.json
```

### Domain diagnosis

Matched native injections have median features `[3, 0.236, 48.34, 24.02, 0.388, 3.780]`; v1 training positives have `[4, 0.353, 6.865, 5.170, 0.216, 1.856]`. Injection median SNR reaches 236.48 versus a training-positive maximum 17.765; peak ratio reaches 8.677 versus 3.200. Training already has 70 three-epoch positive rows, 41 four-epoch, 46 five-epoch and 25 six-epoch rows, so absence of three-epoch positives cannot alone explain failure.

`v1-domain-ablation.json` records counterfactual probes applied to every candidate without changing observed rows or the model. Substituting only training-positive median peak ratio, capping only SNR at training-positive maxima, or forcing only epoch count six each still gives zero known injections first. Combining shape substitution and SNR caps gives only two. These diagnose dependence and joint domain mismatch; they are not physically valid feature corrections, and do not justify falsifying measured features. Broader physical simulation and a newly reserved final field are required.

## Limits and next evidence

Domain shift remains substantial: sparse positive training rows, only two selected real objects, no independent real-survey precision, no measured planet probabilities, short linear arcs and low detector completeness. Runtime settings may depart from training; the model remains experimental. Pipeline peak/candidate limits can make searches incomplete and are surfaced as warnings.

The initial M101 sample was expanded to four independent native exposures for the frozen-v1 study below. After observing its failure, M101 and all derived injections become development data for subsequent models. They must not be described as a held-out final test for v2. The next model requires an untouched parent field after freezing. Representative real labels remain necessary before calibrating an acceptance threshold.

Primary documentation checked directly because Context7 was unavailable: [RandomForestClassifier probability semantics](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html), [sklearn-onnx conversion options](https://github.com/onnx/sklearn-onnx/blob/main/docs/parameterized.rst), [ONNX Runtime threading](https://onnxruntime.ai/docs/performance/tune-performance/threading.html).
