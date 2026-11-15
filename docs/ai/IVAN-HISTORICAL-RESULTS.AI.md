# Historical motion support: implementation and real-input verification

This is the second, separate support PR after frontend archive/date PR #32. It connects the existing archive acquisition and image-preparation contracts to Ivan's `ml/service.py` and `science/motion/review.py`. It does not resume the stopped model research, train a model, change a released model, or overwrite the frozen discovery comparison.

## Supported path

The first qualified source is the author's time-resolved **unWISE neo11 W2 visit coadds**, including real 2010 and 2024 observations. These are visit coadds, not individual exposures or continuous yearly coverage. The mission gap remains visible. CADC/HST browsing and other unsupported products remain ineligible for this motion adapter.

Discovery uses `/api/archives` and `/api/observations-search` with provider `unwise-neo11` and actual UTC interval overlap. It is metadata-only and reports bounded atlas search/truncation. Download uses selected server observation IDs through `/api/observations-download`, preserving science, inverse variance, coverage and contributor-table assets as four related files per epoch. Generic `analysisEligible` remains false: explicit product qualification controls the historical path.

`/api/image-unifications` accepts completed science asset IDs. Scala resolves matching companions from the same observation and snapshots every input with its checksum. The worker's explicit `unwise` adapter validates native band/release/epoch, calibration, contributor times, coverage, and full undistorted TAN WCS agreement. It prepares a common sky grid at native 2.75 arcsec/pixel. The existing pickle-free NPZ format preserves physical flux, variance, footprint, real elapsed hours and actual observation dates.

`POST /api/motion/search` accepts `{"unification_id":"UUID","profile":"stellar_proper_motion"}`. Scala leases and streams the checksum-pinned artifact to the configured Ivan origin. Ivan's private `/internal/motion/prepared` validates the bounded stream and qualified bundle before calling the existing review with `forest=None`. No public caller provides filesystem paths or acquisition URLs. The fixed profile is **0.1–30 arcsec/year**, converted to pixels/hour using actual sampling and 8766 hours/year. Detection and ranking receive no known-object trajectory. Returned sky positions use the actual target WCS; legacy SPHEREx coordinate behavior remains intact.

The frontend's **Find historical motion** action prepares the selected epochs and calls this route through the existing same-origin `/backend` proxy. It displays the real returned frames, track overlays, dates, yearly speed, provenance and unavailable-quality information. Unsupported products do not acquire fabricated SPHEREx detector/channel labels.

## Actual runtime and original files

Verification ran the actual frontend, Scala backend, processing worker and Ivan HTTP service locally, on ports 18203, 18200, 18202 and 18201 respectively. This is local development-source QA, not an immutable executed-image attestation or a claim of production deployment. The ML Docker source scope and isolated staged-runtime import/HTTP checks passed; an actual container build is left to CI because the local Docker daemon was inaccessible.

Two fixed natural-object fields used epochs **0, 1, 4, 8, 12, 15, 21, 22** selected before inference. Each field acquired 32 original files for eight visits. All **64 files, 394,851,812 bytes**, were independently rehashed against the completed download response. Original FITS products remain in the private runtime's managed cache; small raw API responses, source URLs, checksums and receipts are committed under [`ml/pvusatov/support/historical/evidence`](../../ml/pvusatov/support/historical/evidence/). No raw image archive or prepared cube is added to Git.

| Field | Actual visit midpoint span | Blind HTTP result | Separate published-astrometry audit |
| --- | --- | --- | --- |
| WISE 0855-0714 | 2010-05-04 to 2024-04-17 | Six returned candidates | Recovered at rank 1 in all eight epochs; maximum residual 2.887 arcsec against the fixed 4.125 arcsec criterion. Returned motion 8.174 arcsec/year; published linear total 8.090 arcsec/year. |
| The Accident | 2010-02-13 to 2024-02-14 | Twenty returned candidates | Not recovered among the returned candidates. Full comparison counts are 24 leave-one-out and 21 shared-median candidates; no claim is made about omitted candidates or the cause. |

Published truth is read only by the separate post-inference audit. These targeted known-object checks are not new discoveries or a population-completeness measurement. No injected stars or training examples serve as this acceptance evidence.

