# Selected-v3 production API proof

PASS on 2026-11-14 at 23:23 UTC. Public `/version` reported merged revision `a7493463eaace9af4357dcdeb0c8fa939c016ed5` before and after the checks. `/api/analyses/models` and actual analysis results reported ONNX SHA256 `c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204`, `ExtraTreesClassifier`, algorithm `motion-extra-v3-sigma08`, and the bound sigma-0.8/minimum-speed-0.5 detector profile.

[HTTP proof](http-prod-proof.json): the existing smoke script ran against `http://146.103.122.246` with comet-D6 and the fresh-request minimum-SNR override `4.2718281828459`. Job `ca9dbf78-3417-4b1a-8cdb-a21afb84a3b8` completed with four frames and 27 candidates. All 62 returned PNG resources decoded successfully (106,761 bytes). Result-schema validation, SSE completion, request deduplication, an empty high-SNR job (`619d6a91-4b2e-4608-a67c-ebd05f6b5f1a`), missing-download HTTP 404, and invalid-option HTTP 422 passed. The script's recorded analysis/resource checks took 11.70 seconds.

[gRPC proof](grpc-prod-proof.json): through the coordinator's existing `127.0.0.1:15057` tunnel, comet-D2 job `80c99d8a-4e29-426d-8752-9c341c9cd10d` completed with three frames and one candidate. Its result equalled the public HTTP result exactly, and completed watch replay passed. The result's model SHA, family, full detector profile, and algorithm version were independently checked again through HTTP and recorded in the proof.

These are production transport, process-boundary, rendering, and contract checks. They do not change or extend the frozen scientific evaluation. No deployment setting, model, scientific source, or input was modified; all 15 bound scientific source hashes still matched afterward. The coordinator-owned tunnel was left running.
