# Complete team pipeline integration in PR 7

## User-approved final design

Scala calls the existing team pipeline as a separate HTTP container. The user
explicitly rejected a Python child-process adapter inside Scala's container and
requested deletion of its dead code. Scala sources/protobuf/resources move to
backend/scala/src; the OpenAPI contract moves to backend/docs/openapi.yaml.

The final flow is frontend -> Scala -> pipeline HTTP service -> team cleaning and
spectral functions -> Scala -> frontend. Scala owns IRSA discovery, server-side
cutouts, persistent jobs, cache leases and public HTTP/gRPC. Containers share the
same /app/data volume. They run the same immutable image revision with different
commands, allowing the existing SHA-based image delivery and rollback to remain.

## Implementation tasks

1. Reconcile main into PR7, preserving existing ML analysis, IRSA cutouts and CI.
2. Retain the team's current numerical cleaning/spectral functions. Add bounded
   internal HTTP processing operations in pipeline/service.py. Supervise execution
   inside the pipeline service; validate all paths against its shared-data root.
3. Replace Scala PythonProcessor/ProcessBuilder with HttpProcessingClient.
   Preserve default previews, ZODI mode and typed HTTP/gRPC failures. Add the
   diagnostic spectrum endpoint and durable-download polling handoff.
4. Connect frontend spectral requests through Scala, handle202/cancellation,
   expose measured-point counts/quality and errors without simulated fallback.
5. Package both containers; verify old Compose migration, revision consistency,
   health/rollback, existing frozen ML and frontend. Remove the obsolete backend
   Python adapter, worker settings and subprocess tests; relocate numerical/HTTP
   tests to pipeline/tests.
6. Push the existing PR7 branch and update its review description. Do not merge.

## Scientific boundary

SpectrumPreview contains actual WCS-WAVE diagnostic aperture measurements and
explicit experimental_visualization_photometry quality. It is not a calibrated
science spectrum. Missing bands, molecular detections, aperture corrections and
local-background corrections are never synthesized. The strict science spectrum
operation stays gated. Epoch-difference remains unsupported because the team
removed its alignment module; existing independent ML motion analysis remains.

## Review focus

- Cancellation/deadlines terminate pipeline computation; input leases and atomic
  publication must not expose incomplete outputs.
- Current SOURCE-only/positive-variance masking must agree across operations.
- Missing spectral WCS, off-image/partial/flagged apertures and upstream failures
  remain explicit; invalid pixels outside an aperture do not reject valid points.
- Both containers and retained ML sources must be present in Docker's allow-list.
- Experimental diagnostic spectra must never be presented as calibrated102bands.

## Evidence ledger

The pre-HTTP implementation passed142 Scala tests (one optional live test ignored),
42 Python tests and three frontend client tests, plus frontend lint/build. That
architecture was superseded by the user's explicit separate-container instruction;
those results alone do not verify the final architecture.

Independent review identified and corrected Docker ML allow-list relocation,
variance-mask disagreement, off-aperture variance rejection, stale calibrated/
102-band claims and zero/negative flux plotting. Mask fixes were reproduced in
failing FITS tests before their implementations. Final HTTP/Compose verification
is recorded in the PR description and CI results.

Final HTTP architecture local evidence: 141 Scala tests passed, one optional live
IRSA test ignored; 60 Python FITS/HTTP tests passed; three frontend client tests
passed, lint has no errors and production build passed. The cancellation regression
failed before making the HTTP completion region bounded and uninterruptible, then
passed with the complete suite. The client bounds chunked responses to64KiB.
Server504/503 retain gateway-timeout/service-unavailable public semantics. No
backend Python adapter directory, worker settings or adapter ProcessBuilder remain.
