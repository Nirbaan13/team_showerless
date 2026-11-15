# Ivan historical observation support

This implements the user-directed second PR. The independent model/research task is stopped. The first frontend archive/date PR remains separate. Detection and heuristic ranking stay in `science.motion.review`; no retraining, new ranker or synthetic discovery acceptance is part of this change.

## Qualified initial product

Use the author's time-resolved unWISE `neo11` W2 visit coadds. Actual FITS `MJDMIN/MJDMAX` establish observation intervals, including real 2010 and 2024 products and the intervening mission gap. Epoch numbers and processing dates never substitute for observation times. Discovery is not proof of downloaded pixels or successful analysis.

Use the existing `/api/archives`, `/api/observations-search`, `/api/observations-download` and `/api/image-unifications` workflow. Add an explicit `unwise-neo11` provider with bounded cached atlas/header metadata and truthful completeness. One observation is one release/tile/band/epoch; science, inverse variance, coverage and contributor metadata are related assets, not independent epochs. Unsupported instruments, bands, geometry or calibration remain explicitly ineligible.

The initial adapter requires the same qualified W2 release/band and native 2.75 arcsec sampling. It reads separate science, inverse-variance and coverage products, preserves checksums and actual times, and declares unavailable artifact/outlier/bloom masks. It never creates SPHEREx HDUs or bits. Calibrated physical flux and variance must use the documented Vega conversion consistently; an AB nanomaggy conversion is inappropriate. Common-grid interpolation must retain its variance/coverage semantics and state the PSF/astrometric qualification limits.

## Preparation contract

Public unification inputs continue to select a completed science `archive_asset` ID. Backend resolves associated, completed assets from the same server observation record and snapshots every file with its checksum. The internal schema-v1 input uses profile `unwise` and optional `auxiliaries`:

```json
{
  "profile": "unwise",
  "auxiliaries": {
    "inverse_variance": {"id": "server-asset-id", "path": "unifications/JOB/inputs/FILE", "sha256": "HEX", "bytes": 123},
    "coverage": {"id": "server-asset-id", "path": "unifications/JOB/inputs/FILE", "sha256": "HEX", "bytes": 123},
    "contributors": {"id": "server-asset-id", "path": "unifications/JOB/inputs/FILE", "sha256": "HEX", "bytes": 123}
  }
}
```

Paths are managed snapshots, not client URLs. Primary and auxiliary checksums and physical identities must agree before and after decoding. Missing or mismatched required products fail qualification. Existing generic/SPHEREx inputs remain compatible.

The existing bounded pickle-free NPZ retains physical images, validity, footprint, variance, actual elapsed hours, UTC dates, observation identities and provenance. Unknown quality-mask placeholders in this transport must be interpreted through their explicit `*_known` metadata and become `None` at Ivan's consumer.

## Ivan service and runtime bridge

The documented Scala `/api/motion/search` accepts a completed `unification_id` and the named `stellar_proper_motion` profile for this path. Scala leases and streams the managed NPZ to Ivan's prepared-input operation at a fixed configured service origin. The ML operation does not discover or download archives and accepts no caller-supplied acquisition URL. Its adapter uses the existing NPZ validator and calls Ivan's `build_review(..., forest=None)`.

The profile is 0.1–30 arcsec/year converted using the actual grid scale and 365.25×24 hours/year. Existing times remain real elapsed hours. Coordinates only select the requested field/grid; known-object trajectories never enter detection or ranking. The response preserves native dates, band, profiles, preparation limitations and instrument-specific unavailable evidence.

The ML image must contain the actual adapter and NPZ loader; separate containers must not assume shared local paths. Verify the processing worker and the deployed frontend→Scala→Ivan route explicitly. CADC/HST browsing remains separate and ineligible for this first qualified motion path.

## Acceptance

Preserve the existing frozen real-discovery evidence without edits. Obtain real `neo11` science/variance/coverage inputs for WISE 0855 and a second known-object field, including genuine 2024 observations. Record raw response metadata, source checksums, selected actual dates, preparation and blind service results; evaluate known astrometry separately afterward. Keep misses and unavailable products visible. Existing infrastructure tests may use analytic fixtures, but the historical acceptance uses actual pixels through acquisition, preparation, backend and Ivan's running service.

Open a separate reviewable PR after the frontend archive/date PR. Do not push directly to main or include stopped research changes.
