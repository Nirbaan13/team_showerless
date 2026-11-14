# Namespace relocation verification

These probes exercise the running application after its dedicated ML sources moved under `ml/pvusatov/`. They use real archived FITS fixtures and the immutable v2 ONNX model; no expected coordinates are used by inference. The local server used a worktree based on Git revision0bf04fa with uncommitted relocation changes; its version field therefore identifies the base revision, not a claim of a clean deployed release.

- `http-proof.json`: four frames, ten candidates, 28 real PNG resources, SSE completion, deduplication, empty/error behavior and public result-schema validation.
- `grpc-proof.json`: extracted analysis.proto client, three frames/two candidates, HTTP/gRPC result equality and watch replay.
- `grpc-old-server-new-proto-proof.json`: the newly extracted protobuf client also interoperated with the existing VPS service before relocation deployment, demonstrating wire compatibility.
- `swagger-proof.json`: actual browser loaded the spec through the frontend proxy and executed GetModels successfully, with no JavaScript errors.
- `viewport-proof.json`: actual frontend displayed a real computed job with reachable provenance at desktop and mobile sizes; shared Homepage navigation still worked.

Run `http-smoke.py` and `grpc-smoke.py` from the repository using the diagnostic Python environment (including jsonschema). Defaults are HTTP127.0.0.1:18086 and private gRPC127.0.0.1:15056. `PROBE_HTTP`, `PROBE_GRPC`, `GRPCURL` and gRPC `PROBE_OUTPUT` override those values. The gRPC probe resolves both repository proto roots and sbt's external includes. Its default grpcurl binary and the Swagger probe's Playwright installation are local diagnostic prerequisites.

Run `swagger-smoke.cjs` with the frontend proxy running on127.0.0.1:18087, or set `PROBE_FRONTEND`. Browser screenshot output remains temporary. The historical viewport script in the adjacent v2 snapshot supports `PROBE_BASE`, `PROBE_JOB` and `PROBE_PROOF` for exercising the currently computed ten-candidate/four-frame fixture.

The live IRSA test ignored by the Scala suite is an existing opt-in network test, `known QR3 product returns a small valid MEF with every mission extension`. The relocation checks separately passed131 Scala tests/stage,78 package tests, experimental accounting tests and the real-data Python smoke. CI/container and post-merge VPS verification are recorded separately when completed.
