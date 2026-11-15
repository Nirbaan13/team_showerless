# SPHEREx server inference implementation plan

> Execution: implement independent modules in this session with explicit ownership, test each module and perform independent review before integration/merge.

**Goal:** Provide real CPU model inference from retrieved SPHEREx frames to ranked, reviewable moving-source candidates.

**Architecture:** Scala owns durable analysis jobs and APIs. A supervised Python CLI prepares FITS and runs a frozen ONNX Random Forest on detected tracks. Real review data flows into a dedicated frontend view.

**Tech Stack:** Existing Scala/ZIO/SQLite/gRPC; Python >=3.12, NumPy, SciPy, Astropy, ONNX Runtime; scikit-learn/skl2onnx for offline training; existing React/Vite frontend.

**Spec:** ML-INFERENCE-DESIGN.AI.md.

## Global constraints

Preserve native retrieval chunks, existing routes, human AGENTS.md, teammates' files and main's ml/. One concurrent analysis worker, at most32 frames and512x512 grids initially. Explicit workload/coverage errors; finite JSON; no training or expected-position use at inference. Frozen artifact/checksum, real provenance and honest ML/heuristic comparisons. Generated prose uses .AI.md. Follow PR review and existing main CI deployment.

## Review focus

- Alternative processing versions/duplicate midpoints must not count as independent detections.
- Cache eviction and server restart must not silently lose accepted inputs/results.
- FITS WCS orientation, RA wrap and masks must preserve physical coordinates and missing coverage.
- A detector cap, incompatible passbands or synthetic-trained score must not appear as an exhaustive or calibrated discovery result.
- A model with no quality gain must remain visibly experimental; no hardcoded demo ranks/ephemerides or mock UI fallback.

## Task1: Scientific Python inference core

Own backend/inference/ml_inference/{contracts,detector,prepare,pipeline,cli,__main__,render}.py, scientific fixtures/provenance and tests excluding model tests. Reuse/adapt Ivan's pinned branch with attribution. Establish shared request/output contracts before integrating callers. Write failing tests for real fixture inference without ephemerides, finite empty results, validation, WCS/masks and resource bounds. Implement detection/registration/review evidence and atomic outputs. Run the Python suite and record actual real-case recovery.

## Task2: Frozen model and evaluation

Own backend/inference/ml_inference/model.py, backend/inference/training/, backend/inference/models/, model tests and model/evaluation .AI.md docs. Model API: load_ranker(model_dir:Path)->Ranker with metadata and score(features:array[N,6])->array[N]. Pin feature names/order from the spec. Test correct schema/hash/classes, no training on load, empty/nonfinite input, ONNX/sklearn parity. Train with reproducible disjoint field partitions, publish frozen artifact plus ablations and actual limitations. Keep real known-object fixtures out of training and distinguish unlabeled candidates from negatives. Add stronger real-background injection tests where data permits.

## Task3: Durable Scala integration and gRPC

Own backend Scala analysis domain/repository/service/controller, bootstrap integration, protobuf/gRPC analysis changes and corresponding Scala tests. Add job-level analysis over download_id and explicit real presets. Call Python via argument-vector ProcessBuilder with trusted manifest/output paths, bounded stdout/stderr/runtime and cleanup. Persist/deduplicate/recover work; pin input files; expose state/events/allowlisted resources. Verify errors, output bounds, safe paths, process failures, persistence/restart and typed HTTP/gRPC parity. Do not modify existing native retrieval semantics.

## Task4: Packaging, OpenAPI and runnable demo

Own backend/inference dependency/packaging files, Dockerfile, workflows, ops changes and OpenAPI analysis operations. Pin inference dependencies separately from training. Include installed model and small provenance-tagged real fixtures. Ensure Docker runs Python as existing uid10001 with bounded CPU threads and writable data outputs. Add Python tests and actual model CLI smoke to CI, keep existing rollback/current-and-legacy Compose checks. Document one-command local execution and real-data HTTP/gRPC examples.

## Task5: Real frontend review

Own new frontend inference client/types/page and minimal App/navigation wiring. Show submitted query/preset, actual job progress, real frames, per-epoch detections, ML score and heuristic rank with limitations. Never cast computed output into mock types by fabricating flux/classification. Match points by epoch ID and dynamic image dimensions; display errors and empty candidates. Link native FITS/provenance and export JSON. Browser-test a real backend analysis; preserve teammates' existing views.

## Task6: Whole-system verification and delivery

Run all scientific/Scala/frontend tests, independent code/science review and realistic resource/runtime measurements. Verify trained-model artifact is loaded on VPS, actual HTTP/gRPC results and frontend review reflect computed outputs, and input label changes cannot affect inference. Publish the evaluation/limitations report, PR and deployed URLs using the authorized repository flow. Audit every completion item in the design; leave the goal active if any required deliverable remains unverified.