The real browser check independently completed discovery, selection of eight visits, download, preparation and Ivan review. It decoded three displayed image panels without page errors and verified real 2010–2024 dates and yearly units. Its default five-arcminute field uses 110×110 pixels, whereas the two HTTP checks used 128×128; candidate counts need not match across these different fields. The actual browser response, request receipt and screenshot are retained in `evidence/browser-wise0855/`.

Two initial preparation failures are preserved in `evidence/preparation-attempts/`. Actual author `frames.fits` products have three table HDUs and byte-valued inclusion flags. Compatibility fixes select the unique exposure table by schema and use the author's `included > 0` rule. Both failures happened before inference. Later browser-helper failures involved the unit glyph, newly collapsed date controls and receipt logging; they did not change product inference. Their local attempt directories remain preserved.

## Scientific and operational limits

- W2 flux uses the nominal Vega zero flux 171.787 Jy and MAGZP 22.5: one native unit is 0.171787 microJy. Variance uses the squared conversion divided by native inverse variance. No source-spectrum color correction is applied.
- Native `MJDMIN/MJDMAX` establish each visit interval; the midpoint approximates its time. `UNW_DATE` is a processing date and never substitutes for observation time.
- Coverage and inverse variance establish usable support; they do not establish absence of artifacts. Per-pixel artifact, outlier and bloom masks are unavailable and remain `None` in Ivan's consumer. Native `-m` denotes upstream outlier rejection.
- Native scan-dependent W2 PSFs are not homogenized. Nominal FWHM is 6.4 arcsec. WCS registration is not independent stellar-centroid refinement; interpolation covariance is not modeled.
- Only same-tile, same-release, same-band qualified sequences enter this adapter. No HST eligibility, cross-instrument homogenization or annual-coverage promise is implied.
- The new path advertises its own Ivan health capability. Older healthy service images cannot silently masquerade as supporting prepared historical motion. `IVAN_ML_BASE_URL` configures the fixed private origin; Compose supplies the host gateway.

## Validation

- Scala suite after integrating main `2b43019` and its IRSA mirror changes: **293 passed, 0 failed, 4 optional tests ignored**, including the actual Scala-to-Python prepared-bundle fixture.
- Image preparation: **74 passed, 1 existing Codex-detector roundtrip deselected**. Run with repository `pipeline` on `PYTHONPATH`, as the real worker subprocess imports `unification.worker`; an initial root-directory invocation without that path failed the subprocess test and was corrected without product changes.
- Ivan service/preparation transport: **48 passed**. Motion review/profile/preparation regressions: **42 passed, 1 forest-training test deselected**, plus two subtests.
- Frontend: **66 Playwright tests passed** and TypeScript/Vite production build passed. Existing large-bundle warning remains.
- ML source-scope/staged-runtime checks: **5 tests passed, 9 subtests**. No extra research files enter the service image.
- Complete native science-to-auxiliary WCS agreement: **32 actual pairs passed**. Regression tests reject inconsistent celestial reference frames and pole metadata; distorted inputs are unsupported. Independent science re-review confirmed the WCS finding resolved.
- Independent runtime review found no blocking issues. Real HTTP and browser results and the separate natural-object astrometry audits are preserved beside the implementation helpers.

The final integration preserves main's IRSA mirror initialization, discovery/status routes and archive gateway alongside historical motion. Its new ML gateway dependency is included by exact Docker context and source-scope exceptions. The integrated Scala suite, frontend production build and isolated ML runtime smoke passed; independent review of both merge resolutions found no dropped functionality. The 66-test frontend run predates main's small IRSA advisory UI addition; the integrated frontend build was checked again.

No GitHub test workflow was polled or awaited. This PR does not merge or deploy to production.

## Primary product references

- [Author neo11 release and atlas](https://portal.nersc.gov/project/cosmo/temp/ameisner/neo11/).
- [Author coadder implementation](https://github.com/dstndstn/unwise-coadds/blob/master/unwise_coadd.py), including positive contributor inclusion flags and native visit bounds.
- [IRSA WISE photometric calibration](https://irsa.ipac.caltech.edu/data/WISE/docs/release/All-Sky/expsup/sec4_4h.html).
- [Astropy complete Wcsprm comparison](https://docs.astropy.org/en/stable/api/astropy.wcs.Wcsprm.html), with no comparison relaxations enabled.

The previously frozen comparison remains at `/home/usatovpavel/playground/hackaton/docs/ai/ml-real-discoveries-ivan-vs-codex.AI.md` and its benchmark directory. It is preserved independently of these new runtime receipts.
