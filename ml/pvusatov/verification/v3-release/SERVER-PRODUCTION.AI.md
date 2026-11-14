# Actual VPS v3 installed-release proof

PASS on 2026-11-14T23:23:39.455758+00:00 through 2026-11-14T23:23:40.268937+00:00. The public backend first reported the merged revision and C13 model at 23:23:09 UTC. The subsequent strict-SSH audit verified both running components on revision `a7493463eaace9af4357dcdeb0c8fa939c016ed5`, healthy, with **running image = latest tag = exact revision tag** before and after the additional read-only checks.

| Component | Exact running image |
|---|---|
| Backend | `sha256:cd521f7de4dc528a4b0d98b48932e214511e4959066a591bd5a772702578e209` |
| Frontend | `sha256:ac6d37cb7a16c60421810bf3dccecbdc19e8304c4f9b2b650ce5b699b4457378` |

Installed ONNX SHA-256 is `c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204`. Installed administrative metadata SHA-256 is `f137db2a3b35ed6c8fa709732a3cf70f8276357fce61275920a482fb63360eb5`; its ten protected identity/score/profile/training fields equal the original frozen candidate metadata (`983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04`). ONNX embedded metadata agrees with the installed external metadata: `ExtraTreesClassifier`, `motion-extra-v3-sigma08`, sigma 0.8, minimum speed 0.5 pixels/hour, and every remaining fixed detector setting. Metadata inspection initialized the ONNX session but executed no predictions.

All **nine packaged runtime core Python files** match their scientific-freeze hashes inside the running backend container. All 15 scientific source files were separately verified in the local repository. The six evaluation/training sources are deliberately absent from the production image; this report does not claim 15 remote source copies. Container Python is 3.12.3. gRPC remains privately published at `127.0.0.1:50051`.

The existing `server-audit.py` ran unchanged via SSH standard input with verified known hosts, `StrictHostKeyChecking=yes`, `IdentitiesOnly=yes` and `BatchMode=yes`. The supplemental check read installed bytes and ONNX metadata; no persistent script was uploaded, no new container was started, and no service, application data or configuration was changed or restarted. Credentials remain external and are absent from the evidence.

Evidence: [server-prod-proof.json](server-prod-proof.json), SHA-256 `6864444fcca428cecce1117df11e5b6ad391d82e89873d588b1bbbe0b71a5d02`. It includes original audit-script hash, component/image identities, full installed metadata/profile, runtime source hashes, before/after consistency, public model listing and explicit scope. This proves installed release identity, health and private binding; request integration, browser behavior, real-object precision and future availability are separate evidence.
