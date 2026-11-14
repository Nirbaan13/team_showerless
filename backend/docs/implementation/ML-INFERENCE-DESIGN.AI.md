# SPHEREx server inference design

## Objective and evidence

Build a working CPU inference path from retrieved astronomical data to a ranked list of moving-source candidates for human review. This implements Paul's WhatsApp message of 2026-11-14 18:19:26 Europe/Moscow: data -> backend -> ML analysis -> list of stars, with processing located under backend/. The user allocated 15 hours starting approximately 2026-11-14 15:23 UTC.

Sources of requirements: the Space Apps Challenge WhatsApp discussion, task-distribution document, actual repository and Ivan's motion-review work. Existing main at ca63aa4145f5a539b157f8bd25c237c8cca56148 has classical detection and an offline Random Forest experiment, but no saved model or inference API. Ivan's 2b6dc435b0f73a6f255e50ca795900acfd69cd33 additionally provides FITS registration, per-frame background references, four real cases, and review output. Reuse and attribute that work; preserve ml/ and teammates' unrelated changes.

## Selected approach

Reuse the team's classical detector and astrometric track linker, and add a trained, frozen Random Forest reranker exported to ONNX. Inference never fits a model. The learned score is a ranking score, not a calibrated probability of a planet or a discovery claim. Publish the heuristic comparison and limitations; if ML does not outperform it on a given benchmark, report that result.

The alternatives are an optical-survey pretrained CNN with substantial SPHEREx domain shift, or a newly trained image CNN without sufficient native labels. Neither is a better default within the allocated time. A source-level classifier remains a future improvement; it must not be confused with the track reranker delivered here.

## Boundaries

- Scala/ZIO owns public HTTP and gRPC, job admission/persistence, observation retrieval, resource links and process supervision.
- backend/inference/ owns Python FITS preparation, candidate detection/linking, trained-model inference, review evidence and offline training/evaluation.
- Python runs as a bounded subprocess with structured JSON files. No shell interpolation, arbitrary user paths, arbitrary remote URLs, runtime training, or separate public Python port.
- Frontend offers an actual inference/review flow using API results and real evidence, without silently substituting mock objects or generated stars.
- Existing retrieval behavior, native IRSA chunk identity and old routes remain compatible. Registration is an analysis transformation and never changes cached native products.

## Python contract

Package: ml_inference, runnable with python -m ml_inference --request PATH --output DIRECTORY. Request schema_version is 1. The trusted Scala adapter supplies either a registered NPZ fixture or cached FITS paths plus a requested region/grid, immutable observation identifiers and provenance. The Python CLI must also run locally for a downloaded manifest.

An analysis requires at least three independent observations with finite, strictly increasing physical exposure midpoint times after sorting/deduplication. Group different detectors separately. For the first release, short-arc, approximately linear motion is the supported model. Sparse coverage, excessive requested work or invalid/mismatched inputs produces explicit structured errors; no fabricated candidates.

Prepare native FITS using IMAGE, FLAGS, VARIANCE, ZODI and spatial WCS. Preserve observation identity, detector, release/processing version, midpoint MJD/UTC, units and mask policy. Use a common ICRS grid for detection/review. Native input files are immutable. Default science masks exclude invalid/saturated measurements; an explicit motion policy may retain OUTLIER with per-detection warnings. A separate BLOOM-mask track is flagged evidence, not calibrated photometry or a Random Forest prediction.

Limits initially: at most 32 exposures per analysis, grids no larger than 512x512, bounded peak/candidate counts and one concurrent Python worker on the VPS. Reject oversized requests explicitly. Report any detection cap so an incomplete search cannot appear exhaustive. Bound process runtime and every output resource.

NPZ benchmark expected_xy/ephemerides are evaluation-only. Production inference must ignore them and never use target names or expected positions to locate/rank candidates. Legacy fixtures retain their recorded grid convention; newly prepared grids use explicit WCS metadata and tests for RA wrapping and axis orientation.

