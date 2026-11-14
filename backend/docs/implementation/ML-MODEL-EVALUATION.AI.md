# Frozen v2 motion-track model and evaluation

`spherex-track-rf-v2` is the selected experimental ranker. It improves known-injection retention at three reviews on the reserved synthetic test and on one newly reserved real background, but **worsens one-review retention on that real background**. Detector completeness is low: 213/785 synthetic injections and 28/150 final real-background injections reach ranking. Scores are uncalibrated ranking values, not planet probabilities, object classes, detection significance or discovery claims. No real-survey precision or survey-wide performance is established.

## Frozen artifact and provenance

Runtime files are `backend/inference/models/ranker.onnx` and `metadata.json`. The ONNX artifact is 3,679,990 bytes, model ID `spherex-track-rf-v2`, SHA-256:

```text
dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9
```

Training-manifest SHA-256 is `577c492d424ed21974a8db35d2d5fb0fff2697d605ad921ace2d6057eb796b04`. The original freeze was **2026-11-14 16:39:45 UTC**, before opening the reserved real-field pixels. `freeze.json` remains unchanged. The selected weights, six measured features, detector, training source and selection decision have not changed after the final evaluation.

An independent pre-test audit identified missing coverage-subset recovery accounting and ambiguity when an injected trajectory already matches a control track. At **16:41:55 UTC**, before opening the reserved real pixels, an accounting-only evaluator amendment was recorded in `pretest-accounting-amendment.json`. It excludes preexisting control matches from attributable recovery while retaining raw spatial matches, and reports a separate finite-center-coverage cohort. The original evaluator remains in `training/archive_v2/evaluate_background.py`; no model, feature, injection, source placement or detector change accompanied the amendment. [Accounting amendment](ML-MODEL-V2-PRETEST-ACCOUNTING.AI.md) and [evaluation protocol](ML-MODEL-V2-EVALUATION-DESIGN.AI.md) preserve the sequence. The final synthetic evaluation used the unchanged frozen synthetic evaluator.

`release-manifest.json` inventories runtime/evidence hashes and distinguishes final evidence from development. Immutable training/freeze manifests retain their historical `final_real_field_opened=false` and `reserved_real_field_unopened=true` declarations at the recorded pre-test times; these are not claims about the current state. Full real-background provenance, source URLs, FITS hashes, local ePSF selections, trajectories, measured features and matches are retained in compressed JSON alongside compact summaries. Raw development experiment caches remain ignored.

## Training, features and selection

Exact production feature order is `epoch_count`, `fit_rms_px`, `median_snr`, `min_snr`, `snr_coefficient_of_variation`, `median_peak_ratio`. Features are measured by production `Candidate.features()` without expected positions, target names or real labels. Positive training rows match simulated injected paths within 1.5 pixels at every linked epoch. No real observation pixels enter fitting.

V2 addresses the domain mismatch diagnosed after v1 failed on M101: instrument ePSFs and analytic core/wing responses, pixel phase and orientation, varying per-epoch PSFs, extended static/blended sources, three to eight epochs with irregular physical-hour cadences, masks, noise, registration residuals, flux variability and missing epochs. Source and transient-artifact integrated amplitudes share the same log-uniform 6..600-times-noise law. This removes an explicit amplitude-label shortcut but does not establish that the simulation represents the survey population. The 384-stamp six-detector calibration bank contains instrument knowledge only; its SHA-256 is `793e05135438c95b8eaeace21948b34fe2eb49cd581be9e81dfff2b493e08d6d`.

Whole synthetic fields are the grouping unit; all epochs and candidate rows stay with their parent field:

| Partition | Independent fields | Seeds | Use |
| --- | ---: | --- | --- |
| Training | 1,500 | 10000..11499 | Fit only |
| Validation | 400 | 300000..300399 | Model selection |
| Development diagnostic | 200 | 900100..900299 | Development, despite historical `test` JSON key |
| Reserved final synthetic | 400 | 500000..500399 | Evaluated after freeze |

Training contains 50,983 rows, 866 positive. Negative epoch-stratum weights match the synthetic-positive marginal across 3, 4 and >=5 epochs, capped at 0.05..50 and combined with balanced class weights. Extended backgrounds occur every third seed; PSFs vary by epoch. Six forest choices combine `max_features` of 1.0 or `sqrt` with `(minimum leaf size, depth)` of `(4, 12)`, `(12, 16)`, `(24, unlimited)`. Validation selection prioritizes macro cadence-family unique-object recall at one review, then three reviews, then candidate average precision.

