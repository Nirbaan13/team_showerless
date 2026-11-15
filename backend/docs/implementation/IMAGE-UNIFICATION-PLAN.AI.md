# Image unification implementation plan

**Goal:** prepare downloaded astronomical images as versioned, scientifically
explicit ML data in the existing Python pipeline container, with a Scala client
and durable public jobs; submit a PR.

**Spec:** IMAGE-UNIFICATION-DESIGN.AI.md; tool comparison and primary documentation
are in IMAGE-UNIFICATION-RESEARCH.AI.md.

**Architecture:** a separate Python package performs bounded decoding and explicit
WCS registration. Scala resolves completed IDs, snapshots inputs, calls the private
operation, validates artifacts and publishes them. The original four Python routes,
frontend and frozen ML model remain unchanged.

## Shared protocol (version 1)

POST `/internal/image-unifications` accepts a JSON object:

```json
{
  "schema_version": 1,
  "job_id": "canonical UUID",
  "inputs": [{
    "id": "server identity", "path": "unifications/UUID/inputs/000.fits",
    "sha256": "64 lowercase hexadecimal characters",
    "profile": "generic",
    "image_hdu": null, "plane_indices": [],
    "metadata": {"provider": "eso", "observation_id": "native identity"}
  }],
  "grid": {"kind": "sky", "ra_degrees": 266.4, "dec_degrees": -29.0,
           "width": 64, "height": 64, "pixel_scale_arcsec": 1.0},
  "options": {"target_unit": null, "normalization": "none", "mask_policy": "science"}
}
```

Pixel mode uses `{kind:pixel,width:64,height:64}`. Profiles are `generic`,
`spherex` or `raster`; Scala derives profiles from trusted source metadata.
`image_hdu` is null, a nonnegative integer or a FITS extension name.
No arbitrary URLs, absolute paths or caller-controlled output destinations.
Output paths are fixed to `unifications/UUID/output/dataset.npz` and
`unifications/UUID/output/manifest.json`.

Successful response:

```json
{"schema_version":1,"job_id":"UUID","status":"completed",
 "bundle":{"path":"unifications/UUID/output/dataset.npz","bytes":123,"sha256":"..."},
 "manifest":{"path":"unifications/UUID/output/manifest.json","bytes":123,"sha256":"..."},
 "frame_count":3,"width":64,"height":64,"detection_ready":false,"warnings":[]}
```

Errors expose bounded `code` and `message` without filesystem paths.
Python entry `unification.worker.run_job(request: dict, root: Path) -> dict`
does all scientific work. `python -m unification.worker REQUEST_JSON` reads a
bounded request file; root is `UNIFICATION_DATA_ROOT` and prints one JSON result
to stdout. CLI returns nonzero on failure. HTTP supervises this child.
ML loader `unification.ml.load_bundle(path)` returns a validated bundle with
`images`, `tensor`, `valid_mask`, `metadata` and `.motion_inputs()` returning
`(images, times)` or a descriptive ValueError if unqualified.

## Constraints and review focus

- Inputs 1–32; target sides 1–512; source sides at most 4096; encoded and decoded
  input at most 256 MiB each; bundle 192 MiB compressed/192 MiB expanded/32 members.
- Missing times, units, masks and calibration remain unknown; preserve provenance.
- Duplicate observation identities, different bands, missing times, misleading
  unit conversions and unselected cubes must not silently become motion ML input.
- Symlink/path escapes, same-ID source replacement, oversized output, interruption
  and restart must leave no falsely completed artifact or live abandoned child.
- New numerical code is separate from the team's original service implementation.

## Task 1: numerical module and actual ML roundtrip

Owner: Python numerical worker, only `pipeline/unification` excluding
`app.py`/`http.py`, and `pipeline/tests/unification/test_numerics.py` plus helpers.

- [x] Write failing FITS, grid, variance/mask, metadata and safe-bundle tests.
- [x] Implement worker/readers/resampling/bundle/ML loader using existing scientific
  dependencies, with separate physical images and finite normalized ML tensor.
- [x] Test primary/extension/scaled/gzip/tile-compressed/cube inputs, explicit
  raster pixel mode, rotated/translated sky grids and real source times.
- [x] Export/reload an injected moving source and recover it with the actual
  `ml_inference.detector.find_candidates` consumer without model/source edits.
- [x] Verify both current real ESO/CADC downloaded files can be normalized.

## Task 2: durable Scala jobs and artifact lifecycle

Owner: Scala worker, new `spaceapps.unification` production/tests and narrow
`FitsCache` ownership extension with tests. Constructor accepts
`invoke: Json => Task[Json]` so transport is independently testable.

- [x] Write failing ID-resolution, completed-artifact, snapshot, restart and
  rejection tests using real SQLite, files and a controlled pipeline callback.
- [x] Implement `Unifications.make(jobs, archiveService, archiveRepository, cache,
  data, database, invoke)` returning a service; `UnificationApi(service).routes`.
- [x] Public POST `/api/image-unifications` takes `inputs` of
  `{kind:archive_asset|native_chunk,id,image_hdu?,plane_indices?}` plus grid/options.
  Native chunks additionally take `download_id`. Reject unknown nested properties.
- [x] GET `/api/image-unifications/{id}` reports durable queued/running/completed/
  failed state and public `artifact_url`; GET `.../{id}/artifact` streams only a
  registered complete NPZ. Missing or evicted output is explicitly unavailable.
- [x] Snapshot under capacity admission, verify source SHA, keep leases through
  bounded remote completion, atomically publish validated output, recover and
  clean inputs/staging. Count and evict final NPZ within existing cache limits.
- [x] Run new Scala tests and existing cache tests; no bootstrap/OpenAPI edits.

## Task 3: private HTTP, composition, wiring and packaging

Owner: root; `pipeline/unification/http.py`, `app.py`, HTTP tests, existing Scala
processing client/tests, Main, OpenAPI, Docker/Compose/CI and documentation.

- [x] Write failing private API tests for real worker execution, limits,
  concurrency, deadline, disconnect and child cleanup.
- [x] Supervise one child at a time, 120-second numerical deadline; paths derive
  solely from validated UUID and shared root. Await cleanup even during cancellation.
- [x] Add `HttpPipelineClient.unify(Json): Task[Json]` through the bounded existing
  transport; wire the durable service and additive public routes in Main.
- [x] Copy package into current image and compose `unification.app:app` without
  modifying the original Python service; add unification tests to CI.
- [x] Document actual public/private schemas, scientific limits, artifact loader
  usage, runtime mounts and pipeline compatibility.

## Task 4: integration, independent review and PR

- [x] Full Scala test/stage; original Python pipeline tests and unification tests;
  frozen inference suite; YAML/OpenAPI validation and shell/deployment checks.
- [x] Real Scala -> Python HTTP -> exported artifact -> ML loader smoke.
- [x] Inspect complete diff for frontend/original science/frozen-model changes.
- [x] Independent whole-branch review and fixes with regression tests.
- [x] Push feature branch, create PR with truthful validation and limitations;
  inspect CI/container results. Do not merge or deploy without a separate request.

Baseline: `./sbtw test stage` on main 44cc7e3: 185 passed, zero failures,
three ignored, 2026-11-15. Research and design are present in this directory.
