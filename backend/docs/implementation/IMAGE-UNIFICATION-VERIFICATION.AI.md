# Image unification verification and review

## Scope

Research, a separate numerical module in the existing Python pipeline container,
a Scala processing client and durable public jobs, artifact/ML interoperability,
and a feature PR. Original pipeline/service.py, spherex/scripts functions,
frontend and frozen ML artifacts are unchanged.

## Verification performed

- Baseline main44cc7e3: Scala test/stage185 passed, zero failures, three ignored.
- Python pipeline final scientific/HTTP suite:57 passed, including the full
  advertised32×512×512 shape, bounded-output writer and14 physical-identity cases.
  The environment reports one external Starlette/httpx deprecation warning.
- Existing inference91 passed; experiments74 passed; frozen v2 suite78 passed;
  final guards31 passed plus21 subtests. No changes to those sources or models.
- Actual existing detector recovers an injected moving source after export/reload
  through rotated/translated WCS; a SIP regression is also present.
- Actual Scala HTTP -> pipeline -> published NPZ -> Python ML-loader test is part
  of the Scala suite when UNIFICATION_PYTHON is set.
- Standalone packaged-operation smoke script passed against the locally running
  composed Uvicorn application. Exact Docker execution is delegated to PR CI:
  this workstation's Docker socket denies access.
- Real downloaded ESO and CADC FITS decoded/reprojected/exported/reloaded. ESO:
  194 valid pixels on32×32 grid, ADU and actual exposure midpoint preserved;
  CADC:324 valid pixels, unknown units/time remain unknown. Both correctly remain
  unqualified for motion inference.
- YAML parses, component schemas pass JSON Schema syntax checks; every preexisting
  OpenAPI path/schema is structurally unchanged. Deployment shell syntax and SSH
  command-rejection checks pass.

## Independent review and decisions

The independent whole-feature review found no Critical findings and four
Important findings. Each received a regression test before its fix:

1.32×512×512 already consumes160MiB for eight core arrays, before metadata.
   **Decision:** the new format's compressed and expanded limits are192MiB.
   This changes only this module, not frozen inference input limits. Full maximum
   geometry now exports/reloads successfully. Cost: a larger bounded per-job disk
   reservation and loader memory budget.
2. Publication double-reserved a product and counted staging as completed data.
   Associate staging with a directory reservation and atomically adopt the
   validated existing file using that reservation. Tests exercise an exact byte
   budget, final eviction and a complete tight-capacity service lifecycle.
3. Checking compressed size after writing could overrun reserved space.
   A seekable bounded writer rejects before a write crosses the limit; the peak
   file-size regression verifies no excessive bytes reach disk.
4. ObsCore dataset IDs were mislabeled as physical exposure identities.
   Keep product IDs separately; qualify ESO/CADC observation identity from
   collection+obs_id. SPHEREx uses actual OBSID/OBS_ID plus a verified detector.
   Missing identities stay unknown; contradictory trusted/native identities fail;
   distinct products of one physical exposure cannot become independent epochs.

Additional regressions cover duplicate NPY header keys and canonicalization of
mathematically integral JSON decimals before the strict Python boundary.

The reviewer did not repeat parent-owned suite execution, network probes or Docker
execution. Those require the evidence above and PR CI. Destructive hard-crash/VPS
pressure experiments were outside the requested PR scope. PSF equivalence and
frozen-ranker qualification are not established by format registration and remain
explicit scientific limitations, with foreign analysis eligibility unchanged.

Final Scala test/stage:209 passed, zero failures, three ignored, with real Python
HTTP integration enabled. Staged Main health, Swagger and the three additive
public paths passed. Exact PR container/CI outcomes are recorded in the PR.

Repeated native-fixture setup exposed an intermittent cache admission failure.
A real-cache regression reproduced423/1000 failed admissions while a WAL sidecar
was created/deleted: Files.walk could throw NoSuchFileException before the
per-file size check. Usage scanning now uses walkFileTree and captured attributes,
ignores only disappeared entries and propagates other I/O failures. The regression
and complete209-test suite pass. The exact exception from the earlier fixture
was not captured, so this establishes a confirmed cache race rather than asserting
certainty about that earlier single failure.

A selected-cube regression additionally verifies celestial pixel-axis correspondence.
A plane that fixes RA and retains frequency/DEC cannot be registered as a sky
image; explicit pixel mode remains available with unknown astrometry.

## PR #19 rebase and processing module integration (2026-11-15)

Rebased onto the merged downloads/common-observations implementation from PR #18.
Moved all Scala unification production code to processing controller, service,
service/model, service/core and repository packages; retained the HTTP transport
in processing/integrations. Updated bootstrap and tests to the current module
owners. Original PR #19 Python unification code and frontend code are unchanged
by this integration.

Archive source resolution now uses the scoped downloads resource operation so
the same LRU coordinator holds an input lease during inspection and snapshotting.
Known unification staging is reclaimed before producer startup. The extended
shared-cache crash recovery test first failed with cache_capacity against the
old cleanup, then passed after recognizing the generated staging paths. Final
NPZ publication still uses the existing directory reservation, product size
limit and common LRU index.

Fresh verification after integration:

- Scala test/stage: **234 passed, zero failed, three optional live checks ignored**.
  UNIFICATION_PYTHON enabled the real Scala HTTP -> Python -> NPZ -> ML-loader test.
- Python pipeline scientific/HTTP suite: **57 passed**, one external
  Starlette/httpx deprecation warning.
- OpenAPI: all 38 existing main paths and 45 schemas are structurally unchanged;
  total 41 paths and 51 schemas. All local references resolve and component
  schemas pass JSON Schema syntax validation.
- Deployment shell syntax and SSH command-rejection checks pass.
- Independent read-only review found no Critical or Important integration
  findings, including the startup cleanup. Minor stale module names in design
  and plan documents were corrected. A dedicated final-NPZ/unknown-child recovery
  preservation assertion remains an optional coverage improvement.

Exact Docker build, packaged-operation smoke, deployment/rollback and old Compose
upgrade checks run in PR CI; local Docker daemon access remains unavailable.
