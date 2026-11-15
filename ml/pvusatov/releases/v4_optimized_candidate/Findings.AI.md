# Whole-CLI performance findings

No meaningful whole-CLI acceleration was established. This candidate stays unpromoted. Median gains are small, and Vesta D6 and the empty case are slower. The prior approximately 1.54× feature-stage DEV result does not transfer to a whole-CLI claim.

| Fixed case | Linked tracks | Reference median wall, s | Candidate wall, s | Wall ratio | Reference CPU, s | Candidate CPU, s | CPU ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| comet-d2 | 1 | 1.4457 | 1.4427 | 1.0021× | 1.4155 | 1.4172 | 0.9988× |
| comet-d6 | 36 | 1.9884 | 1.9691 | 1.0098× | 1.9695 | 1.9572 | 1.0063× |
| vesta-d3 | 112 | 2.2948 | 2.2329 | 1.0277× | 2.2801 | 2.2137 | 1.0300× |
| vesta-d6 | 17 | 1.7666 | 1.8077 | 0.9773× | 1.7500 | 1.7923 | 0.9764× |
| engineering-density 8 | 2603 | 39.3982 | 38.8441 | 1.0143× | 39.3640 | 38.8041 | 1.0144× |
| empty-negative | 0 | 1.3646 | 1.3864 | 0.9842× | 1.3538 | 1.3670 | 0.9904× |

Ratios are reference/candidate, so values below 1 mean a slower candidate. These are three alternating paired repetitions per case on one local pinned CPU with math threads 1. The longest case is the exact existing engineering density 8 fixture at 32×512×512; its three reference wall times are39.623,39.131,39.398 seconds and the candidate times are38.944,38.844,38.558 seconds. All 36 CLI processes exit successfully. Peak wait4 RSS is 663.43MiB, below the 2 GiB sampled stop. No timeout or RSS interruption occurs. This is an observed local bound, not a hard memory cap or a worst-case deployment guarantee.

All 18 paired comparisons have exact scientific JSON after removing only `provenance.feature_producer`. This includes every candidate score, ID/order, detection value, threshold, setting, warning, frame and resource record. All 1836 PNG comparisons are direct byte equality checks. The four real fixtures contribute 1026 comparisons; engineering density 8 contributes 792 and the empty negative case 18. The density 8 fixture is byte-identical to the published existing fixture hash69cb2197506e614edad69cfa72404d1d18a95667eddbbea086dfc12b0c5dbda7.

`benchmark-cli-evidence.json` records every execution order, wall/process-CPU timing, sampled and wait4 RSS, scientific JSON digest, PNG hash, source/model/input identity and negative case. `source-inputs-before.json` records original V4 runtime/model/prototype/fixture identities, all rechecked unchanged after the benchmark. Benchmark executable candidate bytes are similarly rechecked. Additional test-only tamper/CLI checks were appended after this frozen measurement; `verification.json` records both benchmark-time and final test hashes. Runtime, model, dependency lock, original fixture and measured adapter bytes did not change after measurement.

The ported adapter produces exact float64 and float32 bit patterns, candidate IDs, complete missingness diagnostics, feature-contract metadata, selected C596 scores and full order on signed/masked/empty-epoch cases and 4095/4096/4097-row block boundaries. Four independent in-process real-preset runs also compare the complete feature matrices and diagnostics, all scientific JSON and every PNG byte. Coordinated adapter/manifest and reference/manifest tampering must fail against the baked descriptor before pixels; standalone modified-adapter CLI testing also verifies that tampered adapter code is never executed.

The actual adapter is 5ac4716292ba19af8b7ef124aac9c4386d8b501e055d46c898bae70f9a9e2ca6. Original843 remains the immutable training/reference extractor. Model C596 and metadata472 are unchanged, and no learned association policy or new model was introduced. No new native holdout or FINAL read, download, training, policy change, deployment or production wiring occurs. All generated large inputs and outputs remain under `/tmp/spaceapps-v4-optimized-cli-20261115`.
