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
Network-dependent live tests are ignored in ordinary CI. Full regression results
are recorded below after the final run.
