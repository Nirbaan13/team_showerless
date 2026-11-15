# ML namespace relocation implementation plan

> Root coordinates implementation; existing child agents retain explicit ownership. User instruction authorizes relocation and pushing this work through the repository PR flow.

**Goal:** Put all of this session's dedicated ML files, including the published inference release, under `ml/pvusatov/`, preserving their previous subdirectory hierarchy and working integrations.

**Architecture:** Move the Python inference subtree, dedicated Scala API/service/domain/repository/gRPC files and test, dedicated frontend page/API client, and ML reports below the new namespace. Shared backend/frontend entry points remain in their existing builds and reference these sources. Docker and CI build from the repository context while packaging the same v2 runtime and immutable model. Existing teammates' `ml/`, `pipeline/` and shared application changes are preserved.

**Spec:** User's latest explicit instruction: package existing and future directly ML-related work under `ml/pvusatov/` while preserving subdirectories. The last explicit path takes precedence over the earlier `ml/usatov/` spelling.

## Constraints and review focus

- Preserve every frozen model, scientific fixture and historical manifest byte; append a relocation map rather than rewriting old hashes.
- Wait for live native cache writers that read source paths before moving the Python directory. Never kill completed-but-unobserved jobs or silently restart them.
- No duplicate maintained source trees or permanent compatibility symlinks. Shared files contain necessary integration/configuration changes only.
- Root owns moves, git/CI/Docker and cross-component verification. Frontend agent owns moved page/client plus TS/Vite/App import glue. Native-data agent finishes read-only scientific review before any new ownership.
- Public HTTP paths, gRPC service names and v2 model identity remain stable. V3 remains experimental and unpromoted.
- Do not direct-push main; create a reviewable PR. All authored prose documents end `.AI.md`.

## Task 1: Establish namespace and immutable relocation map

- [ ] Create a fresh branch from current main while all agents' code edits are parked.
- [ ] Inventory owned tracked and untracked files with old paths and SHA-256, excluding generated caches/bytecode and external `/tmp` native downloads.
- [ ] Move each dedicated file to `ml/pvusatov/<old relative path>`; move local ML coordination/delivery reports into the analogous `docs/ai` path.
- [ ] Verify the recorded immutable files have identical hashes at new paths. Record historical external-manifest path translations without editing those manifests.

## Task 2: Restore build and runtime integration

- [ ] Include relocated Scala main/test source roots in sbt; move the dedicated analysis protobuf definitions if doing so preserves package and wire names, update generated imports accordingly.
- [ ] Update local `ML_ROOT` discovery to the relocated Python tree; keep container installed runtime paths stable.
- [ ] Update Docker COPY sources/root build context and Dockerfile-specific ignore rules, preserving deployment owner's delta-transfer logic.
- [ ] Update frontend import, TypeScript include and dependency resolution for sources outside `frontend/`, with no navigation or behavior change.
- [ ] Update CI scientific paths and ensure tests cover relocated experiments without leaking final data.

## Task 3: Verify and publish

- [ ] Run frozen release/hash audit and Python tests/smoke from the new location; run Scala tests/stage and frontend lint/build.
- [ ] Verify actual local API and browser use relocated code, including private gRPC and Swagger.
- [ ] Obtain independent review, fix material findings, publish branch and PR with exact validation evidence. Continue the existing authorized merge/deploy flow only after checks pass.
- [ ] Resume v3 experiments from the new root and append relocation provenance; keep final inputs closed until complete freeze.
