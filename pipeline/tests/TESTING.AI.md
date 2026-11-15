# Pipeline HTTP processing verification

Scala owns archive search, downloads, public APIs, and file leases. It calls the
team pipeline container over HTTP; Python processing lives entirely in `pipeline/`.
Start from that directory with `python -m uvicorn service:app --host 0.0.0.0 --port 8002`.

Install the existing scientific runtime lock from `ml/pvusatov/backend/inference/requirements-inference.txt` plus
`pipeline/requirements-http-test.txt`, then run `python -m pytest pipeline/tests -q`
from the repository root. The tests use real on-disk FITS and real subprocesses.

`GET /internal/capabilities` reports preview, ZODI subtraction, and experimental
spectrum preview. `POST /internal/processing` accepts the bounded processing JSON
contract. Successful responses retain `status: ok`; validation failures return
HTTP 422 with `status: error` and typed `error.code`. Capacity returns 503;
processing deadlines return 504. Both containers mount the same `/app/data` paths.
`PROCESSING_DATA_ROOT` defaults to `/app/data`; resolved input and output paths
must remain beneath it. Inputs must exist; outputs must be new files in existing
directories. Requests are capped at 65,536 bytes, FITS files at 256 MiB, images at
4096 by 4096, and spectral batches at 120 observations. The default concurrency
limit is two operations and the deadline is 120 seconds. Both settings are
configurable by `PROCESSING_MAX_CONCURRENCY` and `PROCESSING_TIMEOUT_SECONDS`;
the latter cannot exceed 120 seconds. The Scala HTTP timeout is longer.

Each operation uses an immutable JSON snapshot on a supervised Python child's
stdin. Stdout and stderr are each capped at 65,536 bytes. File size is bounded by
the child's OS resource limit and numerical output checks. Deadline, disconnect,
or ASGI task cancellation kills the child's process group and waits for process
exit before completing the request, so Scala can safely release native leases.

The numerical implementation is `spherex.processing`. It imports the team's
`spherex.cleaning.load_clean_cutout` and `scripts.spectra.measure_cutout_point`.
Archive query dependencies are loaded only for the preserved public archive APIs,
so internal processing starts without `astroquery` or deleted alignment code.

Preview masks bad pixels and renders ZScale PNGs. ZODI subtraction preserves
other HDUs and WCS, records provenance, regenerates checksums, and rejects a
second subtraction. FLAGS allows SOURCE only; nonfinite/nonpositive variance is
masked. Invalid variance outside a spectral aperture does not discard good
measurements inside it.

`spectrum_preview` measures actual complete apertures using WCS-WAVE. It returns
`experimental_visualization_photometry`, `scientifically_calibrated: false`, and
explicit limitations. No channels or detections are fabricated. The strict
scientific `spectrum` operation remains gated inside the numerical module and is
not advertised or exposed through the HTTP processing contract. Matched CWAVE and
CBAND alone do not bypass that gate.

The five-pixel spectral fixture independently expects 95 MJy/sr after ZODI
subtraction: flux 2.232920901214299 mJy and uncertainty 0.10511500891568655 mJy.
Raw pixels sum to 110 MJy/sr: flux 2.585487359300767 mJy. The tiny native fixture
used by Scala can be regenerated with `pipeline/tests/generate_native_fixture.py`.
