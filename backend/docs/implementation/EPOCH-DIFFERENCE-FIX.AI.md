# Honest epoch-difference states for custom coordinates

## Confirmed failure

The persisted250deg,10deg request failed with archive_timeout and zero chunks.
The viewer swallowed errors, abandoned pending analysis after18seconds, generated
five mock epochs and synthetic candidates, and labeled the result as a live NASA
stream. The canvas also painted a procedural sky whenever the selected image
was missing or still loading. Candidate coadd evidence was separately generated
in the browser instead of using the returned assets.

## Resulting behavior

A custom field clears previous observations/candidates and follows the actual
backend download manifest to a terminal state. Only successful native downloads
are passed to analysis. Terminal errors preserve their code/message. An analysis
that is still running remains pending until completion, failure or cancellation
by another user action; there is no18second successful-fallback path.

Only returned frames and candidates populate the live viewer. A failed download
has no epochs, no successful stream/ML indicator, and no implied zero-motion
result. Image load/failure is explicit per layer. Missing/failed difference
images state that motion cannot be assessed. Async image completion repaints the
canvas; Refresh retries failed URLs even when the backend deduplicates the job.

Free-coordinate submissions always query their own field. They cannot borrow a
nearby benchmark from the former0.25/0.85degree match windows. Packaged benchmarks
remain available through explicit preset selection, including3I/ATLAS differences.
Custom verification targets use the same lifecycle with their own FOV/detector;
preset verification cancels pending work and restores an explicit preset status.

Candidate stacks use actual returned URLs or explicit unavailable states.
Procedural coadd stamps and invented stack S/N/winner claims were removed.
This fixes evidence presentation, not external IRSA availability or scientific
qualification of other surveys. Existing scientific metadata/classification
conventions outside these failure/evidence paths are a separate concern.

## Verification

- Original browser suite: five regressions failed; the real3I/ATLAS packaged
  difference control passed. Five subsequent review regressions also failed
  before their fixes.
- Clean npm ci, lint, TypeScript/Vite production build and13browser regressions
  passed on the installed Playwright1.65.1 Chromium159.0.8154.6. The same cases
  also passed using local Google Chrome. Lint exits0; React lint and bundle-size
  warnings remain.
- Tests cover archive_timeout, prolonged pending analysis, valid difference
  assets, missing URLs, failed bitmap HTTP requests, retry, nearby custom fields,
  custom and preset verification, actual/missing stack assets and HTML returned
  by a misrouted static-site API. HTTP fixtures replace only the external API;
  the real production application, canvas and packaged benchmark PNG are used.
- Independent review findings were fixed and rechecked; no material finding
  remains in this scope.

A live browser check replayed the actual acceptance ID for persisted download
0c7813f6-2c7b-472c-9e82-314e367ccf71, then fetched its status from the VPS through
the normal API proxy. It displayed archive_timeout, zero ready/fabricated epochs,
and started no doomed analysis. Screenshot/proof were retained locally. This
check reuses the real failed status without initiating another archive transfer.

## Running viewer regressions

```sh
cd frontend
npm ci --no-audit --no-fund
npx playwright install chromium
npm run lint
npm run build
npm test
```

For a local system browser, set
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome when running npm test.
The frontend CI installs Chromium with system dependencies and runs the suite
before building/deploying its container. Browser output directories are ignored.
The setup follows the official [Playwright web-server](https://playwright.dev/docs/test-webserver)
and [HTTP boundary mocking](https://playwright.dev/docs/mock) documentation.
