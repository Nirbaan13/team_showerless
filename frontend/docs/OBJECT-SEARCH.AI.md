# Named object search

The square magnifier beside **Update Field** opens a small searchable object
list. Selecting an object immediately applies its reference coordinates and
searches the currently selected archive and observation period. The field of
view and detector remain unchanged. Arrow keys and Enter select an item; Escape,
Tab out, or a click outside dismiss the list without a search. Unknown names
remain an empty list.

Object requests use the existing backend acquisition flow. The normal loading,
empty, archive failure, download, and analysis states remain authoritative.
Selecting an object, refreshing it, or switching its detector cannot silently
turn the request into a stored benchmark. A selected object's identity is kept
in `object=<id>` alongside coordinates, archive and date URL parameters. On
reload the field is restored; Refresh starts a new search. Applying manual
coordinates clears the object identity.

## Object data and provenance

Ten named fields are included: Barnard's Star, RW Aurigae, R Draconis, Wolf 28,
LAWD 37, 40 Eridani B, G 221-5, Epsilon Indi B, WISE 0855-0714, and
2MASS J02511490-0352459. Names and aliases filter a local finite list; this is
not a general external name resolver.

The reference positions are the published epoch **2025.9** query centers in
[the source target list](https://github.com/FearmessOp/blackhole-spherex/blob/c1c45570332d73d57b91aec34b6b0ed08ddcc999/data/targets.json).
Saved IRSA observation lists are in [the source data directory](https://github.com/FearmessOp/blackhole-spherex/tree/c1c45570332d73d57b91aec34b6b0ed08ddcc999/data/sia).
The source is an independent public project containing saved IRSA responses,
not an official maintained IRSA object catalog.

On 2026-11-15, one original NASA S3 FITS header was checked for each included
object using a bounded HTTP Range request. All ten selected examples returned
HTTP 206, contained an IMAGE HDU, and placed the reference target coordinates
inside the detector according to the FITS WCS. That verifies field coverage,
not source detectability, photometry, every listed exposure, or a complete
download. The lists contain 2,799 DR1 rows in total.

These positions are fixed reference fields. This picker does not propagate
proper motion, parallax, or moving-object ephemerides to arbitrary selected
dates. A narrow historical field can therefore miss a high proper motion star.
The reference epoch is shown in the dropdown. Source coordinates have not been
independently rederived from the underlying astrometric catalog.

## Backend boundary

No backend discovery, FITS delivery, metadata ingestion, or mirror crawler is
changed here. During an IRSA outage, useful results still require coverage in
the backend mirror index and successful FITS delivery. The frontend does not
equate a known name or saved manifest with downloaded image pixels. The backend
owner has the observation-list sources for independent catalog ingestion.

## Validation

The Playwright object-search tests exercise the actual application with the
remote API boundary controlled: object-to-coordinate requests, archive/date
preservation, keyboard and pointer dismissal, empty names, date validation,
refresh and detector behavior, URL restoration, manual coordinate reset, and
mobile layout. Protocol fixtures are not evidence of real scientific results.

Before this change, the full frontend suite had 55 passing and five failing
tests: two provenance-display assertions in `epoch-difference.spec.ts` and all
three `qa-spectrum.spec.ts` tests, whose tab clicks were intercepted by the
drawer expand button. These failures must be reported separately from the new
feature's validation; a full-suite-green result is not implied.

Final local checks:

- `npm run build`: passed; Vite reports the existing large bundle warning.
- `npm run lint`: passed with existing repository warnings.
- Full `npm test -- --workers=3`: **61 passed, 5 failed**. All six new
  `object-search.spec.ts` scenarios passed; the same five baseline failures
  remained. The complete run used a separate output directory.
- Independent read-only review found an `all` detector identity/coordinate
  mismatch. A regression test failed against that behavior, then passed after
  applying coordinates before the unsupported-composite early return. The
  reviewer confirmed the finding resolved.
- Desktop and fresh 390px mobile screenshots were inspected. The trigger is
  36 by 36 CSS pixels and the dropdown stays inside the control panel.

Unchanged failing tests, by name:

1. `stored benchmarks disclose provenance without pretending to run a new model`
2. `live analysis displays the returned model family, ID, score meaning and server ranking`
3. `QA-002 failed measurement never enables exporting generated science`
4. `QA-002 measured export contains only returned channels and retry failure clears them`
5. `QA-002 empty measured channels and molecular detections remain empty`
