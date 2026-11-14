# Multi-archive backend integration

Implemented on `feat/multi-archive-integration`, based on `13d580e`. The independent
`spaceapps.archive` package adds discovery and native-file retrieval without
changing legacy SPHEREx HTTP/gRPC schemas, detectors or `verices_degrees`.

## Contract

The additive HTTP routes are documented in `backend/docs/openai/openapi.yaml`:

- `GET /api/archives`: full inventory, qualified operations and limitations.
- `POST /api/archive-searches`: accept a validated ICRS circle/UTC query; return
  HTTP 202 with `id` and `status_url`.
- `GET /api/archive-searches/{id}?limit=50&cursor=...`: persisted status,
  provider outcomes and local snapshot pagination (maximum page size 200).
- `POST /api/archive-searches/{id}/continue`: body `{"provider":"..."}`;
  resumes only a genuine adapter continuation. Initial production adapters have
  no qualified upstream continuation and return `unsupported_continuation`.
- `POST /api/archive-downloads`: accept server-known `record_ids` and optional
  `delivery` with `mode` and `region`; return HTTP 202.
- `GET /api/archive-downloads/{id}`: per-asset status, typed failures, provenance
  and local artifact URLs.
- `GET /api/archive-assets/{id}`: serve completed native science bytes only.

Example search:

```json
{"region":{"type":"circle","ra_degrees":210.8,"dec_degrees":54.35,"radius_degrees":0.1},"providers":["eso","cadc","nadc-bass","iki-artxc"],"product_kinds":["image","coverage"],"limit_per_provider":100}
```

Example native download request:

```json
{"record_ids":["ID_FROM_SEARCH"],"delivery":{"mode":"require_cutout","region":{"type":"circle","ra_degrees":266.4,"dec_degrees":-29.0,"radius_degrees":0.002}}}
```

UTC bounds must be valid ordered ISO instants. Unverified native clocks cannot
satisfy an exact UTC filter; their independent provider outcome reports
`unsupported_filter`. Catalogue reference epochs are separate from observation
intervals. Missing brightness units, proper motions and wavelengths are omitted.
Gaia source IDs and other native identities remain strings.

ObsTAP records' `original` and `cutout` flags identify provider-level delivery
candidates before per-record DataLink resolution. They do not promise a public
file or a usable SODA descriptor for every matching record. Resolution and the
persisted download outcome qualify authorization, service availability and whether
the selected subset actually contains pixels.

SQLite stores separate `federated_*` tables alongside the existing jobs database.
Queued/running searches and download work survive restarts; completed provider
outcomes and native assets are retained. Local cursors belong to a persisted
snapshot generation and return HTTP 409 when that generation changes. Exhausting
local pages never changes upstream completeness. Continuation deduplicates stable
versioned IDs and accumulates per-provider record counts.

## Qualified providers

| Provider | Discovery | Native delivery | Scientific boundary |
| --- | --- | --- | --- |
| `irsa-spherex` | Existing SIA2 bridge; native frame/release/detector preserved | Original FITS | Legacy processing endpoints remain separate |
| `eso` | ObsTAP footprint intersection and time overlap | DataLink science originals; advertised synchronous SODA circles | Foreign instrument processing unqualified |
| `cadc` | ObsTAP across collections | DataLink science originals; advertised synchronous SODA circles; scoped CANFAR redirects | Foreign instrument processing unqualified |
| `esa-gaia` | Direct ESA DR3 source cone | No image delivery | Source positions and reference epochs only |
| `nadc-bass` | Repeated multipart `showcol`; radius in arcseconds; native date metadata | Unavailable: image host failed DNS in qualification | Image footprint completeness and clock unverified |
| `iki-artxc` | Native region JSON coverage, radius at most 5 degrees | Unsupported: `fits-zip` returned 404 | Indexed days only; not effective exposure; native mission seconds, `mjdref`, provisional clock and mode flags retained |
| `lamost` | Public DR11 v2.0 LRS cone after checking current release status | Original spectra, including native gzip | Spectrum records only; full FITS validation occurs at transfer |
| `iki-artxc-catalog` | Local spherical filtering of official first-year CSV | No image delivery | Survey-aggregated sources, no per-exposure UTC |

