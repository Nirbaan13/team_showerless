# gRPC and package implementation plan

Goal: add a native gRPC interface for a server-side frontend, apply the accepted Controller/Service/Repository package structure, merge PR3 after checks, verify public Swagger and automatic deployments for both backend and frontend.

The user explicitly approved implementation and merge. IRSA belongs to spaceapps.integrations.irsa and the gRPC server to spaceapps.integrations.grpc. HTTP remains compatible with the current OpenAPI; PNG and scientific modes remain deferred. All adapters share the same application service, repository, cache and workers.

Packages: controller (HTTP), domain (immutable models/query validation), service (orchestration and outbound ports), repository (SQLite), bootstrap (composition/lifetime), integrations.irsa (archive adapter), integrations.grpc (protobuf mapping and incoming gRPC adapter).

Steps:
1. Move existing classes into packages; retain public HTTP schema and persistent JSON compatibility. Verify existing38tests.
2. Fix confirmed review defects with red/green regressions: job.updated must always carry a manifest; active partial transfer bytes must not count twice in storage admission.
3. Add versioned typed protobuf contract, generated Scala/ZIO gRPC code, request/error mapping, metadata search, native preparation, job status/watch, streamed FITS and revision. Keep gRPC internal by default, on a separate port. Real TCP client/server tests must cover validation, unknown/pending/failed files, status and stream completion/cancellation.
4. Wire both listeners under application scope; update Docker/Compose/build/CI/docs and verify protobuf codegen and service lifecycle on JDK25.
5. Inspect frontend deployment; establish automatic build/deploy on main if absent, with scoped ownership to avoid disturbing backend deployment. Verify actual target.
6. Independent review, full tests/container CI, update PR3 and answer review threads. Merge only after checks pass, then verify deployed revision, Swagger UI/schema/API and frontend deployment. Notify the WhatsApp team according to the repository flow.

The original objective is preserved and extended by the user's explicit continuation and expanded instructions; no approval to merge is inferred from earlier messages because the user has now expressly requested it.

## Validation ledger

- Package-only migration retained all38existingtests.
- job.updated regression failed against compact payloads, then15JobsSpec tests passed after marking deferred previews at discovery and retaining full manifests for job.updated.
- Cache admission regression reproduced the active-partial double count; reservations now track active paths, exclude written partials from completed usage and reserve only remaining disk bytes.
- Native gRPC generated client/server TCP tests passed8/8, including typed errors/trailers,200003bytefile reconstruction, client cancellation and bounded server shutdown with an active watch.
- Full integrated sbt test/stage:48passed,0failed. Runtime/codegen dependency pins verified against published artifacts.
- Frontend npm lint/build passed;5existinglintwarnings retained. Real isolated VPS Docker tests verified revisions, assets, current/latest, healthy updates, failed updates, same-SHA rollback and both API proxy paths. Temporary test resources removed.
- Independent final review found no Critical or Important issues. Frontend forced-command user/key and GitHub secret were prepared; backend Compose adds loopback gRPC and persistent data. Existing running backend is unchanged until the approved main deployment.
