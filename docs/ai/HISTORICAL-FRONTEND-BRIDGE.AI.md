# Historical motion frontend bridge

This change builds on the archive/date frontend PR. It adds the historical action to the existing archive panel without changing `App` props or the ordinary viewer flow. Select `unwise-neo11`, apply the actual sky coordinates and observation period, select at least three distinct epochs of one qualified W2 tile, and complete their native download. The action is named **Find historical motion**.

## Public transport

All new requests use the same-origin `/backend` Scala proxy. The browser submits `POST /backend/api/image-unifications` with only the downloaded science asset IDs (`AssetOutcome.provenance.asset_role == "#this"`). It does not send source URLs or auxiliary asset URLs. Backend associates the required variance, coverage and contributor metadata with each selected science observation. The browser follows the returned `status_url`, retaining its query string, until completion or failure. A completed unification is submitted to `POST /backend/api/motion/search` using only `unification_id` and `profile: "stellar_proper_motion"`.

Selection checks require backend observation eligibility, available native image products, verified real observation intervals, native `neo11` release, W2 band, 2.75 arcsec sampling, one tile and unique epochs. Each observation requires one ready science asset and one ready associated product for each of `#inverse-variance`, `#coverage` and `#contributors`. Generic `StoredAsset.analysisEligible` remains false by design and is not used to block qualified observation records. Preparation still checks pixel, calibration and coverage qualification. CADC and SPHEREx inputs remain disabled for this historical action.

## Geometry and review

The preparation grid derives its square width from the viewer's applied `ArchiveQuery.fovArcmin`: `ceil(width_arcmin × 60 / 2.75)` pixels, capped at 512. The input is field width, not metadata-search circle radius. The panel displays requested width, actual result width and native sampling. If the cap applies, the UI explicitly says the result covers only the central field.

The existing `MotionField` renderer is reused directly for actual historical responses. It displays aligned/residual PNGs, full UTC dates, unWISE W2 identity and backend-supplied proper motion in arcsec/year. Null outlier evidence remains unknown in the UI and exported candidate JSON. The historical result never passes through the SPHEREx epoch/detector conversion and has no saved-benchmark fallback. Backend preparation limitations and warnings remain visible. Empty tracks are displayed as empty tracks.

The historical child resets when the applied query, selected observation IDs, or download job changes; unmount aborts pending preparation/inference. Preparation and inference progress, cancellation, real failures and a bounded timeout are visible. A late response from a previous query cannot populate a new field.

## Verification scope

`frontend/tests/historical-motion.spec.ts` uses HTTP protocol fixtures only. These tests do not claim astrophysical detection or real-pixel ingestion. They verify science-asset selection, exact preparation and inference payloads, server polling links, yearly speed and null quality export, incompatible tiles, missing science assets, preparation failures, empty results and aborting pending work when the field changes.

Commands from `frontend/`:

```sh
npm run build
npm test
```

Existing dependency artifacts are reused through an ignored `node_modules` symlink; no packages are installed by this change. Real archive transfer, processing and frontend-to-Scala-to-Ivan acceptance are separate runtime checks recorded by the integration owner.

The TypeScript/Vite build passed and the complete frontend Playwright suite passed **66 tests**, including the historical protocol checks, after integrating the archive/date frontend changes. An independent read-only frontend contract review found no significant correctness issues. The integration owner also verified the real browser-to-Scala-to-Ivan flow; its actual image and request evidence is described in `IVAN-HISTORICAL-RESULTS.AI.md`.