The selected forest uses all six features, 150 trees, minimum leaf size 4, depth 12, `max_features=sqrt`, balanced classes, random seed 42 and one training job. Validation is not refitted. Feature ablations suppressing epoch-count or epoch-count plus shape splits were rejected on development evidence; they did not alter measured inference features. Their validation keys and M101 diagnostics remain in `feature-ablation-development.json`; generator ablations remain in `v2-development-ablation.json`.

Validation has 791 injections and 215 detector recoveries. Heuristic versus forest retention is 41 versus 76 at one review and 67 versus 132 at three reviews; candidate average precision is 0.058641 versus 0.242185. These are selection evidence, not final estimates.

Detector settings match production defaults: leave-one-out references, minimum SNR 4, filter sigma 1.2 pixels, maximum 100 peaks per epoch, speed 0.5..60 pixels/hour, link radius 1.4 pixels, minimum three epochs and minimum support 0.8. A ranking gain cannot recover objects the detector missed.

## Reserved synthetic test: both review budgets

Both rankers receive identical candidates. Retention counts unique injected objects, while average precision labels candidate rows that may include several matches to one object. Each budget allows at most that many candidate reviews per field; there is no acceptance threshold.

| Final synthetic test, 400 independent fields | Heuristic | Frozen v2 |
| --- | ---: | ---: |
| Injected objects | 785 | 785 |
| Candidates | 11,701 | 11,701 |
| Recovered before ranking | 213 (27.13%) | 213 (27.13%) |
| Retained in one review per field | 57 (7.26%) | 81 (10.32%) |
| Retained in three reviews per field | 99 (12.61%) | 143 (18.22%) |
| False selected tracks, one review | 257 | 233 |
| False selected tracks, three reviews | 751 | 708 |
| Candidate average precision | 0.091473 | 0.255627 |

The forest retains 81/213 (38.03%) of detector-recovered objects at one review and 143/213 (67.14%) at three reviews. Overall recovery remains bounded by detector completeness.

A paired bootstrap of whole independent test fields, 10,000 draws with seed 274912, gives forest-minus-heuristic 95% percentile intervals of **+1.31..+4.86 percentage points** for one-review recall and **+3.67..+7.67 points** for three-review recall. False selected tracks per field differ by -0.095..-0.025 at one review and -0.150..-0.070 at three reviews. These intervals describe sampling variation within this generator and say nothing about real-survey generalization.

The 40 noise-only fields contain no detected candidates. The 40 zero-injection artifact fields contain 1,593 candidates; each ranker selects 30 false tracks at one review and 81 at three reviews. Unconditional ranking does not control false discovery. Exact final metrics are in `models/evaluation.json`, bootstrap intervals in `evaluation-statistics.json`, and descriptive cadence/epoch/detector/control subsets in `evaluation-subsets.json`. Complete field features, labels and baseline scores are preserved in `evaluation.fields.json.gz`; these subsets were computed from existing final outputs without changing or rerunning the test generator.

## Reserved real background: one parent field

The final field is a separate DR1 detector-1 observation group near ICRS (127.69444, -39.17760), absent from training and all M101/comet/Vesta development. Four native FITS exposures form **one independent parent field**. Production preparation registers them onto a north-up 59x59 grid with 6.15 arcsec pixels over a six-arcminute square. Actual relative midpoint hours are approximately `[0, 0.03581444, 0.07162833, 0.10744250]`: a short 6.45-minute arc. Finite coverage per epoch is 42.95%, 88.37%, 92.33% and 92.16%. Passband variation and missing PSF matching remain preparation warnings.

The predeclared matrix uses 30 trajectories, six deterministic positions/directions at each speed 1, 4, 10, 25 and 50 pixels/hour, seed 932711. Five brightnesses target projected peak/background pixel-MAD multipliers 3, 6, 12, 24 and 48, giving 150 sparse one-source trials. These brightnesses are not calibrated source SNR. Native pixel-convolved local ePSFs are sampled at native pixel centers without another convolution, then projected with the production WCS/interpolation/mask treatment. Expected coordinates are used only for offline matching after detection and scoring.

