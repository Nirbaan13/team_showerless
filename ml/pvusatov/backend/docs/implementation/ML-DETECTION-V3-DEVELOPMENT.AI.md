# V3 detector development experiments

Status: experimental detector research only. Production `ml_inference/`, training sources, and released model artifacts are unchanged. V2 frozen ranker SHA-256 is `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9`.

## Question and boundaries

Can blind multi-epoch evidence recover moving sources missed by the per-epoch SNR4 gate at the same one-review and three-review budgets? The probe compares paired parent fields. Known injected positions enter matching only after candidate search, never the detector or score. Fresh simulated development seeds begin at 1200000; these are not a final test. Entire parent fields are the grouping unit. Old v2 final real field may be development for v3 but is never a new final. Newly quarantined native final fields are not opened by this experiment.

The first control changes only the existing peak threshold (4, 3, 2.5, 2), retaining the six measured-peak observables and frozen v2 scoring. The second probe fits linear moving Gaussian templates jointly after eliminating a constant spatial nuisance by subtracting the temporal mean. It streams velocity hypotheses, retaining only the best statistic per reference pixel; it never allocates a velocity cube. Motion-dependent template normalization accounts approximately for attenuation caused by the mean subtraction. Individual epoch positions are template hypotheses and must not be called measured peaks; the frozen six-feature forest is not applied to these joint candidates.

A constant Gaussian response and independent equal-noise epoch approximation motivate the normalization. Real fields have masks, correlated interpolation noise, variable PSFs and passbands. The search statistic is uncalibrated. It is neither photometry nor a detection probability, and multiple-trial significance is not claimed. Static source variability and coherent residuals may dominate the joint search. The implementation reports these limitations rather than inferring precision from unmatched real tracks.

## Resource bounds

The prototype accepts 3..32 frames on grids at most 512 square, physical-hour strictly increasing times, declared minimum/maximum speeds and an endpoint-displacement grid. It caps pixel-epoch work, rejects incomplete work-cap searches rather than silently reporting partial results, and caps returned candidates with an explicit diagnostic. Defaults use 600 million pixel-epoch operations, 64 pixel displacement, 1 pixel endpoint steps and 100 candidates. The current benchmark explicitly uses 48 pixel displacement. Objects moving farther, lacking full-window coverage, or appearing only in omitted windows can be missed. A 512-square/32-frame request may hit the work cap: bounded memory does not imply acceptable latency or complete velocity coverage.

Workers are capped at six, with one BLAS/OpenMP thread each. Shared Python is `/home/usatovpavel/edu/UtilsAI/.venv/bin/python`. Scratch outputs are `/tmp/spaceapps-v3-detection/`.

## Initial threshold ablation

100 paired whole development fields, seeds 1200000..1200099, 197 injected objects; the existing v2 physical generator uses varying epoch PSFs and extended backgrounds in every third field.

| Per-epoch threshold | Detected objects | V2 RF at K1 | V2 RF at K3 | Candidate rows | Median detector wall s | P95 detector wall s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4.0 | 53 | 25 | 37 | 4175 | 0.105 | 0.690 |
| 3.0 | 55 | 25 | 38 | 5218 | 0.119 | 0.796 |
| 2.5 | 58 | 24 | 41 | 6244 | 0.125 | 0.918 |
| 2.0 | 60 | 25 | 40 | 9147 | 0.171 | 1.179 |

Maximum worker peak RSS was 159.1 MiB, including Python and frozen ONNX runtime. No linking-work failures occurred. Measurements include concurrent workers and are development diagnostics, not production latency guarantees. Lowering the gate alone yields modest detector gains and increased synthetic false candidate burden. It has not established a convincing same-budget improvement.

## Reproduction

From `backend/inference`, set `PYTHONPATH` to this directory and `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`.

```text
/home/usatovpavel/edu/UtilsAI/.venv/bin/python experiments/v3_detection/threshold_scan.py --fields 100 --workers 6 --output /tmp/spaceapps-v3-detection/threshold-pilot.json
/home/usatovpavel/edu/UtilsAI/.venv/bin/python experiments/v3_detection/joint_scan.py --fields 20 --workers 6 --output /tmp/spaceapps-v3-detection/joint-pilot.json
```

`digital_tracking.cpp` is compiled locally into a source-hashed shared library under scratch with `g++ -O3 -shared -fPIC`. No new package or production dependency is installed.

