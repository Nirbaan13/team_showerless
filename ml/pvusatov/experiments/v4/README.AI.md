# V4 inference quality study — work in progress

This study continues the user's full-time ML task. It does not replace the deployed, independently tested C13/v3 release. The original v3 graph, source and final artifacts remain immutable. All work belongs to `ml/pvusatov/`; unrelated teammate services and interfaces stay under their existing ownership.

The prospective method and frozen seed reservations are in [protocol.json](protocol.json), execution plan in [IMPLEMENTATION-PLAN.AI.md](IMPLEMENTATION-PLAN.AI.md), and current handoff in [STATE.AI.md](STATE.AI.md). Research continues until 2026-11-15 12:50 UTC / 15:50 Moscow; an early successful milestone does not complete this resumed task.

The first completed acquisition consists of 8 new TRAIN, 8 new development-validation and 12 quarantined FINAL parent fields, each with eight physical SPHEREx observations. The complete source selection is reproducible from archived official queries and excludes every prior physical observation. Source image bytes remain outside git; checksums, acquisition evidence and independent injection/variance engineering checks are in `data/`. FINAL pixels have not been opened for inference and no final authorization exists in this checkpoint.

`detection/` contains the measured 30-feature contract, bounded inference-only ONNX loader, development diagnostics and separately typed detection experiments. `ranker/` contains objective/weighting ablations, grouped fitting, graph export and parity checks. `evaluation/` contains source-bound development generation and prospective freeze/evaluation tools still under construction. Reports distinguish selection evidence from independent evaluation and preserve failed approaches.

The source-history directories preserve exact earlier research versions and failure evidence. They are not alternative production modules. Native pilot/main-v1 caches were excluded after an importer source-binding risk was reproduced; safe main-v2 compiles exactly the checked source bytes. No native UNKNOWN controls are negative training labels. Ranking scores are not calibrated object probabilities.

Run the portable tool tests from repository root in the existing scientific environment:

```bash
PYTHONPATH=.:ml/pvusatov/backend/inference python -m pytest -q ml/pvusatov/experiments/v4
```

No study script implicitly selects or opens FINAL data. The future root-authorized paired run must bind a single development-selected model, exact source closure, inputs and seed maps before any FINAL reader, and must pass scientific, resource and actual integration gates before deployment.
