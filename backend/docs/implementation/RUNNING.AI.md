# Running the IRSA retrieval service

Use JDK25 and the locked Python scientific runtime. For local work set `PROCESSING_PYTHON` to the shared UtilsAI interpreter (or a compatible installed runtime). Run `./sbtw test stage` in backend/, then `APP_REVISION=$(git rev-parse HEAD) java --enable-native-access=ALL-UNNAMED -cp 'target/stage/classes:target/stage/lib/*' spaceapps.bootstrap.Main`. Native libraries require an executable temporary directory. The service listens on port8000; /health and /version report the Git revision; /docs serves Swagger UI from the checked-in OpenAPI through /openapi.json.

The application implements metadata search, expanded frame metadata, equipment/calibration discovery and file delivery, wide/deep native-image retrieval, durable status, snapshot-first SSE and FITS file delivery. The public polygon parameter is spelled `verices_degrees` to match the current contract. It does not invent tiles or reproject pixels. A chunk contains an entire native IRSA image, which can extend beyond the requested discovery region.

PNG previews and native ZODI subtraction are enabled through a supervised offline Python worker. Default retrieval retains the original FITS and prepares a real masked ZScale PNG. The zodi-reference-subtracted route subtracts the source's own ZODI layer exactly once, preserves FITS HDUs/WCS, and records provenance. Epoch difference and alignment remain unsupported501. Spectrum computation remains explicitly not-ready until per-pixel spectral calibration and photometry are scientifically qualified. No synthetic fallback service is called.

Configuration is read at startup:

| Environment | Default | Meaning |
|---|---|---|
| APP_REVISION | development | Build/deployment Git revision |
| PORT | 8000 | HTTP listen port |
| DATA_DIR | data | Persistent SQLite, event journal and native FITS cache |
| IRSA_SIA_URL | https://irsa.ipac.caltech.edu/SIA | Archive metadata endpoint; use a local fixture endpoint for isolated integration tests |
| IRSA_TAP_URL | https://irsa.ipac.caltech.edu/TAP/sync | Exact-product metadata enrichment; metadata requests never download science images |
| IRSA_CALIBRATION_URL | https://nasa-irsa-spherex.s3.amazonaws.com/ | Official public IRSA calibration mirror; actual catalogue files are cached and served through this backend |
| MAX_OBSERVATIONS | 256 | Bounded discovery result count; overflow fails explicitly |
| MAX_PRODUCT_BYTES | 268435456 | Maximum streamed size of one native image |
| MAX_CACHE_BYTES | 21474836480 | Cache admission budget including active transfers |
| MIN_FREE_BYTES | 536870912 | Space reserved for OS/database activity |
| PROCESSING_PYTHON | python3 | Scientific interpreter; Docker uses /opt/inference-venv/bin/python |
| PROCESSING_WORKER | processing/worker.py | Offline trusted worker executable |
| PIPELINE_ROOT | ../pipeline | Team module directory; Docker uses /app/pipeline |
| PROCESSING_CONCURRENCY | 2 | Concurrent supervised Python operations, between1 and4 |
| WORKERS | 2 | Application-scoped background coordinators |
| TRANSFERS | 4 | Global concurrent product transfers |
| MAX_ACTIVE_JOBS | 32 | Transactional accepted-work limit |
| CHANNEL_BANDS_JSON | {} | Authoritative channel-to-wavelength interval mapping in meters; absent mappings return422 rather than inventing a calibration |
| OPENAPI_PATH | docs/openai/openapi.yaml | Team's authoritative contract |

Center requests support angular dimensions up to600arcmin; ranges support up to10degrees per axis; convex polygons accept3–64vertices. These are service admission limits, not IRSA image sizes. Use polygons to cross RA0. Search time filters are ISO timestamps converted to UTC MJD. Metadata discovery never downloads FITS bytes. Channel filtering chooses native image products through IRSA BAND; it does not extract spectral planes or relabel an LVF image as a102channel cube.

SQLite is authoritative for jobs, chunks, request deduplication and events. Workers run in application scope, so request/SSE disconnection does not cancel retrieval. Restart requeues interrupted jobs. Output uses a same-filesystem temporary file, FITS signature/record-size checks and atomic rename before ready status. This checks transfer integrity basics rather than complete scientific FITS correctness. Failed/partial transfers are removed; missing cached files are surfaced explicitly and permit a new request. SSE always begins with job.updated containing the current manifest and closes after job.completed. Poll status after reconnecting.

