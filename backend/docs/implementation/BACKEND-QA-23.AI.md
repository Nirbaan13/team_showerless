# Backend response integrity follow-up to PR 23

The historical QA report remains in PR 23. This change addresses the Scala/API
boundary and deployment wiring; it does not fix all 19 UI findings.

## Supported topology

Frontend nginx routes `/api/motion/*` and `/api/catalogue/*` to Scala on the host
API entry point instead of the missing port-8001 service. No additional Python
service or synthetic legacy renderer is deployed. No frontend TypeScript,
Sienna processing, or model implementation is changed. The domain stays on
Hostinger; no DNS action is part of this change.

- `/api/motion/catalog` queries real TAP rows in Scala. Gaia DR3 and AllWISE use
  VizieR; SIMBAD uses the Harvard mirror recommended by CDS during its current
  service incident. Each returned source names its provider URL. CDS states that
  Harvard's snapshot contains data ingested through 2026-10-14; a live query does
  not imply a current-day observation.
- Unknown brightness and proper motion remain null. Successful empty results
  remain empty. Individual failures remain visible in `providers`; partial
  success is labelled `partial_agency`. All-provider failure is HTTP 503 with
  empty source lists and per-provider errors. No ephemeris is generated.
- TAP requests have a six-second deadline, one-MiB response limit, at most eight
  rows per provider and four concurrent query groups. Coordinates and duplicates
  are validated before outbound requests. No user can select a remote URL.
- `/api/capabilities` distinguishes worker availability, installed inference model
  metadata/score semantics, unsupported native-FITS subtraction, unsupported
  legacy/community endpoints, and disabled external submission. Container health
  alone is not archive or scientific-product readiness.
- The installed durable `/api/analyses/motion` remains the supported ML interface.
  Retired synchronous `/api/motion/search` and generated-image legacy endpoints
  return explicit HTTP 501 JSON with the supported analysis URL.
- Community catalogue/verification persistence was owned by the missing legacy
  service and is not reimplemented here. Those legacy calls fail explicitly;
  there is no claimed successful persistence or fabricated consensus.
- Automatic submission and submission-record writes return HTTP 403 before any
  side effect. Client-provided confirmation counts cannot authorize publication.
- Processing errors retain the upstream HTTP status in their stable public
  message. Existing retriable IRSA failures and download manifests are preserved.

The deployment workflow now checks actual worker availability, installed model
metadata and routing of the UI catalogue request, as well as the revision. The last of the two independent VPS deployments also checks the catalogue route
through frontend nginx once both revisions match. It does not wait for
asynchronous test CI or external TAP availability.

## QA mapping and remaining responsibilities

| Finding | Backend disposition |
|---|---|
| QA-001 | Real failed downloads remain failed; no synthetic backend success. UI fallback was separately removed in PR 22. |
| QA-004 | Client-seeded publication is rejected; real authenticated consensus/publication remains unavailable. |
| QA-005 | Dead upstream removed; supported catalogues reach Scala. Retired workflows return explicit unavailable responses, not a pretend replacement. |
| QA-006 | External IRSA failures remain retriable and distinct from empty coverage. The external incident cannot be fixed by repository code. |
| QA-007 | Capabilities distinguish unsupported native modes from installed inference products. UI gating still needs frontend work. |
| QA-010 | No invented frame measurements are added. Existing observation metadata endpoint remains authoritative; frontend HUD literals are outside scope. |
| QA-011 | Server catalogue data have no simulated fallback. Browser fallback generation remains a separate frontend defect. |
| QA-014 | No seeded persistence or consensus is introduced. The community service requires a separately implemented supported backend. |
| QA-018 | Capability response publishes actual installed model metadata; frontend model labels must consume it. |

## Verification and evidence limits

The new HTTP contract tests first failed against main because the capability,
legacy failure and submission-rejection routes were absent. HTTP fixture tests
exercise the actual Scala catalogue transport and controller for empty, partial,
failed, malformed and invalid-input cases. They do not prove provider uptime.
The live Strasbourg SIMBAD endpoint returned HTTP 404 and VizieR reset its TLS
connection during this session; Harvard SIMBAD returned HTTP 200 for the same
coordinate query. Those observations are not claims that all catalogs are online.

Primary service references:

- [CDS incident and official SIMBAD mirrors](https://simbad.cds.unistra.fr/)
- [VizieR TAP syntax and quoting](https://tapvizier.cds.unistra.fr/adql/about.html)

The full Scala suite passed: 240 tests, zero failures and four explicitly skipped
live tests; staging succeeded. The final targeted suite passed all 20 tests. A
local run of the staged Scala API queried RA 250°, Dec 10° and returned one real
SIMBAD row with `partial_agency`, separate Gaia/WISE failures, and no fabricated
ephemeris. With an intentionally absent worker it reported `available: false`.
These are local validation results; this branch is not deployed yet.

Commands: `./backend/sbtw test stage`, `actionlint .github/workflows/ci-deploy.yml`,
and `git diff --check`. Test CI is not awaited.
