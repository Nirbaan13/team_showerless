# V4 inference quality study

The selected V4 RankNet scorer is deployed and verified. See the [release verification](../../verification/v4-release/RELEASE.AI.md) and [canonical independent results](../../verification/v4-final-repair-1/RESULTS.AI.md). The original C13/v3 graph, source and final artifacts remain immutable. All work belongs to `ml/pvusatov/`; unrelated teammate services and interfaces stay under their existing ownership.

The prospective method and frozen seed reservations are in [protocol.json](protocol.json), execution plan in [IMPLEMENTATION-PLAN.AI.md](IMPLEMENTATION-PLAN.AI.md), and original development checkpoint in [STATE.AI.md](STATE.AI.md). Research continues until 2026-11-15 12:50 UTC / 15:50 Moscow; an early successful milestone does not complete this resumed task.

The first acquisition contains 8 new TRAIN, 8 development-validation and 12 FINAL parent fields, each with eight physical SPHEREx observations. Source selection is reproducible from archived official queries and excludes prior physical observations. Raw image bytes remain outside git. A single development-selected artifact was frozen before authorized FINAL inference; a coverage-informed but scientifically blinded engineering repair and exact synthetic-equality check preceded the canonical unblinding. Frozen closures, original failures and the canonical report remain preserved under `verification/`.

`detection/` contains the measured 30-feature contract, bounded inference-only ONNX loader, development diagnostics and separately typed detection experiments. `ranker/` contains objective/weighting ablations, grouped fitting, graph export and parity checks. `evaluation/` contains source-bound generation, freeze/evaluation tools and report guards. Reports distinguish selection evidence from independent evaluation and preserve failed approaches.

The source-history directories preserve exact earlier research versions and failure evidence. They are not alternative production modules. Native pilot/main-v1 caches were excluded after an importer source-binding risk was reproduced; safe main-v2 compiles exactly the checked source bytes. No native UNKNOWN controls are negative training labels. Ranking scores are not calibrated object probabilities.

Run the portable tool tests from repository root in the existing scientific environment:

```bash
PYTHONPATH=.:ml/pvusatov/backend/inference python -m pytest -q ml/pvusatov/experiments/v4
```

Later operating-point and association experiments are separate research. They do not alter the deployed model, thresholds or frozen FINAL evidence. The next independent synthetic association evaluation uses new reserved seeds; acquisition of twelve new native parents is explicitly incomplete after upstream IRSA502 failures. No substituted native holdout or successful live-download claim is made.