`esasky` stays unavailable after maintenance HTML evidence; this does not disable
direct Gaia. `nadc-ast3` remains pending: successful direct FITS access does not
establish working circle/time discovery. `einstein-probe` requires authentication.
`nadc-plates`, `sao-ras` and `erodat` remain pending independent qualification.
Unavailable providers never return a fabricated successful empty result.

TAP requests use `MAXREC`, not a `TOP` sample presented as exhaustive. All query
status markers are inspected; trailing `OVERFLOW` wins over initial `OK`. Shared
XML decoding supports secure bounded TABLEDATA. BINARY/BINARY2/FITS serializations
return `unsupported_serialization`; generalized binary support is not claimed.
CSV parsing preserves quoting, embedded newlines, empty fields and exact strings.
HTML maintenance, empty-200, malformed rows and application errors are failures.

## Transfer and configuration

Defaults and environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ARCHIVE_PARALLELISM` | 3 | Global metadata concurrency |
| `ARCHIVE_PROVIDER_PARALLELISM` | 1 | In-flight metadata calls per provider |
| `ARCHIVE_METADATA_TIMEOUT_MS` | 30000 | Metadata attempt timeout |
| `ARCHIVE_SEARCH_DEADLINE_MS` | 120000 | Whole search deadline including retries/waiting |
| `ARCHIVE_METADATA_BYTES` | 8388608 | Metadata transport byte budget; parsers additionally cap at 8 MiB |
| `ARCHIVE_FILE_BYTES` | 268435456 | Both transferred and decoded native-file limit |
| `ARCHIVE_MAX_ACTIVE_JOBS` | 32 | Admission limit for each archive job queue |

Transient discovery errors receive at most two retries after the first attempt,
with backoff and server `Retry-After`; all attempts fit the search deadline.
Permanent errors, unsupported filters and NoContent are not retried. Metadata
operations share per-provider and global semaphores across search jobs.

Native downloads stream into temporary files under `DATA_DIR/archive-assets`,
validate complete FITS HDU structure, then atomically publish. Gzip is validated
after bounded decompression while preserving the original compressed bytes.
Startup removes abandoned `.part` files; interruption and byte-limit failure
remove partial files. Stable cache keys include provider, collection, native ID,
version, product kind, observation-time identity and subset/delivery request.
Temporary retrieval grants are neither cache identity nor serialized API state.
Every redirect is origin-checked; CADC's qualified CANFAR hosts are explicit.

`prefer_cutout` uses an advertised cutout when a region is supplied. Without an
advertised cutout it can select a supported original. A failed/NoContent cutout
never silently falls back to an original. `require_cutout` needs a region and
fails if no qualified subset exists. Preview and ancillary links are not selected
as science `#this`. No new SPHEREx-equivalent calibration, preview, differencing
or ML eligibility is claimed; foreign assets retain `analysisEligible=false`.
Multiple `#this` originals are rejected as `ambiguous_science_asset` until a
provider-specific artifact identity is qualified; they never overwrite one
another under the same cache key. Unexpected provider defects become sanitized
per-provider or per-record failures rather than stopping background execution.

The native asset store retains completed artifacts without its own LRU/TTL, but
shares the existing `FitsCache` admission coordinator and `MAX_CACHE_BYTES` /
`MIN_FREE_BYTES` guards with legacy SPHEREx files. Archive file limits cannot
exceed `MAX_PRODUCT_BYTES`. Native gzip reserves both encoded and decoded
temporary capacity. Completed archive assets count toward the combined volume
budget and cannot be evicted by the legacy FITS LRU; new work receives an explicit
`cache_capacity` failure when the remaining space cannot admit it. Download
admission stays responsive while the single native transfer runner is active.

## Evidence and verification

Fixtures in `src/test/resources/archive` contain bounded response bodies only,
without cookies, transient headers or grant URLs. ESO/CADC overflow/DataLink,
BASS and ART-XC coverage/Gaia originate in the research probes dated 2026-11-14.
LAMOST release/cone and first-year ART-XC catalogue bodies were freshly retrieved
anonymously on that date. Synthetic FITS transfer fixtures test file structure,
not astrophysical correctness. No science images or temporary grants are checked in.

Optional Scala/ZIO live smoke:

