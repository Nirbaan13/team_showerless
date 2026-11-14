# IRSA retrieval service implementation plan

Goal: implement the current ten OpenAPI operations and open a PR against main for human review. Do not merge or deploy the branch. The local human-written backend/AGENTS.md also requires Scala/ZIO, SQLite, native IRSA image chunks and WhatsApp notification.

Architecture: JDK25 / Scala3.9 / ZIO2.1.27 / ZIO HTTP3.11.6 / zio-json1.1.2 / SQLite JDBC3.54.1.0. Serve the authoritative checked-in OpenAPI rather than regenerate an incompatible contract. Application-scoped workers discover and retrieve native products. SQLite snapshots and events survive restart. Atomically published files are streamed outside the heap. Scientific processing and PNG preview are explicitly deferred per the user clarification. NoProcessing marks preview unavailable without failing native retrieval; subtraction routes return an explicit501. Configured channel wavelengths filter native products through IRSA BAND without extracting pixels.

## Scope and interfaces

- Domain.scala: DTOs exactly matching OpenAPI, validated center/range/polygon inputs including the public spelling verices_degrees; stable request identity; ICRS region-to-SIA conversion. No image reprojection or custom tile dimensions.
- Archive.scala: trait Archive.search(query: Query): Task[List[ArchiveImage]] and fetch(image: ArchiveImage, destination: Path): Task[Unit]. Metadata-only SIA search, DR1/QR3, detector/time/channel-band filters, overflow detection, bounded streams, trusted product URLs and transient retries.
- Repository.scala: SQLite jobs/chunks/events with transactional deduplication, conditional job claims, durable manifests/events, reset interrupted jobs on startup. Trait boundaries stay small and testable.
- Jobs.scala: application-owned workers, bounded admission and parallel transfers, file publication, cached raw products, terminal preview states, errors and SSE snapshot/replay. Processing mode participates in identity. Metadata lookup validates epoch references.
- NoProcessing.scala: explicit disabled processing capability; no scientific algorithm or external processing command is implemented.
- Api.scala / Main.scala: all ten contract paths, 422 JSON validation errors, 202/200 jobs, pending/failed/missing resources, snapshot-first SSE, health/version/OpenAPI/Swagger. Request disconnects cannot cancel workers.
- Build, container and CI: sbt1.13.1, JDK25, immutable revision, persistent data volume, native access, tests/build on PR; existing main-only health-checked deployment/latest behavior retained.

## Execution

1. Write domain and archive tests; observe failure; implement validation and SIA decoding/streaming; verify exact geometry, overflow and invalid upstream responses.
2. Write persistence/job tests; observe failure; implement deduplication, restart recovery, download lifecycle, processing failure and terminal events; verify that chunk URLs are stable and one product yields one chunk.
3. Write HTTP integration tests; observe failure; implement routes, files and SSE. Verify all paths, malformed inputs, cache reuse, unavailable/failed previews, missing references and non-cancellation.
4. Replace the Python bootstrap build/container with the Scala application; retain health/version/revision semantics and deployment rollback checks; add contract parity checks and operational instructions.
5. Run full tests, real local HTTP and upstream metadata smoke tests, independent code review and fixes. Open a PR against main, retain the branch for human review and notify the team according to AGENTS.md.

## Review focus

- Sphere boundaries: RA wrap, polar centers, non-convex/self-crossing/degenerate polygons, NaN/infinity and malformed filters must not become plausible archive queries.
- Archive truncation/error documents, false FITS bodies, partial downloads and native-product identity must not produce successful manifests.
- Deduplication and file/DB publication during process restart must not lose accepted work or announce absent bytes as ready.
- Slow/reconnecting SSE clients must recover state without stalling worker completion; preview failures count toward terminal completion.
- Processing capabilities are external dependencies. Missing pipeline or channel calibration must be explicit, documented and tested, not replaced with scientifically incorrect data.

## Execution ledger

- Base: origin/main 69b2b3c; latest contract includes range and polygon (5e29a49).
- Native managed worktree tool targets the outer personal repository. Service work is isolated with a manual linked worktree of team_showerless at /home/usatovpavel/.codex/worktrees/spaceapps-zio-backend; original dirty human AGENTS.md is untouched.
- User has authorized implementation and PR creation. Design follows the already selected stack and the current contract; no repeated authorization gates.
- Public API processing integration details requested asynchronously while independent retrieval work proceeds.

- User clarification: no Python pipeline exists yet. PNG preview and both subtraction modes are explicitly deferred. Default/range/polygon jobs retrieve native FITS and complete with preview_status=unavailable; no scientific implementation or fabricated preview. Channel calibration is configurable; requests without a configured authoritative mapping are rejected explicitly.

- Domain TDD: initial missing Query, then5green; strict JSON type/duplicate regression observed red and fixed. Archive red againststub, then11green including partial cleanup. Jobs red then12green including concurrency, replay and disabled previews. API red then4green. Capacity red then1green. Latest integrated result:34tests,0failures, staging successful.
- Build/deployment: replaced obsolete Python bootstrap, retained revision/latest/rollback flow, added durable Docker volume and compatibility test for existing VPS Compose. No main push or production change is part of this task.

- Independent review: fixed stale completed-job reuse after live cache eviction, cleaned owned UUID partial files at startup, and replaced the polygon fixed-area degeneracy cutoff with a scale-aware check. Each regression was observed red before the fix. Added transport error classification/logging. Integrated result after review fixes:38tests,0failures.
- Live local verification against actual IRSA: metadata search found2nativeimages; background job completed; HTTP FITS responses contained63,492,480and66,237,120bytes; SHA256 calculated; SSE snapshot/completion and identical-request cache reuse passed. One initial metadata attempt failed without a diagnostic cause in the original implementation; repeated complete and search-then-background paths passed. Network failures now expose retryable archive_unavailable and log their causes.
