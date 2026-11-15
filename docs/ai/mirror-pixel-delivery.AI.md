# Mirror pixel delivery during an IRSA outage

Issue: https://github.com/Nirbaan13/team_showerless/issues/33

## Failure and intended behavior

SIA and TAP can be unavailable while the official NASA S3 bucket remains reachable. The mirror catalogue then supplies actual product identities, dates, detectors and sky footprints. A successful catalogue search alone does not establish that image delivery works: the previous transfer implementation mapped every mirror product back to IRSA IBE for its cutout.

The mirror path must obtain the selected source pixels directly from S3 and create a native rectangular subset locally. Keep the original S3 identity and the selected geometry in the cache key. The IBE-formatted selection URL describes geometry; the mirror transport does not contact that host. Normal primary discovery and hourly recovery checks retain their existing behavior.

## Data integrity and resource bounds

- Accept only allowlisted official SPHEREx S3 products, with a matching IBE selection path.
- Request bounded byte ranges and require valid HTTP 206 responses. Pin the object ETag across requests.
- Read the required pixel rows and necessary auxiliary tables; do not preload the entire archive or a complete full-frame product merely to obtain a small field.
- Preserve native pixel values, detector masks, variance, calibration tables and the shifted celestial and alternate WCS. Do not rotate, interpolate or invent pixels.
- Reject unsupported layouts and unsafe URLs explicitly. Remove partial outputs when transfer, validation or cancellation fails.
- Continue to report incomplete metadata coverage honestly. This change cannot make an unindexed part of the sky searchable.

## Verification

Verification must cover the Scala transport routing, the subprocess boundary, strict HTTP Range and identity handling, and an actual official S3 product. Compare the resulting pixels and world coordinates with the corresponding original source window. Synthetic FITS fixtures are appropriate for transport failure regression tests; they do not establish real-data compatibility.

Verified before opening the draft PR:

- Full Scala backend: 287 passed, four opt-in live tests ignored.
- Python backend: 70 passed, one optional smoke skipped; shared gateway and processing callers: 117 passed.
- A real 36×36 cutout matches every original IMAGE, FLAGS, VARIANCE and ZODI pixel. Celestial SIP WCS matches within 1e-10 degrees; alternate reference pixels shift correctly. EPSF and WCS-WAVE tables remain byte-identical. The optimized result SHA-256 is `05723b99700a942ba055e244c8267a6abf7de96fb62d47d8e7267e45ef6f411e`.
- An isolated container on the VPS fetched a real WISE-field cutout directly from S3: 9,380,512 network bytes from a 65,710,080-byte parent, 44 ranges, 73.35 seconds. No production service was restarted for this test.
- Backend and ML Docker-specific context smoke builds include the helper and import the complete caller chain successfully.

The VPS measurement means an 18-second mirror deadline is insufficient. Python callers now use a separate 90-second mirror deadline, while IBE retains its existing 18-second bound. Both native network and output budgets remain 24 MiB. This is a slow fallback rather than an immediate response; metadata completeness and the number of usable observations can still limit an analysis. Production rollout remains pending human review.

## Cold end-to-end outage verification on the VPS

On 2026-11-15, an isolated test API used an empty pixel cache and 29 verified metadata records. SIA and TAP were configured to unreachable loopback ports. The container mapped `irsa.ipac.caltech.edu` to loopback as well, preventing an accidental IBE request from succeeding. Production containers remained running throughout.

The exact original object was `dr1/level2/2025W19_1B/l2b-v27-2026-197/5/level2_2025W19_1B_0231_1D5_spx_l2b-v27-2026-197.fits` from the official NASA S3 mirror.

| API path | Result | Time | Downloaded FITS | IMAGE shape |
|---|---|---:|---:|---|
| Legacy `/api/observations/default` | One of one chunks ready | 52.06 seconds | 3,985,920 bytes | 49×50 |
| Federated `/api/archive-searches` → `/api/archive-downloads` with `require_cutout` | Completed, real asset downloadable | 44.28 seconds | 3,962,880 bytes | 37×38 |

The legacy job retained `archive_mirror_partial` as a coverage warning; no pixel transfer failed. Both HTTP responses were reopened as FITS and contained IMAGE, FLAGS, VARIANCE, ZODI, EPSF and WCS-WAVE, with their original S3 URL recorded in `SRCURL`. Different request geometries explain the different native shapes.

Exported response SHA-256 values:

- Legacy: `25c1f76fc3175bee51effea8f7c483d26a233b0104a1b1a149169784f3379ffc`.
- Federated: `58674afdf7eb43af5d24643a9d8b987913fd4f382eb9e5d2c946b30d93ebf5c6`.

Runtime logs and JSON manifests are preserved locally in `/tmp/spaceapps-irsa-pixel-proof/`; original verification scripts and science comparison results remain there or in `/tmp/spaceapps-verify-native.py`. These checks establish delivery under a forced outage. They do not claim complete sky coverage, a confirmed object detection, or successful model inference for every field.

Geometry remains an enclosing native-axis subset. Python callers retain the previous IBE-compatible size semantics; this is not a guarantee that every corner of a north-aligned sky box is present on a rotated detector grid. Supporting a distinct sky-box contract is separate from transporting the same original data during an outage.
