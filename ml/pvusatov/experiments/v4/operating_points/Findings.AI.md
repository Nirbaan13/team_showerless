# Fixed-model threshold operating points

Default SNR 4, release gates and both models remain unchanged. This DEVELOPMENT study measures how a request's per-epoch threshold changes residual-track proposals, recovery at fixed review budgets and processing work. The source-bound protocol was written before new draws: `protocol.json`, SHA256 `50260bdf28f7bb3cd6db237e1c0f65e505f597fd8634098050001306d72922e0`.

Fixed models are deployed C13 (`c13ba957…`) and selected C596 (`c596f66f…`), using byte-identical graph/metadata snapshots. Every field's same images, physical times and latent sources feed thresholds 3/4/5/6 with sigma 0.8, 100 peaks/epoch, ≥3 epochs and 0.5–60px/h. Both models score identical measured proposals at each setting; full 30 features are retained, and C596 uses its fixed first 27 subset. All four feature/prediction passes complete before truth matching. No fitting, adaptive parameter selection, FINAL access or runtime edits occurred.

There are 100 independent synthetic fields (seeds3805000–3805099), 199 moving-source truths, the original calibration bank, varying PSFs and extended sources on seed%3==0. Optional native coverage comprises 54 correlated derivatives on only two TRAIN backgrounds: speeds 0.1/1/10px/h × three fixed RNG directions × brightness 3/12/48, seeds 3805201/3805203. Native origins are sampled without recentering. Actual native masks are passed; synthetic instrument masks are absent and explicitly recorded. Unmatched native rows remain UNKNOWN.

## Allplanned recovery and workload

| Per-epoch threshold | Synthetic raw rows | Detected /199 | C13 K1/K3 | C596 K1/K3 | Profile CPU sum |
|---|---:|---:|---:|---:|---:|
|3 |7,773 |77 |30/52 |41/70 |7.92s |
|4 |6,078 |76 |29/51 |40/70 |6.71s |
|5 |5,135 |71 |30/49 |39/66 |6.02s |
|6 |4,444 |68 |28/49 |37/63 |5.54s |

| Per-epoch threshold | Native raw rows | Detected /54 | C13 K1/K3 | C596 K1/K3 | Profile CPU sum |
|---|---:|---:|---:|---:|---:|
|3 |11,487 |10 |2/5 |7/8 |53.56s |
|4 |5,771 |14 |6/12 |11/13 |32.63s |
|5 |4,044 |14 |8/10 |11/14 |23.58s |
|6 |3,144 |12 |9/10 |11/12 |18.47s |

All 156 planned records (100 synthetic, 54 native, 2 native controls) completed; no missing truths, processing errors, reached 100-peak limits or linker-limit exceptions occurred. CPU figures cover per-setting peak/link/feature/scoring work; shared residual formation, model startup and latent generation are excluded. Whole study wall time 86.66 s using four math-single-thread workers; peak worker RSS 299.66 MiB.

These are raw residual pools. A default 100-entry publication cap would apply to 17/16/13/11 synthetic pools and 27/27/0/0 native derivative pools at thresholds 3/4/5/6. The full BLOOM publication flow is outside this study; its existing protection of the first three residual reviews preserves the stated K1/K3 budgets.

For C596, paired whole-synthetic-field bootstrap differences in K3 recovered objects per field versus threshold 4 are: threshold 3,0.00 [−0.03,+0.03]; threshold 5,−0.04 [−0.08,−0.01]; threshold 6,−0.07 [−0.14,−0.01]. These are exploratory percentile 95% intervals from 5,000 prespecified paired resamples of all 100 independent fields, including empty fields. No population confidence interval is claimed from the two native parents. Native per-parent and actual matched-epoch injection-path-span≥3 diagnostics are saved separately. The 3 px criterion is an engineering diagnostic, not a fundamental limit or confirmation of motion.

## Empty-field and native-control work

Ten known noise-only synthetic fields produce 23 linked proposals in 4 fields at threshold 3, versus zero at 4/5/6. Ten known artifacts-only fields all produce proposals at every threshold: 786/555/469/415 total. Their K3 review slots stay 28 at every setting; noise-only fields add 7 slots at 3. Raising the threshold therefore removes weak noise proposals while structured artifacts can remain.

The two uninjected native backgrounds produce 441/211/149/115 UNKNOWN residual tracks at 3/4/5/6. Those counts describe proposal work, not false-positive precision. Both backgrounds have at least three tracks at every setting, so a fixed K3 still requests six reviews across them. The native injection comparisons have 54/54 common-attributable trials versus threshold 4 at every setting.

## Why lowering the threshold can reduce recovery

A post-hoc diagnosis replayed one preregistered TRAIN01 derivative (speed 1 px/h, direction 0, brightness 3) from its exact stored path/flux and verified the image hash. No models or FINAL data were read for this trace. Threshold3 contains every threshold 4 peak and reaches no cap. Both pre-dedup pools contain 12 hypotheses matching the injection. The unchanged baseline-score-ordered pair-exclusive pruning retains zero matching hypotheses at 3 but one at 4. Earlier accepted tracks share measured detection pairs with the matching alternatives and suppress them; those accepted native tracks are described only as not matching this injection, not as negative ground truth.

This establishes a concrete upstream association/deduplication failure. Lowering a per-epoch cut expands the peak set, but the final linked pool is not guaranteed to preserve every previous track. A later ranker cannot recover a candidate that has already been discarded. No detector/deduplication policy was altered by this diagnosis. Exact evidence is `results/nonmonotonic-linker-case.json`, SHA256 `070473fb401645f40a7a821096c6e82b54538769aebc1d137573a8677e9470e6`.

## Practical interpretation

Threshold3 increased synthetic proposals by28% for one extra detected object and unchanged C596 K3; on these native TRAIN derivatives it nearly doubled proposals while losing four detections and five K3 recoveries. Lowering the setting therefore deserves a workload and association check rather than an assumption of better sensitivity.

Thresholds5/6 reduce raw proposal and CPU burden, with fewer synthetic recoveries. The native N2 result at 5 is descriptive and cannot establish a new default. Threshold4 remains the existing default. The per-epoch SNR quantity is a residual/MAD proxy; C596's sigmoid pairwise utility is uncalibrated, and its training profile remains threshold 4. No real precision or calibrated probability is inferred from this sweep.

Evidence index: `results/evidence-index.json`, SHA256 `65b624f241196b527c24e1c11c6a3de863f3206bef09a0d919343e3d123b00db`. It binds the protocol, full row-summary/analysis, fixed metadata snapshots and 156 derived feature/score caches archived as `results/derived-feature-caches.tar.gz` (10,806,051 bytes). The archive contains numeric derived data and image/mask hashes; no raw images, FITS or model weights are included. All source/hash checks and allplanned identities passed. Four study tests and two paired-analysis tests passed.