Docker Compose mounts api-data at /app/data; retain this volume across container replacement. Keep API heap, direct buffers, OS cache and other team services inside the host memory budget. Deployment uses immutable Git SHA images; the existing deployment script publishes Docker latest only after health checks and rolls back failed updates. PRs run tests/container checks; they do not deploy. Human review precedes merge into main.

The image also declares /app/data as a Docker volume for compatibility with the existing VPS Compose file. Compose preserves that volume across ordinary container replacement; CI verifies a storage sentinel across upgrade and rollback with both current and legacy Compose. Do not run volume-pruning/removal commands against application storage. Before replacing a legacy anonymous volume with a named volume, migrate its data. Native library extraction uses /app/data/tmp so an existing noexec /tmp mount cannot break SQLite/Netty.


Expanded metadata is available at GET /api/observations/meta?frame_id=<frame_id>, where the frame ID already came from search or a download manifest. The response groups observation, sia, tap and fits. Source availability is explicit; TAP preserves null values and field units, and FITS headers become available only after the original native file is present. No metadata_url field is required. TAP results are cached for one hour (empty results for60seconds), with explicit stale fallback on upstream failure. Stored metadata JSON is limited to4MiB per entry and64MiB total; old replaceable entries are evicted while durable equipment file identities are retained. A cache write failure does not discard a successful live TAP response.

GET /api/equipment?release=DR1&detector_array=1 returns equipment details and actual calibration products. DR1 and QR3 are supported; omit detector_array or use all for every detector. Each product retains its discovered version and a download_url pointing to GET /api/equipment/calibrations/{id}. Those files are downloaded once through the backend and cached with a128MiB per-file limit,512MiB cache budget and512MiB free-space reserve. Catalogue discovery has bounded pagination and never silently returns a truncated successful catalogue. Versions must be matched to a frame's provenance; the service does not claim that the newest file applies to every frame.

GET /api/observationsDeep accepts exactly one geometry family: center RA/Dec with optional angular width/height, four range boundaries, or verices_degrees polygon coordinates. Existing date/detector/channel filters apply. It searches spherex_dr1_deep and spherex_qr3_deep and returns the same durable download/SSE/chunk contract as normal preparation. Wide/deep identity is persisted in the normalized query and deduplication key. POST /api/observations/search also accepts survey=deep in its JSON body for metadata-only deep discovery. Existing requests continue to use the wide survey.

The native FITS cache uses SQLite-backed least-recently-used eviction. Reads and actual reuse update last_accessed_at; download admission reserves its maximum product size and evicts only eligible service-owned FITS files. Processing, FITS-header inspection and HTTP/gRPC readers pin their inputs until completion or cancellation. Active transfer bytes are not counted twice. Atomic publication, restart reconciliation and cache_missing/refetch behavior are preserved; unrelated files and calibration products are never eviction candidates.

Additive gRPC methods mirror the new HTTP capabilities: PrepareDeepObservations, GetObservationMetadata, GetEquipment and streaming GetCalibrationFile. Query.deep selects deep discovery; existing field numbers and RPCs are unchanged. Metadata and equipment documents use google.protobuf.Struct, while calibration bytes use the existing bounded ChunkBytes stream.


EquipmentService also assumes a single owning process per data directory. Startup removes only owned regular calibration partials named <64 lowercase hex>.part; unrelated files are retained and symbolic links are rejected. Shared TAP lookups belong to application scope, so one disconnected metadata caller cannot cancel other callers waiting for the same frame.


Build the backend image from the repository root with `docker build --file backend/Dockerfile --build-arg APP_REVISION=<git-sha> --tag spaceapps-api:<git-sha> .`. The root build context includes the reviewed team cleaning module and offline worker. Only their required sources are copied into the runtime; pipeline/service.py and its synthetic image fallback are not used. Runtime scientific dependencies are hash-locked under backend/processing; CI runs both Python science tests and Scala/FITS integration tests before image and rollback verification. Root .dockerignore retains frontend/dist for the independent frontend image build.

Python subprocess requests/responses and diagnostics are bounded. A processing operation has a120-second deadline; timeout/cancellation terminates its process before releasing input leases. Worker outputs are checked for matching identity, size and PNG/FITS signatures, then Jobs publishes them atomically. Processing failures remain explicit chunk/preview errors; original native files stay immutable.

The additive gRPC PrepareRequest.mode accepts default (or empty) and zodi_reference_subtracted when the configured processor advertises it. Unvalidated modes return UNIMPLEMENTED before job admission. A separate reference_frame_id is not used by these validated modes. Existing clients that omit the new fields retain default behavior.
