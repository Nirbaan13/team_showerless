# Downloaded images to unified ML data

The separate `pipeline/unification` module runs inside the current pipeline
container. Scala's processing HTTP client calls its private operation. Scala
owns durable public jobs, completed-ID resolution, source snapshots, capacity
admission, verification and artifact publication. Existing service functions,
frontend and frozen inference code are unchanged.

## Usage

First download native products through the archive or SPHEREx APIs. Select the
completed **asset ID**, not the archive search record ID, for archive inputs:

```http
POST /api/image-unifications
Content-Type: application/json

{
  "inputs": [{"kind": "archive_asset", "id": "ASSET_ID_FROM_DOWNLOAD_STATUS"}],
  "grid": {
    "kind": "sky", "ra_degrees": 266.4, "dec_degrees": -29,
    "width": 128, "height": 128, "pixel_scale_arcsec": 1
  },
  "options": {"normalization": "robust", "mask_policy": "science"}
}
```

For a completed SPHEREx native chunk use
`{"kind":"native_chunk","id":"CHUNK_ID","download_id":"DOWNLOAD_ID"}`.
Only default, unprocessed native downloads are accepted. Invalid IDs fail before
admission. Poll the returned `status_url`; completed jobs provide `artifact_url`.
Jobs survive restart as durable records; interrupted jobs become failed rather
than exposing partial data. Artifacts share the FITS cache budget and can be
evicted. A completed job with an unavailable artifact reports that explicitly.

`image_hdu` optionally selects a FITS HDU number or name. Without it the file
must contain one unambiguous scientific image. Cubes require explicit leading
`plane_indices` in NumPy axis order. Spectrum tables are rejected as images.
Sky registration additionally requires the selected plane to retain both celestial
pixel axes. A plane containing a spectral axis remains usable in explicit pixel
mode, with no invented sky WCS.
FITS, multi-extension FITS, gzip FITS, tiled compression and scaled integer images
are decoded through Astropy; original source bytes are preserved.

`grid.kind=sky` defines a north-up ICRS TAN grid with RA decreasing along x.
`grid.kind=pixel` accepts just width/height and explicitly makes no astrometric
registration claim. The numerical worker additionally supports single-channel
rasters in pixel mode; the current public archive only delivers FITS, so it does
not invent a public raster upload path. RGB needs an explicit future channel
contract and is rejected. Target sides are 1–512 pixels; 1–32 frames are supported.

`target_unit` optionally converts compatible declared physical units. Missing
calibration, ADU-to-flux and conversions requiring unknown beam area are rejected.
Omitting it preserves each frame's own unit. `normalization=robust` creates a
finite tensor using a per-frame median and robust scale; it does not overwrite
physical image values. `mask_policy=motion` retains SPHEREx OUTLIER pixels while
other bad bits remain masked; `science` is the default. Generic mask bits are
never interpreted using SPHEREx's bit definitions.

## ML consumer

After downloading the NPZ artifact, make the package available on PYTHONPATH:

```python
from unification.ml import load_bundle

bundle = load_bundle("dataset.npz")
tensor = bundle.tensor             # float32 [frame, y, x], finite
valid = bundle.valid_mask          # bool [frame, y, x]
images = bundle.images             # physical values, invalid pixels NaN
metadata = bundle.metadata         # JSON provenance, units, WCS, times, limits
images, times = bundle.motion_inputs()  # qualified motion data; times in hours
```

The pickle-free archive includes physical images, tensor, validity and coverage,
variance with its own known-value mask, outlier/bloom masks, actual exposure
midpoints and IDs, and an embedded UTF-8 JSON manifest. Loader validation bounds
ZIP expansion, checks NPY shapes/types, rejects object arrays and verifies
cross-array/manifest consistency before returning data.

General numeric data can be used by ML models that accept its declared context.
The motion accessor additionally requires sky registration, at least three
increasing known exposure midpoints, known distinct physical observation IDs,
compatible known instruments/passbands and calibrated physical units. It fails
explicitly when these are missing. Scientific suitability still depends on PSF,
photometric calibration and the question being studied. The existing production
analysis endpoint remains SPHEREx-specific; foreign assets keep
`analysisEligible=false`. This work does not retrain or qualify the frozen ranker
on other surveys. Tests do exercise the actual existing detector with an exported,
reloaded moving-source stack.

Bilinear resampling does not conserve integrated flux or match PSFs. Variance uses
squared normalized interpolation weights for independent source pixels; induced
covariance is not represented. Unknown metadata is retained as unknown.

## Runtime and checks

The same immutable Docker image runs Scala and pipeline containers. The shared
volume is `/app/data` for Scala and `/tmp/spherex_cutouts` for Python. Private
requests contain only job-relative, server-generated paths and SHA-256 values.
Pipeline starts `unification.app:app`, which composes the new router with the
original application's four science routes. Public Swagger includes the additive
`Image unification` routes. No new Python dependencies are needed for numerical
processing; the existing scientific runtime already provides Astropy/NumPy/SciPy.

The private POST `/internal/image-unifications` is restricted to the container
network. It supervises one numerical child at a time with a 120-second deadline,
request/response limits, and kill/reap on deadline, cancellation or disconnect.
Scala's bounded HTTP operation waits for termination before releasing snapshots.
Individual input encoded/decoded sizes are bounded at 256 MiB; aggregate selected
source bytes are limited to 256 MiB. NPZ is at most 192 MiB compressed and 192 MiB
expanded. Native output capacity is admitted through the shared cache coordinator.

```bash
PYTHONPATH=pipeline:ml/pvusatov/backend/inference python -m pytest -q pipeline/tests
# From backend/; UNIFICATION_PYTHON enables real Python HTTP integration:
UNIFICATION_PYTHON=python ./sbtw test stage
# Inside the running pipeline container, tests the packaged operation and loader:
/opt/inference-venv/bin/python /app/pipeline/unification_smoke.py
```

CI installs pinned/hash-locked test dependencies, runs numerical/HTTP and Scala
suites, builds the exact image and checks the packaged private HTTP/ML loader
alongside deployment and rollback. Research alternatives and primary sources are
recorded in IMAGE-UNIFICATION-RESEARCH.AI.md.