## References

Heinze, Metchev & Trollo (2015), [Digital Tracking Observations Can Discover Asteroids Ten Times Fainter than Conventional Searches](https://arxiv.org/abs/1508.01599), motivates blind motion-space integration. This prototype uses a distinct nuisance-projected mean statistic and a much smaller, heterogeneous SPHEREx-like stack; the paper's sensitivity gains are not attributed to this implementation.

## Slow-motion engineering profile, predeclared before execution

The official challenge is a public image-change viewer and explicitly includes nearby stars, brown dwarfs, comets and asteroids. The local captured official brief is `search/challenges/12-planet-x-and-spherex.md`; the official URL is [Planet X and SPHEREx](https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/). Live retrieval returned HTTP 502 during this check, so the local capture supplies the brief text. It does not prescribe the fast asteroid-only benchmark. The official [SPHEREx survey description](https://spherex.caltech.edu/page/survey) says successive pointings follow a great circle approximately 90 degrees from the Sun, complete a region over days, and vary the sampled wavelength between exposures. Thus a speed inferred for opposition observations must not be assigned to every SPHEREx visit.

The primary paper [Searching for Planet Nine with Coadded WISE and NEOWISE-Reactivation Images](https://doi.org/10.3847/1538-3881/153/2/65) discusses only about 1.6 arcseconds of parallactic smearing in a representative one-day visit at 600 AU (geometry dependent). This is about 0.067 arcseconds/hour, or 0.011 pixels/hour on a 6.15 arcsecond grid. This conversion is an engineering comparison, not an ephemeris prediction for these fields. The fast benchmark lower bound 0.5 pixels/hour equals 3.075 arcseconds/hour and does not establish distant-body or proper-motion-star sensitivity. Months-long stellar proper motion and annual parallax require a different cadence/model; no such completeness is claimed here.

A fixed diagnostic uses three allowed augmented development parent fields: validation01 (8 epochs, approximately 14.77 hours), validation02 (5 epochs, approximately 39.22 hours), validation03 (8 epochs, approximately 32.67 hours). The exact production-prepared midpoints and registered support will be recorded. All variants remain derivatives of their original parents. Unknown controls are never assigned negative labels.

Before running, fix speeds **0.01, 0.03, 0.1, 0.3, 1.0 pixels/hour**, six uniformly sampled positions/directions per speed, and brightness factors 3, 6, 12, 24, 48 relative to the registered-background pixel MAD. Use fixed RNG seeds 1800001, 1800002, 1800003 respectively. Positions are uniform within an eight-pixel initial border and are never relocated after coverage checks. Local native ePSFs, physical hours, interpolation and production masks are used. This is 150 correlated injections per field, 450 planned trials total.

For both comparator profiles, fix minimum speed **0.005 pixels/hour**, maximum speed 60 pixels/hour, SNR4, max 100 peaks per epoch, min three epochs, support 0.8, leave-one-out median residuals and match radius 1.4 pixels. Compare Gaussian sigma1.2 (v2 profile) with sigma0.8 (experimental v3 profile), and report frozen v2 ranking only as an adaptation diagnostic. These identical search bounds remove an inappropriate fast-only gate equally for both profiles. Full controls run before injection with the same settings.

Report all planned trials and raw matches first. Report algorithm-independent finite-center coverage (at least three epochs) separately from algorithm-dependent ambiguity due to preexisting control tracks. For each comparison, the common attributable cohort excludes a trial if either profile already spatially matches an unmodified control; this is why denominators can differ across profile comparisons. Also report displacement bins and isolated-source attenuation as evaluation-only diagnostics. For total displacements below the matching tolerance, a spatial match cannot establish independent motion; the result must say so. A lower speed gate cannot undo median self-subtraction, inadequate astrometric separation or passband/PSF mismatch.

## Joint-template negative result

Twenty paired fresh development fields, seeds 1200200..1200219, contain 41 injected objects. The comparator uses SNR4/sigma1.2 and the frozen v2 RF. Joint methods rank their own uncalibrated template statistic; they do not consume RF peak features.

| Search | Detected objects | K1 | K3 | Candidate rows | Median wall seconds | Peak worker RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| V2 measured-peak detector + frozen RF | 10 | 3 | 5 | 597 | 0.040 | 153.1 |
| Joint mean-projected sum, full window | 3 | 3 | 3 | 1800 | 1.110 | 153.1 |
| Joint sum, full + sliding three-epoch windows | 6 | 4 | 4 | 1800 | 3.062 | 153.2 |

Both joint searches hit the 100-result cap on 18 of 20 fields. A robust variant ranks the sum of positive path samples with the largest epoch removed and requires at least three samples above 1.2. It reduced rows to 1044/978 for full/window searches, but detected only 3/6 objects, with K1/K3 2/3 and 3/5 respectively. These results do not support promotion. Strong transients, static variability, partial-window coverage, PSF mismatch and source self-subtraction remain problems. The windows are searched separately and may give unequal effective epoch support. The first raw joint run measured 1.11/3.06 seconds median; robust-run latency was higher under different concurrent load and is not an isolated microbenchmark.

Reproduce the two statistics with `joint_scan.py --statistic sum` or `--statistic trimmed`. Both stream hypotheses. An explicit 65,536 velocity-grid-point limit now complements the pixel-epoch work limit so even pathological endpoint step requests are rejected before a large parameter loop. C++ uses `-O3 -shared -fPIC`, with no architecture-specific or fast-math flags. Six isolated guards verify work-cap rejection without partial results, physical-time validation, all-masked support, a controlled faint mover, dense-grid rejection, and compilation in a fresh missing scratch directory. This prototype remains outside production.

## Narrower measured-peak filter and fresh-field confirmation

A 100-field development scan compared Gaussian sigmas 0.6, 0.8, 1.2 and 1.6, each at SNR3 and SNR4. Narrower responses increased detector completeness. Sigma0.8/SNR4 was selected before a separate 1000-field development confirmation with seeds 1201000..1201999. The generator, masks and parent fields are paired, and frozen v2 scoring remains identical.

| Setting | Detected objects / 2068 | Frozen RF K1 | Frozen RF K3 | Candidate rows | Median wall s | P95 wall s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sigma1.2, SNR4 | 623 | 245 | 423 | 33010 | 0.079 | 0.579 |
| Sigma0.8, SNR4 | 731 | 234 | 420 | 51293 | 0.097 | 0.855 |

The detector gain is 108 unique objects, 5.22 percentage points in this simulator; a paired whole-field bootstrap gives a 95% percentile interval of +3.86 to +6.57 percentage points. K1 changes by -0.53 points (interval -1.72 to +0.64), and K3 by -0.15 points (-1.56 to +1.26). Thus increased detector completeness did **not** establish a same-review-budget gain with the frozen forest. Maximum worker RSS was 159.9 MiB; no linking-work failures occurred. These are concurrent-worker development timings, not guaranteed service latency. A separately trained profile-matched ranker is needed before a detector/ranker promotion claim.

Requested narrow-filter training caches use exactly the ranker experiment's whole-field partitions: 1300000..1302999 train and 1400000..1400799 validation. They contain measured peak observables, synthetic truth matches after detection, source hashes and no real controls labeled negative. They are delivered to the ranker agent under `/tmp/spaceapps-v3-detection/synthetic-sigma08-{train,validation}.json.gz`. This is new fitting work, separate from the frozen v2 deployment.

## Native development ablation and denominator accounting

The initial scan uses seven declared development parent fields, five train and two validation snapshots, with **1800 planned correlated injections**. It repeats exactly the ranker agent's cached trajectories and fluxes, reprojects the same local native ePSFs, and recomputes each profile's unmodified control before injection. All unmatched real candidates remain unknown. There are **1720 trials with at least three finite projected centers**; this algorithm-independent geometric count is separate from control ambiguity and does not determine the table denominators below.

| Setting | All planned trials | Raw spatial detections | Raw RF K1 | Raw RF K3 | All candidate rows | Preexisting-control matches |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sigma1.2, SNR4 | 1800 | 445 | 357 | 431 | 4352 | 5 |
| Sigma1.2, SNR2.5 | 1800 | 550 | 400 | 504 | 5885 | 5 |
| Sigma0.8, SNR4 | 1800 | 650 | 352 | 615 | 11051 | 15 |
| Sigma0.8, SNR3 | 1800 | 756 | 351 | 679 | 15400 | 15 |

Raw matches include coincidences with real tracks already present before injection and are not attributable discoveries. Each paired comparison additionally uses a common cohort excluding a trial if **either compared detector** spatially matched its control. These are algorithm-dependent ambiguity exclusions, not geometry or brightness selection. Sigma0.8/SNR4 compared with v2 has 1785 common attributable trials; sigma1.2/SNR2.5 compared with v2 has 1795. Report both denominators explicitly rather than comparing their numerators as if identical.

| Paired common cohort | Trials | Baseline detected | Proposed detected | Baseline RF K1/K3 | Proposed RF K1/K3 | Candidate rows baseline/proposed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sigma0.8/SNR4 vs v2 | 1785 | 436 | 637 | 353 / 426 | 350 / 604 | 4318 / 10922 |
| Sigma1.2/SNR2.5 vs v2 | 1795 | 440 | 545 | 357 / 430 | 400 / 504 | 4327 / 5855 |

On the two validation parents alone, the sigma0.8 comparison has 295 common attributable trials: detector 58→87, K1 40→85 and K3 58→87. Training parent behavior is mixed: for example train04's raw K1 drops 50→2 despite detector 84→117. This rules out a blanket same-budget generalization claim for the frozen RF. Candidate row increases on real images describe review burden; they are **not false-positive counts or precision estimates**.

Full narrow-filter caches for the ranker agent's later eight train and five validation/stress development parents were subsequently generated from their exact `short-v2`/stress `short-v1` snapshots. Each retains input/cache hashes, unknown `-2` matches, recomputed attribution eligibility and unmodified control features. These additional caches are for profile-matched development and are not combined with the initial seven-parent ablation as independent new fields.

## Slow-profile result and scope of motion claims

All 450 planned slow injections completed both searches. At least three projected centers are finite in 425 trials; no tested trajectory matches a preexisting control in either profile, so the common attributable cohort is all 450. The parent time spans are 14.7656, 39.2190 and 32.6719 hours. Counts below use the predeclared spatial matching endpoint; they do not establish resolved motion.

| Speed px/hour | Planned | Finite centers >=3 | Spatial recovery sigma1.2 / 0.8 | Frozen RF K1, sigma1.2 / 0.8 | Frozen RF K3, sigma1.2 / 0.8 | Median isolated-response retention, sigma1.2 / 0.8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.01 | 90 | 90 | 1 / 7 | 1 / 1 | 1 / 1 | 4.2% / 4.6% |
| 0.03 | 90 | 90 | 6 / 21 | 1 / 11 | 3 / 14 | 19.3% / 27.1% |
| 0.1 | 90 | 90 | 21 / 28 | 12 / 15 | 19 / 20 | 62.2% / 63.5% |
| 0.3 | 90 | 90 | 34 / 49 | 26 / 34 | 31 / 43 | 97.4% / 98.7% |
| 1.0 | 90 | 65 | 28 / 29 | 21 / 22 | 25 / 25 | ~100% / ~100% |
| All planned | 450 | 425 | 90 / 134 | 61 / 83 | 79 / 103 | — |

Response retention is an evaluation-only measurement of the isolated injected local ePSF stack after the same leave-one-out subtraction and Gaussian filtering, sampled at the known injected positions. It is not an inferred flux, completeness correction, calibrated SNR or photometric uncertainty. Changes across passbands and masks also affect it. At 0.01 pixels/hour, the longest trajectory here spans only 0.392 pixels, well below the 1.5 pixel matching tolerance. Near-static spatial matching can therefore coincide with a residual close to the source while providing no useful velocity evidence.

The slow sigma0.8 profile generates 32,592 candidate rows across derivatives versus 9,564 for sigma1.2. Unmodified controls contain respectively 137/37 tracks in validation01, 3/2 in validation02, and 68/23 in validation03; every identity remains unknown. Median detector-and-score wall time is 0.567 versus 0.158 seconds, P95 1.413 versus 0.399 seconds, and maximum worker RSS 229.6 MiB. These are development timings for these grids and eight or fewer epochs, not a worst-case 32-frame service guarantee.

A **post-hoc resolution audit**, clearly separate from the original spatial endpoint, reruns only spatially recovered trials unchanged and records each match's actual epochs, expected position span, measured peak span and original stable RF rank. Requiring the known injected positions to span at least 3 pixels over the **matched epochs** leaves 74 baseline and 90 narrow spatial recoveries; none of the 0.01 or 0.03 pixels/hour matches qualify. This is a diagnostic about geometric information, not a new optimized detector threshold. The all-planned counts above retain every unresolved trial. Match-epoch span matters because a source may leave the field at late times while a three-epoch early cluster still matches its near-static starting position.

The actual challenge also asks for Barnard's Star and other nearby stars/brown dwarfs, which this hour-scale detector benchmark does not cover. The [ESA Gaia proper-motion explanation](https://www.esa.int/Science_Exploration/Space_Science/Gaia/Proper_motion) gives Barnard's Star about 10.3 arcseconds/year, consistent with [Barnard's original measurement](https://doi.org/10.1086/104156). On this 6.15 arcsecond grid, proper motion alone is about 0.000191 pixels/hour and only 0.0076 pixels over 40 hours. This conversion is an inference from the published rate, not a measured displacement in our fields. Even the engineering 0.005 pixel/hour gate is much faster. The current integer-peak measurements, uncalibrated residual noise and short-arc fitting have not demonstrated that astrometric precision.

Supported claim: an experimental candidate-review aid for sufficiently displaced compact linear movers on registered, approximately comparable images, with a measured detection-recall improvement in the declared simulations and development injections. Unsupported claims include a newly discovered object, calibrated object probability, actual real-candidate precision, distant-planet sensitivity from unresolved matches, and recovery of nearby stellar proper motion using only hours of data. Proper-motion/parallax work needs longer separated epochs and validated subpixel astrometry, with passband/PSF handling and an appropriate annual-parallax or orbital model where needed; the image viewer can still help users inspect such data independently of this detector's demonstrated limits.

The resolution audit's expected-span>=3 pixel diagnostic, with **all 450 planned trials retained as denominator**, yields 74→90 matches, frozen RF K1 55→68 and K3 68→81. This secondary post-hoc diagnostic leaves every 0.01/0.03 pixel/hour count at zero. It remains a known-injection match diagnostic rather than confirmation of a real unknown object's motion.

Compact durable reports, whole-field paired count rows, source-report checksums and a report manifest are saved in `backend/inference/experiments/v3_detection/results/`. Large feature caches and full development trial records remain in scratch. The durable reports preserve failed and negative probes alongside positive detector-recall results.

The joint pilot's two pure-noise fields produced zero candidates in every method. Its two **known synthetic artifact-only** fields produced 43 baseline candidates versus 200 full/window raw-joint candidates (both fields capped), with zero injected movers by construction. The trimmed joint versions still produced 180/182 rows. This is direct evidence of increased burden in the simulator's static-variable/PSF/registration/transient mixture. It does not isolate which nuisance class causes each track; a static-only coherent-residual attribution ablation was not completed. Real control rows remain unknown, so these synthetic counts must not be transferred into real precision claims.

## Relocation and expanded validation recaches

At the user's request, the existing hierarchy was moved below `ml/pvusatov/`. Historical reports retain their original relative paths and source hashes; `ml/pvusatov/relocation-manifest.json` records the byte-preserving mapping. After relocation, run offline commands from repository `ml/pvusatov/` with `PYTHONPATH=backend/inference`. Frozen production detector/training/model files were not changed by the detector experiments.

Expanded native validation reuses the ranker agent's six new declared development parent caches, validation06..validation11, each with 270 injections: six directions × nine speeds (0.01, 0.03, 0.1, 0.3, 1, 4, 10, 25, 50 pixels/hour) × five brightnesses. Default minimum speed0.5 and secondary minimum speed0.005 are separate profiles with otherwise paired settings. `recache_expanded.py` copies each baseline profile's exact native sources, times, trajectories, injected flux and search bounds, changes only Gaussian sigma1.2→0.8, and recalculates unmodified controls and candidate measurements. No new trial randomness is generated.

Before the first expanded narrow recache ran, review caught that inherited `matched_geometry` would otherwise refer to old sigma1.2 candidate indices. The recacher now discards profile-dependent source geometry/attribution markers and generates fresh candidate indices, epochs, measured positions, true spans among matched epochs, measured spans and offsets for sigma0.8. The empty/error path also clears inherited candidate records. A regression test first failed on missing fresh geometry and then passed with the correct new candidate index and span. No stale-geometry expanded narrow cache was consumed or published. The full relocated inference test suite passed78 tests; the new recache regression passed separately.
