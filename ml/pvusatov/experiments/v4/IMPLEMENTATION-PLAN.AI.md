# V4 inference quality implementation plan

> Agentic execution: parallel data, detector and ranker owners; root owns evaluation, review and release. The user explicitly requested completing the full 15 hours rather than stopping after deployment.

**Goal:** Improve the existing experimental inference with honest independent evidence while preserving the deployed v3 and all frozen historical results.

**Architecture:** First isolate the effect of the learning objective and observable physical features on the same sigma-0.8 proposals. Select one development winner against the strong deployed C13 baseline, then evaluate it once on new independent native parents and synthetic seeds. A changed detector is a separately reported development ablation and may enter selection only before the final freeze.

**Stack:** Existing hash-locked NumPy, SciPy, Astropy, scikit-learn and ONNX Runtime; CPU inference. All implementation and reports stay under `ml/pvusatov/`.

**Spec:** `protocol.json`, initially recorded before any new native injection cache; acquisition uses the separately preregistered `data/partition-plan.json` and exact archived query evidence. The active-work deadline is 2026-11-15 12:50 UTC / 15:50 Moscow; the stopped interval is excluded.

## Constraints and review focus

- V3 graph, source closure, metadata and final artifacts remain immutable. Old FINAL is neither independent V4 validation nor a source of training/selection labels.
- Parent fields and physical observations remain disjoint. Correlated injected derivatives never become independent sample counts.
- Unknown real tracks remain UNKNOWN; only attributable injected stationary artifacts can be known native negatives.
- Image-only feature extraction receives measured candidates, never truth coordinates or ephemerides. Missing mission masks are represented truthfully and direct availability indicators are excluded from the default learned feature subset.
- Keep all planned coverage failures in primary accounting. Report finite-center and resolved-motion diagnostics separately. Geometric eligibility is a necessary condition, not guaranteed detection.
- Keep the same K1/K3 review budget, preserve unscored BLOOM evidence, and report candidate/CPU burden alongside recovery.
- Bind source, feature order/subset, graph, metadata, raw data, seed maps and simulator before root opens the new FINAL. No final-informed alternate selection.
- Bound meaningful maximum-shape inference as well as small fixtures; one-CPU/one-GiB VPS evidence and actual HTTP/gRPC/PNG/UI/Swagger are required for promotion.

## Tasks and ownership

### 1. Establish clean baseline and independent data

- [x] Root starts `feat/ml-v4-quality` from current main; existing 165 scientific/experimental tests pass.
- [x] Data owner preregisters 8 new TRAIN, 8 new DEV-validation and 12 new quarantined FINAL parents before archive queries/pixels.
- [x] Archive and replay the exact SIA/VOTable evidence; audit sky separation and exclusion of all 210 prior physical observations.
- [ ] Acquire all selected eight-epoch cutouts, retrying the same transiently failed URLs; publish complete DEV handoffs and root-only quarantine provenance.
- [ ] Finish independent integrity audit before any final authorization.

### 2. Measure the failure and add physical evidence

Files: `detection/features.py`, its focused tests, and `detection/results/`.

- [x] Reproduce the D6 regression on existing DEVELOPMENT fixtures and compare measured target/competitor evidence without fitting on their expected coordinates.
- [x] Implement the 30-column measured contract, keeping the original six columns exact.
- [x] Test controlled motion, shape/support, empty and malformed cases; stream epoch fit maps instead of retaining sixteen full cubes.
- [x] Measure actual maximum 32x512x512 input with nonempty tracks and reserve model memory.
- [ ] Independently review feature semantics and cohort/domain shortcuts before selection.

### 3. Generate group-aware training and compare learning objectives

Files: root `evaluation/cache_native.py`, `evaluation/geometry.py`; ranker owner `ranker/**`.

- [x] Test-first guards reject FINAL inputs before a pixel reader, reject corrupt manifests, preserve UNKNOWN competitors and distinguish coverage from resolved span.
- [ ] Root generates new native moving and stationary caches, with immutable measured source contracts and per-parent identities.
- [ ] Ranker generates reserved 5,000 synthetic TRAIN and 1,000 DEV fields; compare C13, balanced six-feature and richer physical-feature models.
- [ ] Report every candidate, weighting/seed ablation, class-conditional domain audit and per-parent recovery. Choose once using DEV, never old/new final outcomes.

### 4. Freeze and evaluate one winner independently

Files: root `evaluation/freeze.py`, guarded runners, paired metrics and portable audit; selection artifacts under `ranker/`.

- [ ] Build externally anchored source/model/feature/data/seed freeze and test rejection of unauthorized, incomplete or changed inputs before science.
- [ ] Independently review the exact freeze and native observation map.
- [ ] Run selected candidate versus C13 on all 12 new native parents and 3,000 new synthetic fields; wait for both complete runs before reading aggregate outcomes.
- [ ] Recompute all-planned/common-attributable K1/K3, parent/field bootstrap intervals, coverage, workload, caps and errors; obtain independent recount.
- [ ] Retain v3 if any preregistered recovery/resource/integration gate fails; publish negative evidence without selecting another model on the same final.

### 5. Integrate an eligible release and use the remaining research time

- [ ] Freeze an eligible runtime/model package under a new release directory, preserving all earlier versions and negative evidence.
- [ ] Run appropriate tests and exact-image/rollback CI; merge through PR and verify actual VPS model/source/revision/latest tags and durable results.
- [ ] Continue useful independent robustness, realism, photometry, resource and failure audits through the agreed deadline even if a release milestone finishes earlier. Do not turn post-final diagnostics into undisclosed model retuning.

Progress reports must distinguish selection results from independent results, and useful research from CI waiting. The deliverable is better-supported inference, not a filled timer or another deployment checklist.
