# Archive and observation-period selection

## User workflow

The existing era shortcuts and multi-archive search from PR 28 are consolidated
into this single validated Update Field form, rather than a second independent
query with stale coordinates. The existing shared federated search client is
reused and validates its JSON response. Era labels describe observation windows,
not a claim that WISE images or pre-launch SPHEREx observations are supported.

The Update Field form applies coordinates, archive and observation
start/end dates together. Choices come from `/api/archives`; unavailable,
unqualified, non-image and non-deliverable providers are identified in the menu.
Provider time-filter capability and restrictions remain visible.

The existing undated IRSA/SPHEREx live-analysis path is preserved. Choosing another
provider or specifying observation dates selects the common metadata-only archive
workflow. SPHEREx detector and subtraction controls are disabled for that workflow;
HST pixels are never relabelled as SPHEREx detector data.

- Search: `/backend/api/observations-search`, with a cone that encloses the actual
  requested square FOV. Angular width is not reused as radius.
- Dates are observation UTC, not release/modification time. The inclusive UI end
  date becomes midnight at the start of the next UTC day. Invalid date ordering
  is rejected before a query; there is no 2010 lower-bound restriction.
- Search does not download images. Each provider's status, warnings, completeness
  and continuation indicator is shown, including HTTP-200 provider failures.
  Truncated/unknown results are explicitly incomplete.
- The user selects returned server observation IDs. Only that selection is posted
  to `/backend/api/observations-download` with original delivery. Polling follows
  the returned status URL, preserving its query string. Resource links also come
  from the manifest and retain the configured API proxy prefix.
- A native link appears only for a ready chunk. A preview requires both a ready
  native chunk and an advertised ready preview; otherwise its unavailable/pending
  state is explicit. Actual preview load errors remain errors.
- Observation IDs/timestamps/instruments come from server records. Generic archive
  records do not become invented `SpherexEpochFrame` objects. No generic product
  is sent automatically to the SPHEREx-only inference reader. Record and final
  asset eligibility are respected individually; future eligible records are not
  hardcoded ineligible, and eligibility is not presented as a completed analysis.
- New requests/presets cancel stale search/download polling and clear old archive
  selections, products and results. Source/dates persist in the share URL, reload,
  iframe snippet and full-app link. Reload preserves the target coordinate and
  starts with no restored benchmark candidates or pretend acquired products.

This PR changes frontend files only. Historical ML qualification and integration
remain PR 2, owned by the existing Ivan-service support session.

## Live validation and exact limits

The current deployed OpenAPI and archive inventory were fetched before coding.
A real CADC query around RA 53.1625°, Dec -27.7914°, radius 0.01°, observed between
1990-01-01 and 2010-01-01 returned 100 records with `completeness=truncated`.
Among them were real HST NICMOS/NIC2 observations dated 2002-10-10, including:

- `ivo://cadc.nrc.ca/mirror/HST?n8g6k7duq/n8g6k7duq-CALIBRATED`, observed
  `2002-10-10T14:53:27.112999678Z`, `analysisEligible=false`.
- `ivo://cadc.nrc.ca/mirror/HST?n8g6i8eiq/n8g6i8eiq-CALIBRATED`, observed
  `2002-10-10T17:42:27.110000134Z`, `analysisEligible=false`.

The built frontend was then exercised in a real browser through its normal
`/backend` proxy to `http://144.124.238.101`, without stubbing the archive search,
selection or download manifest. A 1-arcmin field with UI dates 1990-01-01 through
2002-12-31 sent an enclosing radius of 0.011785112936675083 degrees and exclusive
upper bound 2003-01-01T00:00:00Z. It returned 100 truncated observations including
HST/ACS data from October 2002. Exactly the checked server ID was submitted.

The selected HST product's original download **failed** with
`ambiguous_science_asset`: its DataLink contained multiple science originals.
The interface displayed 0/1 ready, the actual error, unavailable preview and no
ML run. This proves the error/selection integration, not successful FITS transfer,
image display or historical ML. The ready-file/preview paths are separately
covered with explicit HTTP protocol fixtures in Playwright.

Machine-readable live evidence: [archive-period-live-proof.json](evidence/archive-period-live-proof.json).
[Live browser screenshot](evidence/archive-period-live.png) shows the actual failed
native transfer and unavailable preview without a substituted scientific image.
An earlier narrow-day live request returned a gateway error; neither that failure
nor the truncated results were interpreted as complete empty coverage.

## Concrete dependencies and boundaries

1. Backend/Processing must expose a qualified preview/render resource for a
   downloaded archive asset, publish its real readiness and image URL, and retain
   the associated observation identity/time. Current common archive manifests
   advertise `preview_status=unavailable`, and their preview route returns HTTP409
   `preview_unavailable`. A FITS URL or a ZIP unification bundle is not a display
   bitmap and is not used as one by this UI.
2. Some original-delivery records require a qualified per-artifact selection to
   resolve multiple science originals. The frontend currently requests original
   delivery only. Existing advertised cutout delivery or another unambiguous
   product can be considered separately; this PR does not claim that the backend
   delivered the particular failed HST product.
3. Historical processing needs an explicitly qualified instrument/band/time/mask
   adapter through Ivan's existing stack in PR 2. Current CADC records remain
   ineligible. Changing a date or a boolean in the browser does not qualify them.
4. Live validation used the VPS API through a local production preview. It is not
   a claim that the unmerged branch is deployed or that Hostinger API routing is
   configured. This PR does not change DNS, hosting, backend or Python code.

## Verification

New Playwright coverage exercises UTC inclusive bounds/leap day, radius, invalid
order, actual selected IDs, pending/ready file links, server-provided polling URLs,
provider failures, unsupported filters, empty/truncated results, ready/unavailable
preview states, per-record eligibility, clearing stale results, share/reload
coordinates and embed links. Existing native SPHEREx tests remain enabled.

Latest main's public API delivery and scientific-provenance repair (PR 30) was
also retained. Its native All Bands guard is scoped to native processing so it
cannot block CADC browsing. That integration regression was reproduced before
the fix and passed afterward.

Verification: the full suite on the latest integrated main passed **57 tests**.
After the final one-condition guard fix, all **14 archive-period tests** and the
existing native All Bands control test passed. The final lint and production
build passed; existing React lint and bundle-size warnings remain. Independent
review found no remaining material issues. One parallel local attempt collided
in Playwright's shared trace directory; the final archive rerun used an isolated
output directory and passed.

Commands: `npm --prefix frontend run lint`, `npm --prefix frontend run build`,
`cd frontend && npm test`, and `git diff --check`. CI tests are asynchronous and
are not awaited. Deployment is not requested by this PR.
