# V2 pre-test evaluation accounting amendment

The selected v2 model was frozen at 2026-11-14 16:39:45 UTC with SHA-256 `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9`. Before opening any pixels in the reserved real observation group, an independent code audit found two evaluation-report gaps: recovery numerators did not have a separately reported finite-center-coverage subset, and a trial spatially matching an already present control track could count as injection recovery.

The accounting-only correction was frozen at 16:41:55 UTC, before the final real-field run. Each cohort now records all planned injections, attribution-eligible trials, ambiguous preexisting matches, raw spatial matches, and attributable detection/retention at one and three reviews. A separate cohort contains trials with at least three finite-center epochs. Preexisting control matches are excluded from attributable recovery. The unmodified control stays scientifically unlabeled.

No model weights, measured features, detector, injection response, source placement, training partition or model-selection decision changed. The original evaluator bytes are retained in `backend/inference/training/archive_v2/evaluate_background.py`. Two new regression tests failed against the old accounting; all eight background-evaluation tests passed after correction, including the independent rotated/masked native-image forward-consistency test.

The original `freeze.json` remains unchanged. `pretest-accounting-amendment.json` records its digest, the original and amended evaluator digests, all imported production/training source digests and the regression-test digest. Amended evaluator SHA-256: `37db87a3e7a9630296867a1ae943578fbb15965edd4f948d68a32e6ef4f40d15`; combined code SHA-256: `8b8bbf038c1f770a3228370c357a0eff13e24e917e5482b2197905cbe06234f3`.

The final synthetic evaluation had already started against the unchanged frozen synthetic evaluator and model. The real-background accounting correction does not affect synthetic generation, unique-object recovery or the paired whole-field bootstrap.
