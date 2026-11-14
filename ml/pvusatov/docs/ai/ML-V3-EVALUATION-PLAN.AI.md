# V3 paired evaluation implementation plan

> For the root implementer: execute inline with test-driven development. The three child agents keep their existing ownership.

**Goal:** Independently summarize frozen v2/v3 paired trial caches with correct review budgets, attribution denominators and parent-level uncertainty.

**Architecture:** A data-only evaluator consumes already-scored cached trials and never reads images, fits models or selects candidates. A separate root invocation supplies ONNX scores after freeze. Trial identities and shared latent inputs must agree before aggregation. Native derivatives are clustered by parent and synthetic trials by independent field.

**Tech stack:** Existing Python/NumPy/pytest environment, no additional dependencies.

**Spec:** `docs/ai/ML-V3-COORDINATION.AI.md`.

## Constraints and review focus

- Own only `backend/inference/experiments/v3_evaluation/`; do not change agent files or frozen releases.
- Missing/duplicate trials must fail rather than silently intersect two systems' successful outputs.
- Preexisting matches are excluded from both systems' common-attributable denominator while all-planned metrics remain visible.
- Multiple candidates matching the same injected source count only once within a review budget; score ties retain detector order.
- Hundreds of derivatives from one native parent must not outweigh a parent with fewer derivatives in macro recovery or uncertainty.
- Empty detections, zero-truth controls and non-finite/misaligned scores must have explicit, verified behavior.

## Task 1: Paired trial accounting

Files: create `paired.py`, test `test_paired.py` in the owned directory. Interface `paired_report(baseline_fields, candidate_fields, baseline_scores, candidate_scores, bootstrap_samples=10000, bootstrap_seed=20261114) -> dict`. Scores are sequences aligned with their corresponding field sequences.

- [ ] Write failing tests for unique-truth K1/K3 with ties, complete pairing, native control ambiguity, score validity and zero detections.
- [ ] Run those tests and verify the missing implementation fails.
- [ ] Implement deterministic trial validation, all-planned and common-attributable counts, finite-center coverage and group macro recovery.
- [ ] Verify tests pass.

## Task 2: Parent uncertainty and final gate

Interface `promotion_gate(synthetic_report, native_report) -> dict`, consuming the primary paired reports and returning pass/reasons without selecting between models. Report paired mean deltas and percentile intervals by resampling independent groups only.

- [ ] Write failing tests proving 100 derivatives from one parent have equal macro weight to one derivative from another, reproducible cluster bootstrap, and rejection of either-budget regression.
- [ ] Implement group bootstrap and the preregistered no-regression/positive-improvement gate.
- [ ] Run experimental tests and the inference package suite; retain output evidence.
- [ ] Obtain a read-only independent review when the acquisition worker becomes available, before final freeze/access.

No final data are generated or opened by these tasks. Code hashes join the eventual complete freeze record.
