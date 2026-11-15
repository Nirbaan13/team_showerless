# Real archive data for the portable demo

`real_sources.json` is a checksum-pinned source lock.
`bootstrap_real.py --output SEED_DIR` downloads the exact native NASA/IPAC IRSA
cutouts in that lock into `api-data/demo/` and `ml-data/demo/`. The root
`provenance.json` and both `demo/manifest.json` files retain source URLs,
SHA-256, byte counts, detector identities, and actual FITS observation dates.
No image arrays or large generated artifacts are stored in Git.

Use the existing scientific environment for reproduction:

```sh
/home/usatovpavel/edu/UtilsAI/.venv/bin/python ops/demo/bootstrap_real.py --output /tmp/spaceapps-demo-real-data/seed
/home/usatovpavel/edu/UtilsAI/.venv/bin/python ops/demo/bootstrap_real.py --output /tmp/spaceapps-demo-real-data/seed --verify-only
/home/usatovpavel/edu/UtilsAI/.venv/bin/python -m unittest ops/demo/test_bootstrap_real.py
```

The second command performs no network requests. It verifies every pinned copy,
including FITS structure, SHA-256, byte count, native detector, `DATE-OBS`, and
actual WCS coverage. A finite inverse WCS result is insufficient: strict SIP
convergence and a forward celestial roundtrip are required. This rejects
Astropy's finite but invalid best iterate after a divergent inverse.

## Acquired preset fields

| Field | Detector | Native frames | Actual UTC dates |
| --- | ---: | ---: | --- |
| Barnard's Star | 2 | 9 | 2025-08-21, 2025-08-25, 2025-08-29 |
| WISE 0855-0714 | 5 | 4 | 2025-05-06 |
| Epsilon Indi B | 3 | 2 | 2025-11-01, 2025-11-03 |
| RW Aurigae | 4 | 1 | 2025-09-01 |
| R Draconis | 6 | 6 | 2025-05-06, 2025-05-16 |
| 3I/ATLAS, additional case | 6 | 4 | 2025-12-14 |
| Vesta, additional case | 6 | 3 | 2025-08-04, 2025-08-05 |

The stellar requests use 0.2° (12′) native cutouts. Most have 117×117 pixels.
The Barnard frame on August 21 and RW Aurigae frame on September 1 meet a
native detector edge; they retain their actual clipped dimensions and WCS.
`native_edge_clipped` records this in the lock. No pixels are padded, simulated,
or stretched to claim a full field. WISE currently has one observing date;
RW Aurigae has one frame and Epsilon Indi B has two. Their seed does not claim
three independent epochs or enough data for a three-frame stack.

`api-data/irsa-mirror.sqlite` contains the original native S3 metadata rows,
including the actual full-image spherical footprints and observation times.
All release completeness flags remain false because this is a targeted demo
index, not a complete archive crawl.

## Availability and interpretation

All five stellar presets are represented with their exact frontend query
coordinates and recommended detector. `discovery_unavailable` means the archive
search failed or targeted metadata discovery remains incomplete. It never means
that no SPHEREx coverage exists. `no_coverage` is reserved for a successful,
complete archive query establishing that result. No failed query is converted
to blank or fabricated science data.

Reference coordinates are query centers. Covering a preset field is not an
independent detection or a confirmation that a moving star occupies its catalogue
reference position at that date. No epoch propagation, class label, photometry,
ML score, or catalogue entry is invented. Barnard's Star and WISE 0855 in
particular require authoritative epoch astrometry before scientific identification.

The real 3I/ATLAS D6 and Vesta D6 cutouts are additional fixtures. Their exact
URLs and ephemeris coordinates originate in
`science/motion/cases/observations.csv`. They do not replace missing stellar
coverage. The model and any benchmark simulations are outside this data seed.

## Official archive references

- [IRSA data access and official S3 mirror](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/)
- [IRSA native cutout and metadata query tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts/)
- [IRSA FITS data product documentation](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/)

The acquisition session on 2026-11-15 encountered repeated HTTP 502 responses
from SIA and TAP, including bounded per-target requests and the asynchronous TAP
endpoint. Official S3 listings and bounded FITS header range reads were used to
search candidate exposures; only verified native cutouts are admitted to the
source lock. Candidate scheduling dates are search hints, never observation
metadata. The date and detector in each accepted record come from the native FITS.

## Native field previews independent of motion analysis

The bootstrap also writes `api-data/demo/preview-manifest.json` and 29 PNGs in
`api-data/demo/previews/`. These previews display the available observations even
when a target has fewer than three frames and cannot run a motion analysis.
They introduce no additional epochs or measurements.

Each PNG is an RGBA display conversion of the actual calibrated `IMAGE` HDU.
Astropy `ZScaleInterval` supplies display limits over the finite input pixels;
a clipped linear mapping converts those pixels to 8-bit grayscale. Nonfinite
pixels have zero alpha. Native array row order and dimensions are preserved:
there is no interpolation, reprojection, padding, rotation, vertical flip, or
inserted source. The original FITS remains the scientific data product.

The preview manifest retains exact published preset query coordinates, native
frame IDs, observation times, detector and release identities, original FITS
URLs and SHA-256, preview SHA-256, pixel dimensions, and the rendering method.
`field_only`, `proper_motion_note`, and `discovery_complete: false` prevent a
field image being represented as a confirmed detection or complete archive.
When present, `flagged_pixel_percentage` is measured as `FLAGS != 0`. It includes
informational source flags and is not a fraction of scientifically unusable
pixels. No cosmic-ray count is invented.

`--verify-only` validates manifest cross-references and hashes, checks native
PNG dimensions and mode, and recomputes the expected display pixels directly
from the pinned FITS. Altering PNG pixels remains detectable even if its PNG
hash is changed to match. The test suite uses explicitly synthetic temporary
FITS patterns only for tests; these are never copied to the demo seed.
