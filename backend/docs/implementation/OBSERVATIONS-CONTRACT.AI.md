# Common observations contract correction

The contract separates metadata discovery from selected-image downloading. `GET /api/observations-search` returns a list of observations and persists their stable backend IDs. `POST /api/observations-download` accepts only the IDs selected by the client (`observation_ids`) plus optional delivery settings. Download acceptance and execution must never invoke discovery, add other observations, or replace the selection with all matching images.

The download response uses the legacy contract's common fields: id, status, mode, query, observations, chunks, progress, status_url, events_url and errors. Chunks include frame_id, status, preview_status, image_url and fits_cutout_url. Source-specific detector_array/channel_index filters are excluded. Missing observation times, releases and wavelengths remain absent. Native source metadata is retained.

Canonical status/events/chunk routes use `/api/observations-download/{id}`, `/api/observations-download/{id}/events`, and `/api/observations-download/chunks/{id}`. Existing IRSA routes and the previous raw archive routes remain compatibility interfaces; no frontend/Python/ML client migration is included. The existing circle, shared LRU, leases, provider resolution and download workers are reused.

## Implementation and validation

- [x] Regression tests: GET search returns observations without downloading; POST accepts an exact subset and never searches; body geometry/unknown IDs/IRSA-only filters are rejected; common manifests, pending links and SSE are consistent.
- [x] Add common query parser and response mapping; expose the two agreed routes and their status/resource endpoints.
- [x] Update OpenAPI with matching parameters, schemas and examples. Mark former archive workflow routes as compatibility routes.
- [ ] Run the complete backend suite/staging and review the change; push into PR18, await CI, merge after checks, and verify main deployment.

Merge into main was explicitly authorized by the user after fixing this contract.

## Verification ledger

- New endpoint tests initially failed because the routes were absent. GET now returns observations directly and creates no download; POST rejects geometry, accepts a strict selected subset and issues no discovery call during acceptance or execution.
- Canonical manifests retain common legacy job/chunk fields. A live subscriber receives compact chunk.ready payloads with job_id/chunk_id/progress; pending FITS URLs return 202 and later return the actual validated bytes. Native preview absence is explicit.
- An alias regression caught product version being mislabeled as a data release; release now comes only from explicitly named source metadata. Verified UTC dates are exposed only when verified, and native metadata remains intact.
