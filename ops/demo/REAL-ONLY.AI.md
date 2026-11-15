# Version 1: real data only

Build the demo frontend with `VITE_DEMO_REAL_ONLY=true`. Run the ML service with
`DEMO_REAL_ONLY=1`. Both switches are explicit; ordinary frontend builds and ML
processes retain their existing behavior. A frontend runtime environment variable
cannot change an already compiled Vite bundle.

## What remains available

- The published SPHEREx review artifacts for `december-d6`, `december-d2`,
  `vesta-d6`, and `vesta-d3`: original observation IDs, aligned/residual/BLOOM
  images, measured track coordinates and available residual SNR, fit RMS,
  velocities, ephemeris offsets, and stored stack images.
- Real coordinate acquisition and inference through the backend. The five stellar
  presets first load the packaged real raw field previews described below, including
  direct preset and matching coordinate links, with an explicit 12′ field
  to accommodate their older reference coordinates and proper motion. The visible
  FOV selector and shared URL retain that 12′ field; no shifted center is invented. Archive failures remain
  explicit and never select a synthetic image sequence or invented candidate.
- The real spectrum and catalog APIs routed to the backend. A request failure or
  missing product stays unavailable.
- User-created discussion entries. Real-only browser storage uses the separate
  `spherex_real_community_comments` key so previous mock discussions cannot leak
  into a real-only session.

## Packaged raw archive fields

`/demo/preview-manifest.json` describes actual FITS-derived PNGs from the read-only
seed. In strict mode, only the five named stellar fields, their published query
coordinates, recommended detector, and an explicitly requested 12′ FOV can use
these artifacts. A nearby coordinate, another detector, or another FOV continues
through the real backend; missing, invalid, or non-real manifests cannot become a
cache substitute.

The loader checks schema/provenance, release, timestamps, local artifact paths,
NASA IRSA source links, digest formats, and actual PNG dimensions. On secure
browser origins it also compares the PNG SHA-256. Valid previews remain usable
when another preview is unavailable. Observation timestamps, native rectangular
geometry, FITS/source links, and the reference-coordinate/proper-motion notes are
preserved. Source FLAGS nonzero percentages include informational SOURCE bits;
they are recorded separately and never treated as bad-pixel quality.

Raw previews require no motion model. A one- or two-observation field stays
visible with an explicit insufficient-evidence status. Larger raw sequences also
state that motion analysis was not run. No candidates, scores, difference images,
BLOOM images, or inferred target identification are created. Catalog overlays are
disabled because these frame responses supply no WCS. The published 3I/ATLAS and
Vesta motion reviews continue to use their existing verified review artifacts.

## Data deliberately left unavailable

Review conversion does not manufacture flux from SNR, infer SNR from BLOOM area,
invent cosmic-ray counts, derive confidence from rank, or interpolate detections
in epochs where none were linked. Missing values stay absent. Historical
heuristic/forest ranks remain ranks; an unknown score does not become a confidence
measurement. Stored review targets receive no invented persistent registry ID.

The legacy analytic 102-channel spectrum is empty in real-only mode. Reporting
therefore exports zero channels, not a fabricated spectral observation. The
actual spectrum widget continues to load the measured spectrum endpoint.

Catalogue images use stored artifact URLs and display an unavailable state after
an error. They never request the legacy synthetic coadd or cutout render routes,
and no source-shaped SVG replaces a failed image. Null catalogue measurements
display as unavailable. External report payloads and external dispatch remain
unavailable because the existing generators derive photometry and confirmations
without measured products or a verified reporting adapter.

## ML enforcement and storage

In real-only mode these legacy HTTP products return 501:

- `/catalog`, `/api/motion/catalog`
- `/api/motion/cutout/render`, `/api/motion/spectrum`
- `/api/motion/coadd/*`
- `/api/catalogue/auto-submit`, `/api/motion/catalogue/auto-submit`

Health and genuine detection/search endpoints remain available. The backend
provides the real catalog/spectrum workflow; the legacy catalog handler is
disabled as a whole because it mixes real queries with synthetic counterparts.

New verification and catalogue databases start empty. Automatic fictional
discussion/catalogue seeds, synthetic validation checks, and invented stack URLs
are disabled. Entries without supplied epoch evidence start with zero recorded
epochs instead of inventing three visits. Posting a comment does not automatically
create a catalogue candidate with placeholder measurements. Use fresh demo data volumes; the switch does not erase historical
rows from an existing database. Genuine newly submitted user records are retained.

## Verification

From `frontend/`:

```sh
node --test tests/real-only.unit.mjs
VITE_DEMO_REAL_ONLY=true npm run build
VITE_DEMO_REAL_ONLY=true PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome npm test -- tests/real-only.spec.ts
```

From `ml/`, using the shared scientific Python environment:

```sh
PYTHONPATH=.. /home/usatovpavel/edu/UtilsAI/.venv/bin/python -m unittest test_real_only test_service
```

The real-only checks cover missing measurements, empty discussion responses,
offline fallback, rejection of synthetic HTTP products, fresh empty databases,
real coordinate requests, and unavailable catalogue images. Version 2 mock mode
is not implemented by this change; it must only follow the completed version 1
image and requires explicit mock labeling.
