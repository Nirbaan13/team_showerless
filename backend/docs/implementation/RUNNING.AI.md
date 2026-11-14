# Running the IRSA retrieval service

Use JDK25. Run `./sbtw test stage` in backend/, then `APP_REVISION=$(git rev-parse HEAD) java --enable-native-access=ALL-UNNAMED -cp 'target/stage/classes:target/stage/lib/*' spaceapps.Main`. Native libraries require an executable temporary directory. The service listens on port8000; /health and /version report the Git revision; /docs serves Swagger UI from the checked-in OpenAPI through /openapi.json.

The application implements metadata search, default/range/polygon native-image retrieval, durable status, snapshot-first SSE and FITS file delivery. The public polygon parameter is spelled `verices_degrees` to match the current contract. It does not invent tiles or reproject pixels. A chunk contains an entire native IRSA image, which can extend beyond the requested discovery region.

Per the user's clarification, PNG previews and the two scientific subtraction modes are deferred. Preview resources report409 unavailable and preview_status=unavailable. The subtraction routes report501 unsupported_processing and never return native data mislabeled as processed. Runtime Swagger documents this deviation; the checked-in team contract is not rewritten. Future processing interfaces are isolated behind Processor.

Configuration is read at startup:

| Environment | Default | Meaning |
|---|---|---|
| APP_REVISION | development | Build/deployment Git revision |
| PORT | 8000 | HTTP listen port |
| DATA_DIR | data | Persistent SQLite, event journal and native FITS cache |
| IRSA_SIA_URL | https://irsa.ipac.caltech.edu/SIA | Archive metadata endpoint; use a local fixture endpoint for isolated integration tests |
| MAX_OBSERVATIONS | 256 | Bounded discovery result count; overflow fails explicitly |
| MAX_PRODUCT_BYTES | 268435456 | Maximum streamed size of one native image |
| MAX_CACHE_BYTES | 21474836480 | Cache admission budget including active transfers |
| MIN_FREE_BYTES | 536870912 | Space reserved for OS/database activity |
| WORKERS | 2 | Application-scoped background coordinators |
| TRANSFERS | 4 | Global concurrent product transfers |
| MAX_ACTIVE_JOBS | 32 | Transactional accepted-work limit |
| CHANNEL_BANDS_JSON | {} | Authoritative channel-to-wavelength interval mapping in meters; absent mappings return422 rather than inventing a calibration |
| OPENAPI_PATH | docs/openai/openapi.yaml | Team's authoritative contract |

Center requests support angular dimensions up to600arcmin; ranges support up to10degrees per axis; convex polygons accept3–64vertices. These are service admission limits, not IRSA image sizes. Use polygons to cross RA0. Search time filters are ISO timestamps converted to UTC MJD. Metadata discovery never downloads FITS bytes. Channel filtering chooses native image products through IRSA BAND; it does not extract spectral planes or relabel an LVF image as a102channel cube.

SQLite is authoritative for jobs, chunks, request deduplication and events. Workers run in application scope, so request/SSE disconnection does not cancel retrieval. Restart requeues interrupted jobs. Output uses a same-filesystem temporary file, FITS signature/record-size checks and atomic rename before ready status. This checks transfer integrity basics rather than complete scientific FITS correctness. Failed/partial transfers are removed; missing cached files are surfaced explicitly and permit a new request. SSE always begins with job.updated containing the current manifest and closes after job.completed. Poll status after reconnecting.

Docker Compose mounts api-data at /app/data; retain this volume across container replacement. Keep API heap, direct buffers, OS cache and other team services inside the host memory budget. Deployment uses immutable Git SHA images; the existing deployment script publishes Docker latest only after health checks and rolls back failed updates. PRs run tests/container checks; they do not deploy. Human review precedes merge into main.

The image also declares /app/data as a Docker volume for compatibility with the existing VPS Compose file. Compose preserves that volume across ordinary container replacement; CI verifies a storage sentinel across upgrade and rollback with both current and legacy Compose. Do not run volume-pruning/removal commands against application storage. Before replacing a legacy anonymous volume with a named volume, migrate its data. Native library extraction uses /app/data/tmp so an existing noexec /tmp mount cannot break SQLite/Netty.
