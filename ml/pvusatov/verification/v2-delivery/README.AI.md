# V2 delivery diagnostics snapshot

These exact diagnostic scripts and proof outputs were previously temporary files in the ML session. They are preserved here because the user requested that existing ML work be available under `ml/pvusatov/`. `snapshot-manifest.json` records their byte hashes.

The JSON proofs describe actual production v2 checks on 2026-11-14, including HTTP/gRPC/PNG/SSE, browser behavior, Swagger and the later viewport fix. They are historical observations with their recorded component revisions, not v3 evidence or a claim that a mutable deployment still has the same revision.

The scripts are historical snapshots, not supported generic CLI tools: some pin job IDs/revisions, temporary grpcurl binaries/import paths or the local Playwright installation. Resolve those deliberately before reuse. Standalone protobuf clients now need `ml/pvusatov/backend/src/main/protobuf/spaceapps/retrieval/v1/analysis.proto`, the shared `backend/src/main/protobuf` include root and the sbt-resolved external include directory. The current production target is 146.103.122.246; the old AWS target is obsolete.

No credentials or private key contents are included. Running the read-only server audit requires an already authorized SSH connection; strict host-key checking and the separately held admin key remain outside this repository.
