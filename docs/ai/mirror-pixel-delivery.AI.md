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
- Python backend: 70 passed, one optional smoke skipped; shared gateway and processing callers: 115 passed.
- A real 36×36 cutout matches every original IMAGE, FLAGS, VARIANCE and ZODI pixel. Celestial SIP WCS matches within 1e-10 degrees; alternate reference pixels shift correctly. EPSF and WCS-WAVE tables remain byte-identical. The optimized result SHA-256 is `05723b99700a942ba055e244c8267a6abf7de96fb62d47d8e7267e45ef6f411e`.
- An isolated container on the VPS fetched a real WISE-field cutout directly from S3: 9,380,512 network bytes from a 65,710,080-byte parent, 44 ranges, 73.35 seconds. No production service was restarted for this test.
- Backend and ML Docker-specific context smoke builds include the helper and import the complete caller chain successfully.

The VPS measurement means an 18-second mirror deadline is insufficient. A separate bounded mirror deadline is required before declaring the Python live-search path ready. Production rollout and cold API checks remain pending review.

Geometry remains an enclosing native-axis subset. Python callers retain the previous IBE-compatible size semantics; this is not a guarantee that every corner of a north-aligned sky box is present on a rotated detector grid. Supporting a distinct sky-box contract is separate from transporting the same original data during an outage.
