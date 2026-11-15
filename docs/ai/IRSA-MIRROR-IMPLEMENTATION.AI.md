# IRSA availability and mirror implementation

User requirement: route around failed SIA/TAP with a circuit breaker, use the public SPHEREx mirror, probe both external services once per hour in infra, and automatically restore primary traffic after a valid successful probe.

## Design and implementation plan

1. Infra owns independent SIA/TAP circuit states, real bounded metadata probes, scoped hourly background loops and a read-only health endpoint. Startup is mirror-first until a successful probe. Transport/timeout/5xx failures open the relevant breaker; ordinary invalid requests do not. Requests never trigger recovery probes. Old concurrent successes must not close a newly opened breaker.
2. IRSA owns a persistent mirror observation index populated from anonymous public S3 listing and bounded FITS header ranges. Search preserves sky geometry, dates, detector, exact release and original artifact identity. It has no dependency on live SIA/TAP. Indexing is bounded, resumable and independent of HTTP request latency.
3. The archive adapter routes discovery through the SIA breaker or mirror. Originals use public S3 URLs. Existing native spatial cutouts retain the working IBE service, mapped from the exact mirror artifact path; failed cutouts do not trigger full-frame fallback. TAP is guarded separately; existing metadata cache and FITS-header details remain available during its outage.
4. Expose service state and index progress. Partial index results must be explicitly labelled in metadata and durable job warnings; an empty unfinished index is not a successful empty sky. Unknown survey or channel calibration must not be invented. QR2 must not be relabelled DR1/QR3.
5. Wire this into bootstrap, the generic archive bridge and container packaging. Test opening/closing/races/hourly scheduling, bounded real S3 protocol fixtures, query geometry and partial results, normal native cutout identity and failure behavior. Run focused tests and a small real S3 header smoke. Open a PR; do not push main.

## Scope and operational limits

The initial mirror needs background ingestion. Full release indexing can take substantial time and network I/O; no claim of instantaneous all-sky recovery is permitted. S3 does not provide the coordinate search API that SIA provides. The existing Python processing service has additional direct IRSA callers; audit and document integration coverage explicitly.

A native epoch difference, scientific spectrum, or image pixel values may never be replaced with synthetic/demo values. The existing byte cache and LRU remain separate from the metadata index.

No production deployment has been performed by this change. Backend review instructions require a PR before main.

## Runtime details

- `GET /api/infra/external-services`: current SIA/TAP circuits, last/next checks, preferred discovery route, indexed object count, listing progress, pending failed objects and scan errors. Reading this endpoint never sends a probe.
- `POST /api/irsa/discovery`: shared pixel-free discovery gateway used by configured Python image, spectrum and motion consumers. It accepts RA/Dec/radius, optional detector and UTC bounds; returns native artifact metadata and an explicit `discovery_complete` boolean.
- Primary discovery has a 15-second failover deadline, below generic discovery's default 30-second provider budget. Mirror searches have an 8-second total queue/processing deadline, two active subprocesses and two waiting callers maximum. Python gateway timeout is 45 seconds.
- Startup and hourly data-plane probes validate bounded VOTable responses. A sole SIA `OVERFLOW` status is valid for the diagnostic MAXREC=1; TAP must report OK. HTTP200 HTML is not recovery.
- Listing advances after successful metadata or durable retry outcomes. Failed objects do not starve the rest of the sky. Release selection uses least scanned pages, with configured release order breaking ties. Retries are limited per scan and back off from 60 seconds to one hour. Coverage stays incomplete while failures remain unresolved.

### Configuration

| Setting | Default / purpose |
|---|---|
| `IRSA_MIRROR_RELEASES` | `qr2,dr1,qr3`; labels always retain actual release |
| `IRSA_MIRROR_SCRIPT` | `python/irsa_mirror.py` locally, `/app/integrations/irsa_mirror.py` in container |
| `ML_PYTHON` | Existing scientific runtime Python, already contains Astropy/NumPy |
| `IRSA_MIRROR_SCAN_ENABLED` | `true`; disable only for controlled seeded-index diagnostics |
| `IRSA_MIRROR_MAX_INDEX_BYTES` | 512 MiB including SQLite WAL/SHM; preserve at least 256 MiB free disk |
| `IRSA_DISCOVERY_URL` | Pipeline: `http://api:8000/api/irsa/discovery`; ML Compose: configurable host gateway URL |

Index file is `${DATA_DIR}/irsa-mirror.sqlite`. A completed snapshot is not automatically rebuilt; release refresh currently requires an explicit helper `reset` followed by background scanning. Reset intentionally clears the chosen releases' index. Do not reset just to recover an unhealthy SIA/TAP: circuit probes run independently. There is no per-request S3 all-sky traversal.

S3 mirror discovery and original transfers are independent of SIA/TAP. Spatial cutouts still require the real IBE cutout service; this change does not claim to replace IBE during an IBE outage. Unknown deep-survey identity and unconfigured channel calibration return explicit unsupported errors. Explicit collection selection remains exact; only implicit default requests and render/spectrum operations opt into cross-release fallback with real provenance.

## Verification evidence

Local full-backend smoke ran with both primary endpoints forced to unreachable `127.0.0.1:1`. A real DR1 S3 header was indexed with a bounded Range request. `POST /api/irsa/discovery` found that artifact and preserved source/date/detector. Native retrieval returned HTTP202 and then a usable chunk; its final job is `completed_with_errors` solely because coverage is partial. The chunk itself downloaded with HTTP200 and passed Astropy FITS verification:

- Real observation: `2025-04-24T18:01:05.843`, detector1, DR1.
- Requested center: RA160.61751806182033°, Dec30.66935970465461°; this is a verification field, not proof of coverage for arbitrary coordinates.
- Size3,954,240bytes, IMAGE10×10, seven HDUs: PRIMARY/IMAGE/FLAGS/VARIANCE/ZODI/EPSF/WCS-WAVE.
- SHA256: `48233fd6af5e818c7efb33ba26a4e9b00eb6bac433e5d9d9a12f3dc6cadffc19`.
- Reproducible JSON evidence: `irsa-mirror-evidence/`. Large FITS file remains scratch data and is not committed.

Focused test runs verified circuit timing/races/protocol validation, subprocess errors and admission, geometry/date/source contracts, partial native jobs, Python gateway and HTTP/FITS responses. Full repository pytest has unrelated research-module collection and uninitialized crawler-database failures; targeted pipeline/science tests passed. No claim of full repository green is made.

## Sources and issue

Closes [#33](https://github.com/Nirbaan13/team_showerless/issues/33).

- [Organizer discussion of the outage and S3 mirror](https://github.com/nasa/spaceapps/discussions/2257).
- [Official IRSA cloud access and actual releases](https://irsa.ipac.caltech.edu/cloud_access/).
- [SPHEREx access documentation](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/).

Final local verification: **84 Scala tests passed**, **61 Python tests passed /1optional live skipped**. The separate live header smoke also passed. Real Python search and PNG rendering through the shared gateway both returned HTTP200 with `s3_mirror` provenance and partial coverage. An additional real QR2 header and coordinate search succeeded for detector2, observation2025-04-24; the QR2 identity is preserved in `qr2-discovery.json`. Docker Compose configuration and whitespace checks passed.
