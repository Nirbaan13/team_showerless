# Archive image unification design

## User brief and scope

Research suitable tools, implement a new module in the current pipeline Python
container, enhance the Scala processing HTTP client and create a reviewable PR.
The objective is real unified data for ML. Frontend and frozen model artifacts are
outside scope. Existing team Python functions retain their behavior.

## Data path

Completed downloaded asset/chunk IDs -> Scala durable unification job -> immutable
input snapshots/checksums -> pipeline unification HTTP operation -> bounded NPZ and
manifest -> Scala validation/atomic publication -> public artifact URL and ML loader.

The two containers currently mount one volume at Scala /app/data and Python
/tmp/spherex_cutouts. Manifests therefore carry server-generated relative job paths.
Neither public nor private APIs accept arbitrary caller absolute paths or URLs.

## Input and output contract

A request selects1–32 completed image assets/native chunks, per-input image-HDU
and optional leading cube-plane indexes, and either an explicit ICRS TAN target
grid or an explicit pixel-grid output shape. Both output sides are at most512.
Source image sides are bounded before loading; compressed/expanded bytes, output
size, concurrency and execution duration have independent limits.

Automatic FITS HDU selection succeeds only for an unambiguous scientific image.
Generic masks/DQ, uncertainty/variance/inverse-variance and SPHEREx flag semantics
are explicit profiles, not assumed shared bit positions. A spectral table or
unselected multidimensional cube is not an image. Pixel-grid rasters preserve
that their registration and physical calibration are unknown.

Version1 artifact contains typed numeric arrays: images, valid_mask, footprint,
variance and variance_valid_mask, outlier/bloom where known, times in hours with
an explicit known-time mask, Unicode frame/observation IDs and UTC dates, grid
metadata and a UTF-8 JSON manifest. No pickles/object arrays. It also supplies a
finite model tensor with invalid positions zero and a separate validity mask;
any intensity normalization records its scale/offset and never overwrites the
physical images. Original downloaded bytes remain immutable.

Missing units/times/variance remain explicitly unknown. Requested unit conversions
must be physically supported by source metadata; no ADU-to-flux or Jy/beam
conversion without calibration. Filters, wavelength ranges, missions and sources
remain per-frame provenance. Registration does not establish matching passbands,
PSFs, calibrated photometry or discovery probabilities.

## Genuine ML consumer

A versioned loader checks archive members, shapes, types, bounds and provenance.
It returns the unified tensors for general ML. Its motion-detection accessor
requires a sky-registered stack, at least3 distinct known exposure midpoints and
compatible known units/passbands; it supplies the existing detector's images and
relative-hours contract. Tests must recover an injected real pixel trajectory
through actual `ml_inference.detector.find_candidates` after export/reload, with
rotated/translated WCS and invalid pixels. No preset spoofing or automatic change
to foreign `analysisEligible=false` is permitted. Frozen model files are unchanged.

## Scala service and lifecycle

Use a dedicated SQLite unification_jobs table, transactional admission/claim and
application-scoped workers. POST returns202 with id/status_url; GET returns durable
state; artifact GET serves only a completed registered bundle. The existing four
synchronous pipeline proxy endpoints keep their current contracts.

Resolve archive IDs through scoped DownloadsService.resource and associated metadata; native chunks
through Jobs.leasedResource. Snapshot with a hardlink or bounded copy under the job
directory, verify SHA against persisted archive bytes, and keep snapshots through
bounded remote completion. A cache pin alone cannot prevent same-ID atomic source
replacement. Reject missing/changed/symlink inputs, and never fetch URLs supplied
by the caller.

Reserve output capacity and extend tightly constrained ownership/retention for
unification outputs so they cannot accumulate outside the existing disk budget.
Validate result schema, identity, dimensions, byte count and checksum before atomic
publication. Restart marks or requeues interrupted work without exposing partial
artifacts. Cleanup snapshots/partials on terminal paths and recover abandoned work.

## Python HTTP composition and execution

A new application entry point imports the current service application and mounts
the unification router. Existing service source need not change. The router validates
shared-root manifests and supervises its numerical job with finite concurrency,
wall time, output bytes and child cleanup. Scala waits for bounded remote completion
before releasing inputs. Packaging adds the new module and its tests to the same
image; the pipeline container selects the new composed entry point.

## Verification requirements

- FITS primary/extension/gzip/tile-compressed/scaled unsigned inputs, explicit HDU
  and cube plane selection; raster pixel-grid path; masks and malformed inputs.
- Shared sky pixels under rotation/translation/SIP, known unit conversion, correct
  squared-weight variance and explicit covariance/flux-conservation limits.
- Real times, duplicate identities, missing calibration/bands and safe NPZ loading.
- Existing ML detector recovery after export/reload, not only file-name/shape checks.
- Scala completed-ID resolution, immutable snapshot replacement race, unknown IDs,
  disk/output bounds, restart behavior, HTTP failures and artifact publication.
- Current Python and Scala suites, container build, private-service health and PR CI.
- Final PR contains the new authorized Python module, Scala client/service/schema,
  required packaging/docs/tests and no frontend or frozen-model changes.