Output result.json is atomic and JSON-finite. It contains model ID/hash and feature schema, input provenance, selected settings, actual frame dimensions/dates/masks, candidate ICRS coordinates and per-epoch points, velocity/time units, fit residuals, heuristic and learned scores/ranks, processing/coverage warnings, and paths to PNG review evidence. Unknown scientific classification, catalog match, flux or uncertainty remains unknown. The API must not invent values required by older mock UI types.

## Model contract

Feature schema initially follows the team's six track features in this exact order: epoch_count, fit_rms_px, median_snr, min_snr, snr_coefficient_of_variation, median_peak_ratio. Keep model and detector feature computation identical. Features and class ordering are versioned. Reject non-finite or wrong-shaped features.

Freeze a model artifact, metadata/checksum, reproducible offline training command, training manifest and evaluation report. Model loading verifies the artifact digest and schema. ONNX runtime uses bounded CPU threading. Inference on an empty candidate list returns an empty result without fitting or failing.

Separate training/validation/test by entire simulated fields and parent real observation/source groups before creating injections/crops. Preserve held-out seed ranges and provenance. Do not claim unmatched real candidates are negatives. Known comet/Vesta examples are selected development/recovery cases, not a representative survey precision test. Include noise-only and artifacts-only controls and recovery before/after reranking.

## Public inference API

Add an analysis-level service, separate from per-image Processor. POST /api/analyses/motion accepts either an existing download_id or a named, explicitly documented real-data demo preset. Existing region preparation followed by analysis submission is the live-data path. A frontend helper may perform the two calls for the user.

Return 202 with an analysis ID, status URL and events URL immediately. GET /api/analyses/{id} returns durable state and final results. GET /api/analyses/{id}/events provides progress. GET /api/analyses/{id}/resources/{name} serves only allowlisted published files. GET /api/analyses/models and GET /api/analyses/presets describe the installed model and real demo inputs. Provide equivalent typed gRPC submission/status/watch interfaces; large evidence is retrieved by stable resource URLs rather than embedded in protobuf/JSON.

Jobs distinguish waiting for downloads, preparing, inferencing, completed and failed. Results must survive restart; interrupted work is recovered or explicitly failed/retryable. Admission/deduplication keys include input identities, model hash, preparation settings and algorithm version. Pin or snapshot input files for the analysis so cache eviction cannot remove in-use bytes. Release temporary inputs after completion/failure. Never expose absolute filesystem paths or arbitrary URLs supplied by a caller.

## Deployment and deliverables

A locally runnable CPU package, frozen model, real demo fixtures with provenance, CLI, automated tests, full scientific evaluation report, HTTP/OpenAPI and gRPC interfaces, frontend real-review page, and Docker/CI integration. Maintain commit-revision application versioning and existing healthy-deploy/rollback semantics. Use Python >=3.12, tested NumPy/SciPy/Astropy/ONNX Runtime versions; scientific training dependencies are separate from inference requirements.

Follow the repository PR flow; the user already authorized implementation and deployment in this session. Do not push directly into main or edit human AGENTS.md. All authored prose documentation ends .AI.md. Communicate changes through the prescribed review flow; report a connector failure honestly if WhatsApp notification is unavailable.

## Completion evidence

- Model artifact is actually loaded by CLI and deployed API; training is not invoked during inference.
- Real held-out/reference cases produce computed trajectories, coordinates and evidence; modifying expected_xy does not change inference.
- Independent simulated/injection recovery metrics, false candidate counts, ranking ablation and limitations are published; no invented real-survey precision.
- Invalid FITS, missing HDUs, duplicate times/observations, masks, empty detections, insufficient frames, large requests, model mismatch, subprocess failure and restart are verified.
- HTTP and gRPC return the same persisted results; resource paths are safe; disconnected clients do not cancel accepted work.
- Frontend uses real API data and real image evidence; browser verification exercises an actual analysis, including empty/error cases.
- Full Python/Scala/frontend checks, CI/container health/rollback and real deployed smoke checks pass before claiming delivery.
