# Running SPHEREx motion inference

The analysis service prepares real observations, detects approximately linear tracks and loads a frozen ONNX Random Forest to rank them for human review. It does not train during a request. The score is an experimental ranking value, not a calibrated probability of a real object, a planet or a discovery. See the model evaluation report for synthetic, selected real-object and independent real-background results.

The public Scala service owns admission, persistence and resource URLs. Python is a supervised CPU subprocess; it has no additional public port. Existing native FITS retrieval stays unchanged.

## Local Python CLI

Use Python3.12 or later in an existing environment, then install the hash-locked runtime requirements. Training requirements are separate.

```bash
cd ml/pvusatov/backend/inference
python -m pip install --require-hashes -r requirements-inference.txt
python smoke.py
```

`smoke.py` starts a real analysis of four archived exposures, verifies the installed model digest, and checks that published image resources exist. It needs no live IRSA connection and never uses expected coordinates to detect or rank tracks.

A normal CLI request is:

```json
{
  "schema_version": 1,
  "analysis_id": "local-review",
  "source": {"kind": "preset", "preset_id": "comet-d6"},
  "options": {"mask_policy": "motion"}
}
```

```bash
python -m ml_inference --request request.json --output /tmp/spherex-review
```

The worker atomically publishes `result.json` and flat PNG evidence files. The output directory should be dedicated to one analysis. On a scientific/validation failure it writes a structured error result and exits2; it never substitutes simulated stars. The packaged presets contain actual archived SPHEREx pixels and explicitly identify their provenance. They are selected known-object recovery cases, not representative survey test data.

For native input, replace source with:

```json
{
  "kind": "fits",
  "observations": [
    {"frame_id": "product-1", "path": "/data/observation-1.fits"},
    {"frame_id": "product-2", "path": "/data/observation-2.fits"},
    {"frame_id": "product-3", "path": "/data/observation-3.fits"}
  ],
  "region": {
    "right_ascension_deg": 127.69444,
    "declination_deg": -39.17760,
    "width_arcmin": 3,
    "height_arcmin": 3
  }
}
```

These are trusted local CLI paths. Public HTTP/gRPC callers cannot supply filesystem paths. Optional trusted manifest fields `release`, `processing_version` and `access_url` preserve archive provenance; the worker reads physical observation identity and midpoint from FITS and computes input SHA-256. Software `VERSION` remains separate from the archive product version.

## Server API

Run the Scala launcher from `backend/` using `./sbtw run`. Its local `ML_ROOT` default is `../ml/pvusatov/backend/inference`; `ML_PYTHON` selects the existing Python environment containing the runtime requirements. An explicit `ML_ROOT` overrides that local default for an installed runtime.

With the Scala service running, get its installed model and available real presets:

```bash
curl http://localhost:8000/api/analyses/models
curl http://localhost:8000/api/analyses/presets
```

Submit a real-data example:

```bash
curl -X POST http://localhost:8000/api/analyses/motion \
  -H 'Content-Type: application/json' \
  -d '{"preset":"comet-d6","options":{"mask_policy":"motion"}}'
```

The response is HTTP202 with `id`, `status_url` and `events_url`. Poll status or use the SSE stream:

```bash
curl http://localhost:8000/api/analyses/ANALYSIS_ID
curl -N http://localhost:8000/api/analyses/ANALYSIS_ID/events
```

A completed result contains actual frames, candidate tracks, model identity/hash, heuristic comparison, processing settings, provenance and quality warnings. Its PNG links are served by the same Scala backend. The frontend review page is `/?analysis=1`; a shareable analysis URL also includes `id=ANALYSIS_ID`.

For live input, first submit an existing native preparation query (`observations/default`, `range`, `polygon` or the deep-survey equivalent), then:

```bash
curl -X POST http://localhost:8000/api/analyses/motion \
  -H 'Content-Type: application/json' \
  -d '{"download_id":"DOWNLOAD_ID"}'
```

The task waits for that download. Only native default-mode FITS inputs are accepted, to avoid applying zodiacal subtraction twice. A failed unrelated retrieval preview does not prevent analysis when all native FITS are ready. A missing native input produces an explicit error; there is no silently incomplete analysis.

The initial workload bounds are32frames, one detector per analysis, a grid up to512×512, one concurrent worker and a bounded queue. Large regions must be reduced or use a supported larger pixel scale. Peak/candidate truncation is explicitly reported as incomplete coverage. Speed settings are in arcseconds per physical hour, using FITS exposure midpoints rather than frame indices.

## gRPC

The same persisted jobs are available through `spaceapps.retrieval.v1.AnalysisService`: `SubmitAnalysis`, `GetAnalysis`, `WatchAnalysis`, `GetModels` and `GetPresets`. The service uses the existing private gRPC listener. Result image links remain HTTP resource URLs.

Use the checked-in `ml/pvusatov/backend/src/main/protobuf/spaceapps/retrieval/v1/analysis.proto`, which imports shared retrieval types from `backend/src/main/protobuf/spaceapps/retrieval/v1/retrieval.proto`. Both protobuf source roots are needed. The ScalaPB custom-option import also requires the corresponding `scalapb.proto` include file when invoking standalone protoc/grpcurl; sbt resolves it during code generation. For generated applications, use the descriptor and dependencies emitted by the normal protobuf toolchain. The public `spaceapps.retrieval.v1.AnalysisService` wire name and existing retrieval service remain unchanged.

After the normal sbt code-generation step, grpcurl can use the resolved imports:

```bash
cd backend
./sbtw compile
grpcurl -plaintext \
  -import-path src/main/protobuf \
  -import-path ../ml/pvusatov/backend/src/main/protobuf \
  -import-path target/protobuf_external \
  -proto spaceapps/retrieval/v1/analysis.proto \
  -d '{"preset":"comet-d6"}' \
  127.0.0.1:50051 spaceapps.retrieval.v1.AnalysisService/SubmitAnalysis
```

## Container/runtime configuration

The container bundles the Python runtime, inference source, frozen model and small real fixtures. Offline training code, scikit-learn and the source calibration archive are not required for a request.

| Variable | Purpose |
| --- | --- |
| `ML_ROOT` | Installed inference directory, normally `/app/inference` |
| `ML_PYTHON` | Runtime interpreter, normally `/opt/inference-venv/bin/python` |
| `DATA_DIR` | Shared managed storage for native data, analysis jobs and results |
| `APP_REVISION` | Git revision, also reported by the existing `/version` endpoint |

CPU math/ONNX threading is bounded. Accepted jobs persist independently of browser connections. Interrupted active children fail explicitly and are retryable; waiting/queued work is recovered. Model ID/hash are fixed when a task is admitted and checked on publication. Native input leases/snapshots protect in-use bytes against cache eviction.

To run scientific tests and reproduce training, use `requirements-training.txt` in place of the runtime lock and follow `ML-MODEL-EVALUATION.AI.md`. Keep training/validation/test partitions and the declared held-out protocol intact; selected real examples and already inspected development fields cannot become fresh independent tests again.