Five brightnesses reuse each trajectory and every trial shares the same four backgrounds. They are **150 correlated derivatives of one field**, not independent survey fields. No independent-field confidence interval is assigned to them. The study does not add photon noise or update variance, and is not a raw detector forward simulation. Fixed injected flux density across changing local passbands is approximate. The archived evaluator includes a generic long-gap limitation inherited from its M101 use; this final field has the short cadence stated above.

| Final real-background injection test | Heuristic | Frozen v2 |
| --- | ---: | ---: |
| Planned injections | 150 | 150 |
| Finite center in >=3 epochs | 150 | 150 |
| Attribution-eligible injections | 150 | 150 |
| Detected before ranking | 28 (18.67%) | 28 (18.67%) |
| Retained in one review | **15 (10.00%)** | **11 (7.33%)** |
| Retained in three reviews | 17 (11.33%) | 24 (16.00%) |

Both predeclared budgets must be reported. V2 retains more known injections at three reviews but fewer at one review. Conditional on the 28 detections, forest retention is 11/28 (39.29%) and 24/28 (85.71%); low overall completeness remains the larger limitation. Every trial has >=3 finite-center epochs, so coverage-cohort numerators and denominators equal the all-trial results. There are zero ambiguous preexisting control-match trials, no peak caps (maximum 23 detected peaks in any epoch), and zero exactly-zero scores among matched positive candidate rows. Failure to detect the other 122 sources is not cured by ranking.

| Peak/background-MAD multiplier | Trials | Detected | Heuristic top 1 | V2 top 1 | Heuristic top 3 | V2 top 3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 30 | 0 | 0 | 0 | 0 | 0 |
| 6 | 30 | 0 | 0 | 0 | 0 | 0 |
| 12 | 30 | 7 | 0 | 3 | 0 | 6 |
| 24 | 30 | 10 | 6 | 4 | 8 | 8 |
| 48 | 30 | 11 | 9 | 4 | 9 | 10 |

The unmodified control contains three tracks of **unknown physical identity**. In heuristic order their model scores are 0.081893, 0.230419 and 0.433891, with model ranks 3, 2 and 1. Their actual features and positions remain recorded. Unmatched candidates remain unlabeled; neither these control tracks nor other real tracks are called false positives. No real-background precision, false-positive rate, calibrated probability or population detection rate follows from these trials.

`models/real-background-evaluation.json` contains compact provenance, control records, all-trial and coverage-cohort counts, brightness/speed subsets, warnings and hashes. `real-background-evaluation.trials.json.gz` preserves the complete original evaluator output, including every trajectory, ePSF selection, injected flux, matched feature vector, score and offset. Its decompressed bytes match the summary's `full_evaluation_sha256`.

## Development evidence and preserved v1 failure

M101 was independent for v1. After v1's failure informed v2 design, all M101 images and derivatives became **development data for v2**. V1 retained 0/150 known injections at one review versus heuristic 65/150, with 52 exactly-zero matched scores. V1's original artifact, manifest, synthetic results, real-background output and domain diagnosis remain in `models/archive/v1/`; the original report is [ML-MODEL-V1-EVALUATION.AI.md](ML-MODEL-V1-EVALUATION.AI.md). This negative evidence is not replaced by v2.

On the same correlated M101 derivatives, v2 detects 67/150, retains 52 at one review versus heuristic 65, and both retain 67 at three reviews. Only 135 trials have a finite center in >=3 epochs. No trial has more than three candidates, so equal top-three results do not establish ranking benefit. `m101-development-evaluation.json` and its compressed full output preserve these development diagnostics; their older accounting layout predates the final-field amendment.

Selected comet/Vesta cutouts are recovery examples for **two objects**, with correlated detector views, not independent survey labels:

| Development cutout | Residual candidates | Heuristic known-target rank | V2 known-target rank | Recovery |
| --- | ---: | ---: | ---: | --- |
| 3I/ATLAS detector 6 | 10 | 1 | 3 | Residual track, maximum offset 0.539 px |
| 3I/ATLAS detector 2 | 2 | 1 | 1 | Residual track, maximum offset 0.604 px |
| Vesta detector 6 | 7 | No match | No match | Separate bloom centroid, offset 0.281 px |
| Vesta detector 3 | 25 | No match | No match | Separate bloom centroid, offset 0.382 px |