```bash
ARCHIVE_LIVE_SMOKE=1 ./sbtw 'testOnly spaceapps.archive.ArchiveLiveSpec'
```

On 2026-11-14 both live tests passed in 43.317 seconds:

| Provider | Discovery | Validated SODA product | SHA-256 |
| --- | --- | --- | --- |
| ESO VISTA | 3 records, truncated | 43,200-byte FITS | `49b3e272d4e3f19675609ce6220a233faae3e63dd56755d4d93e7991d8cb6bdd` |
| CADC NEOSSat | 3 records, truncated | 43,200-byte FITS | `f7da7bbaa8a94e55959443321c9948ab6b27f5f54196c85b548d88e1cddfec06` |

These transfers prove protocol, origin and format handling; they do not establish
cross-survey astrometric agreement, comparable calibration or scientific accuracy.
Network-dependent live tests are ignored in ordinary CI.

Previous offline verification on 2026-11-14 after merging frontend-only main
`9843157012595ab03cb3e7683bb8a6c731ace489`:

- `./sbtw 'testOnly spaceapps.archive.*'`: 49 passed, zero failed, two optional
  live tests ignored.
- `./sbtw test stage`: 153 passed, zero failed, two optional live tests ignored;
  staged runtime built successfully. The 104 existing SPHEREx tests remain green.
- The branch diff passed `git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --check origin/main..HEAD`; original HTTP fixture CRLF bytes are retained. Deployment/bootstrap/test shell syntax checks passed.
- OpenAPI validation retained all 14 legacy paths and 17 legacy schemas
  structurally, and added exactly seven archive paths.
- The staged `spaceapps.bootstrap.Main` started with a fresh isolated `DATA_DIR`,
  HTTP on local port 15843 and private gRPC on an ephemeral port. Health, Swagger,
  JSON OpenAPI and all 14 inventory entries were reachable. A locally submitted
  ESASky-only search returned 202, ran through the real background worker, and
  persisted a terminal `failed` job with provider status `unavailable` rather
  than a fabricated empty success. No upstream network was required for this
  bootstrap smoke; the test process was stopped afterwards.

Review regressions ran red before their fixes and are included in the green
suite: responsive download admission, sanitized discovery/resolution defects,
malformed Gaia HTTP 200 rows, ambiguous multiple science originals, preserved
POST redirects, and continuation admission limits. Combined cache and free-space
guards have four independent tests. Initial TABLEDATA-only parsing, provisional
clocks, pending providers and unqualified foreign processing remain explicit
capability boundaries, rather than implementation claims.

## Refresh against ML inference and VPS migration

On 2026-11-14 the branch merged current `origin/main`
`0a2da5aa13e64c1a8167d94f9f1801ccb49e915a`. The refresh preserves the merged
ML analysis HTTP/gRPC services, teammates' frontend work, and deployment to
`144.124.238.101` including CI image delta transfer. No unmerged cutout branch
was imported, and no deployment was performed as part of this refresh.

The only integration resolutions combine the existing analysis dependency
injection with the archive runtime and shared FITS capacity coordinator in
`Main.scala`, and retain both OpenAPI tags. Archive implementation, fixtures and
tests are unchanged. Existing main services and protobuf definitions, frontend,
operations scripts and CI workflows remain identical to this main revision.

Fresh verification after those resolutions:

- `./sbtw test stage`: 169 passed, zero failed, two optional live tests ignored;
  staged runtime built successfully. This includes the unchanged 49 archive tests
  and 120 existing tests, including the merged ML analysis suite.
- OpenAPI 3.1 schema validation passed. Semantic YAML comparisons preserve all
  20 current main paths, 23 schemas, all other component definitions and the
  migrated server address. The seven additive archive paths and 14 archive
  schemas are unchanged from the pre-refresh archive branch.
- Shell syntax checks passed for deployment, frontend deployment, VPS bootstrap,
  CI SSH helper, their shell test scripts and `backend/sbtw`.
- `git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol
  diff --check origin/main` passed; original HTTP fixture CRLF bytes are retained.

The earlier live-provider and staged bootstrap smoke evidence above was not
rerun during this merge-only refresh; its scope and scientific limits remain
unchanged.
