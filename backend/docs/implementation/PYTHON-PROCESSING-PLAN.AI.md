# Incremental Python processing integration

User instruction: connect the team's Python processing on the backend side only after runtime/scientific verification. Keep alignment and unverified spectrum handling disabled. This is separate from merged PR6 metadata/equipment/deep/LRU and from the concurrent ML Analyses/ONNX branch.

## Boundaries

- Use the existing Processor/Jobs interface and application-scoped jobs, native cache reservations and input leases. Scala owns discovery, caching, jobs and public API. Python only processes trusted local FITS paths and writes a new output file.
- Enable real IMAGE PNG previews and IMAGE minus the native ZODI model through the team's load_clean_cutout. Preserve all original FITS HDUs and WCS in processed files, mark provenance and reject double subtraction. Never call pipeline/service.py or its synthetic fallback.
- Keep epoch-difference/alignment unsupported. Characterize the team spectrum functions but return typed not-ready until per-pixel CWAVE/CBAND calibration and scientific photometry assumptions are qualified. Do not invent 102 missing bands or enable an approximate spectrum API.
- Supervise one Python subprocess per operation through ProcessBuilder argument vectors and bounded stdin/stdout/stderr. Limit concurrent processing, task duration and output bytes, and terminate child processes on interruption. No shell or client-supplied executable/path.
- Python CLI protocol: one stdin JSON request for capabilities, preview, zodi or gated spectrum; one stdout JSON result. Incidental library output goes to stderr. Output paths must be new files; Jobs publishes them atomically after successful completion.
- Root owns Scala Processor, HTTP/gRPC capability/mode wiring, Docker, CI and OpenAPI. Python worker owns backend/processing/worker.py and tests. No edits to backend/inference or its training/model data.
- Agreed with ML owner: land Processor first. Use Python3.12 and the compatible pinned NumPy2.5.3/Astropy8.0.2/Pillow12.3 stack. Runtime virtualenv convention is /opt/inference-venv; preserve independent child PYTHONPATH including /app/pipeline. ML owner reconciles its later Docker/requirements changes.

## Implementation and verification

- [ ] Run Python tests on real FITS fixtures and immutable cached native files using the shared UtilsAI environment. Verify PNG bytes, flags/units/shapes, single ZODI subtraction, FITS/WCS preservation, protocol failures and explicit spectrum gate.
- [ ] Write failing Scala subprocess and real-FITS Jobs/API tests. Implement bounded PythonProcessor and readiness/capability probing.
- [ ] Expose supported processing modes in HTTP/gRPC while preserving default/range/polygon/deep queries and existing deferred epoch difference.
- [ ] Install hash-locked scientific runtime dependencies in Docker, copy only the needed pipeline/worker sources and run scientific tests in CI. Build using repository-root Docker context.
- [ ] Run full Python and Scala suites, real FITS integration and preview/subtraction checks. Review independently, resolve material findings, open a separate PR and finish the authorized merge/deploy flow.

## Review focus

- Missing or invalid source data must fail explicitly, never generate replacement stars or fluxes.
- Cancellation, timeouts and excessive diagnostics must not leak processes or release native-file pins early.
- A processed IMAGE must not receive ZODI subtraction a second time during preview or future measurement.
- Derived FITS output must preserve ancillary layers/WCS/provenance and remain distinct from immutable native inputs.
- New Python runtime/Docker/CI wiring must coexist with the ML owner's independent inference environment and additive Main/API work.
