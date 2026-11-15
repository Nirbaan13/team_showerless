# Downloads module refactor

## Approved task and scope

Move all legacy image retrieval implementation into `irsa`. Rename the federated `archive` module to `downloads`, preserving controller → service → repository boundaries and external integrations. Give downloads the existing asynchronous pipeline guarantees: immediate acceptance, pending artifact links, persistent progress/SSE, recovery, shared caching, and reader leases. Keep circle coordinates in degrees. Apply one persistent LRU policy to every downloaded/generated file type, including calibration equipment files and PNG previews.

Client migration is a separate PR. Preserve current HTTP and gRPC wire contracts and existing SQLite tables/cache identities. Do not edit frontend, Python, ML implementations, or the human-maintained AGENTS.md. Compatibility exports may preserve Scala clients without retaining duplicate legacy implementations. Read current WhatsApp decisions; notify the group after opening the PR as the local backend instructions require.

## Design

- `irsa/{controller,service,repository,model,integrations}` owns legacy retrieval, metadata, SIA/IBE, and retrieval gRPC implementation. Generated protobuf packages remain wire compatible.
- `downloads/{controller,service,repository,model,integrations}` owns federated discovery and downloads. Keep existing public archive URLs for this PR. Add `/api/archive-downloads/{id}/events`; accepted jobs advertise that URL. Each selected record has a pending chunk and future artifact URL. Persist events in the same SQLite transaction as manifests, with monotonic sequence IDs, reconnect replay, a current snapshot, and a terminal event.
- `infra` owns shared file caching and application bootstrap/support. Track raw FITS, prepared FITS, PNG, native archive products, and calibration files in one LRU index. SQLite administrative files are excluded; unrelated user files are counted but never deleted. Atomic publication, temporary reservations, processing/streaming reader leases, and durable last-access order apply uniformly.
- `equipment` owns calibration integration and service. Inject the same cache instance used by both retrieval modules. Use the known calibration size for admission; do not validate YAML/ECSV as science FITS. Both HTTP and gRPC hold a reader lease until their streams close.
- `processing` contains the existing HTTP pipeline proxy. No processing behavior or Python code changes.
- Keep thin root package exports used by the separately owned ML client. No duplicated jobs, repository, cache, or downloader implementation remains there.

## Verification and implementation plan

### Task 1: Shared eviction behavior

- [x] Add regressions proving cross-type eviction, persistent access ordering, and leased-file protection for archive/calibration/preview files.
- [x] Observe failures with the original FITS-only cache, then move cache/store into infra and support all managed products.
- [x] Route native publication through the coordinator, preserving gzip scratch reservations and atomic validation/publication.
- [x] Route equipment publication and HTTP/gRPC streams through the same coordinator. Verify first miss, hit, eviction, redownload, limits, and cancellation.

### Task 2: Module ownership

- [x] Move legacy retrieval into irsa, archive into downloads, calibration into equipment, processing proxy into processing, and bootstrap/cache/FITS support into infra.
- [x] Rewrite backend imports/tests; keep only necessary compatibility exports for separately owned ML clients. Preserve old wire routes, SQLite tables, hashes, and protobuf namespaces.
- [x] Run the complete Scala suite and stage; check no frontend/Python/ML source changes.

### Task 3: Download pipeline

- [x] Add regressions for immediate pending chunks, pending resources, durable progress and SSE replay, terminal stream completion, recoverable jobs, cache hits, eviction/redownload, and live HTTP streaming leases.
- [x] Persist download events atomically with state; recover existing rows and running jobs without replaying already successful outcomes.
- [x] Add events/progress/pending artifact responses, bounded concurrent work and transfer deduplication, current cache validation, and sanitized errors.
- [x] Reuse legacy IRSA spatial selection in the federated provider so circle cutouts follow the existing IBE behavior.
- [x] Document additive contract changes in OpenAPI and update implementation notes.

### Task 4: Delivery

- [ ] Run full tests/staging, independently review the final diff, and address material findings.
- [ ] Open a PR for backend review (do not merge this unreviewed refactor). Send a concise WhatsApp update with the PR link and client migration boundary.

## Review focus

- A client disconnect or unconsumed response must release its lease; a slow active stream must survive concurrent eviction.
- A cache hit must update persistent access order; a stale manifest must never report an evicted file as downloadable.
- Startup with old manifests and existing cache files must retain IDs and recover work without duplicate outcomes.
- Concurrent workers selecting the same product must not download or publish it twice, and all temporary reservations must be released on failure/interruption.
- An SSE reconnect during a state update must neither miss committed events nor wait forever after completion; unknown IDs fail before streaming starts.

## Context

WhatsApp read on 2026-11-15: the team reports the original pipeline integrated in frontend, and the latest archive announcement explicitly plans common download logic and later client-call migration. Image format unification belongs to the Python pipeline and is outside this refactor.

## Execution ledger

- Baseline: `./sbtw test` on main 44cc7e3: 185 passed, 0 failed, 3 optional live tests ignored.
- Cache regressions first failed for cross-format eviction, equipment leases, and calibration redownload. After the shared coordinator change, the cache/equipment suite passed 30/30.
- Pipeline regressions first failed for missing pending links, missing SSE routes, and stale successful manifests after file eviction.
- Module migration plus initial pipeline implementation: full suite passed 191 tests, 0 failed, 3 ignored. Existing ML tests ran without any edits to ML source; compatibility factories bridge its package-private HTTP/gRPC implementations.
- Decision: public archive/IRSA URLs and generated protobuf namespaces stay unchanged in this PR, because client migration is explicitly a separate task. The module and implementation names change now.

- Extended verification: a 305-event replay exposed and fixed a pagination loss; SQLite reopen, live subscription, recovery, concurrent same-product jobs and HTTP artifact leases are covered.
- IRSA provider cutout regression failed with unsupported_cutout, then passed using the existing spatial selector. Circle geometry and original-mode URLs are preserved.
- Retry regression failed after HTTP 503 without retry, then passed after bounded retries and scratch-capacity release were restored.
- Final pre-review `./sbtw test stage`: 199 passed, 0 failed, 3 optional live tests ignored; stage succeeded. HTTP calibration leases are covered alongside cache/equipment redownload and all prior ML/HTTP/gRPC tests.