Vesta's saturated-bloom evidence has **no ML score** and is explicitly non-photometric. A shared reference loses the detector-2 comet track, while leave-one-out construction recovers it; that improvement belongs to classical preparation, not learned ranking. Unknown real candidates stay unlabeled. `models/real-evaluation.json` records fixture hashes, settings and these ablations.

## Runtime, parity and reproduction

`load_ranker` validates model SHA-256, feature order, schema, classes `[0, 1]`, graph metadata, tensor types/shapes and graph label/probability consistency. CPU inference uses one intra-operation and one inter-operation thread, sequential execution and no spinning. It performs no fitting and imports no sklearn/training module. Non-finite or malformed features are rejected; an empty `(0, 6)` matrix returns an empty score vector. No estimator pickle is shipped.

The interface identifier `random_forest_vote_fraction` means the mean class-1 **weighted leaf fraction** across trees (`predict_proba`), not a fraction of hard binary tree decisions. Selected-estimator versus ONNX parity is preserved on 1,344 deterministic training/development/random rows: maximum absolute error `4.818675930495786e-7`, with absolute/relative tolerance `2e-6`. Separate tests compare a different small exported forest on 1,250 rows.

The training manifest records actual source digests and Python 3.14.4, NumPy 2.5.3, SciPy 1.18.1, sklearn 1.9.1, skl2onnx 1.20.0, ONNX 1.23.2 and ONNX Runtime 1.30.0. Inference targets Python >=3.12. Cross-version bit-identical retraining is not promised. The bank and frozen source digests, plus the sole documented pre-test accounting exception, distinguish this implementation from its historical base revision.

The following commands document offline reproduction from repository root using training dependencies. **They were not rerun to promote this release.** The training command deliberately fits a new offline copy in `/tmp`; it does not replace shipped weights. Keep the shipped frozen artifacts as the source of the reported final results.

```bash
PYTHON=/home/usatovpavel/edu/UtilsAI/.venv/bin/python
REPRO_DIR=/tmp/spherex-v2-reproduction
PYTHONPATH=backend/inference "$PYTHON" -m training.train_v2 \
  --train-fields 1500 --validation-fields 400 --test-fields 200 --test-start 900100 \
  --extended-backgrounds --varying-psf --epoch-balanced \
  --designation 'synthetic development diagnostics; reserved test remains unopened' \
  --output-dir "$REPRO_DIR"
PYTHONPATH=backend/inference "$PYTHON" -m training.evaluate_synthetic \
  --model-dir "$REPRO_DIR" --start 500000 --fields 400
PYTHONPATH=backend/inference "$PYTHON" -m training.evaluate_real \
  --model-dir backend/inference/models --output /tmp/v2-selected-development.json
PYTHONPATH=backend/inference "$PYTHON" -m training.evaluate_background \
  --model-dir backend/inference/models --input-dir /path/to/reserved-final-fits \
  --right-ascension-deg 127.69444 --declination-deg -39.17760 \
  --designation frozen-final-heldout --output /tmp/v2-final-real-reproduction.json
(cd backend/inference && "$PYTHON" -m pytest -q)
"$PYTHON" backend/inference/smoke.py
```

The real input directory must contain the four native source files and `downloads.json` matching the final summary's URLs and digests. Calibration-bank generation and final reproduction must not read or overwrite shipped runtime artifacts. Future model development using this final field requires reserving a new independent parent field. Representative real labels and a separate calibration study remain necessary before defining an acceptance threshold or making survey claims.

Release verification after coherent promotion: the full Python suite passed **78 tests in 9.36 seconds**, including five release-integrity checks and eight real-background evaluator checks. The packaged real-data CLI smoke test completed preparation, inference and rendering and verified the exact v2 SHA-256 above. Logs are `/tmp/spaceapps-v2-release-pytest.log` and `/tmp/spaceapps-v2-release-smoke.log`. Release-integrity checks verify all 27 inventoried file digests, parse every released JSON, recompute final real cohorts from the compressed trials, confirm synthetic/development seed separation and enforce the sole documented source-hash exception. No retraining or final image evaluation was run for this bookkeeping repair.
