# Archive details implementation plan

Goal: expose expanded metadata for known frames, equipment calibration files, and native deep-survey observations through the existing Scala service.

User-approved scope: GET /api/observations/meta?frame_id=..., GET /api/equipment, and GET /api/observationsDeep. Frame identifiers already come from search; do not add metadata_url. Scientific image processing remains owned by the Python pipeline.

## Contracts and boundaries

- Metadata resolves a persisted frame ID; unknown IDs return404 before external calls. Return the observation, available SIA fields, additional TAP fields, and FITS HDU headers when the native file is already cached. Report per-source availability and errors explicitly. Do not download a full science image just to answer metadata.
- Equipment returns SPHEREx facility/instrument information and a catalogue of calibration products from official browsable IRSA release directories. Filter by release and detector. Catalogue file identities refer to GET /api/equipment/calibrations/{id}; this supporting resource route streams actual cached files through this service. Do not accept arbitrary upstream URLs.
- Deep observations use the existing geometry, date, detector, channel, durable job, events and chunk machinery. The queried collections are spherex_dr1_deep and spherex_qr3_deep. Keep survey identity in persisted queries and cache keys. Preserve default wide-survey behavior and existing IDs.
- HTTP and gRPC share service implementations. Add gRPC methods for metadata, equipment, calibration bytes, and deep preparation. Preserve all existing RPC field numbers and methods.
- SQLite stores additional metadata/catalogue caches. Bound remote response sizes, request durations, concurrency, file sizes and cache storage; keep external errors explicit and retain useful available metadata.
- Keep IRSA adapters in integrations.irsa and gRPC adapters in integrations.grpc. All prose documentation ends .AI.md; keep the human AGENTS.md unchanged.

## File ownership

- Metadata worker: new MetadataService.scala, integrations/irsa/TapMetadata.scala, integrations/fits/FitsHeaders.scala, MetadataSpec.scala, and the FITS reader dependency in build.sbt if needed.
- Equipment worker: new EquipmentService.scala, integrations/irsa/CalibrationArchive.scala, related equipment domain types, and EquipmentSpec.scala.
- Root: domain query/deep identity, LiveArchive deep collections, SQLite cache methods, Jobs cached-native lookup, HTTP/gRPC wiring and schema, OpenAPI, integration tests, docs and delivery.

## Shared interfaces

- Repository.cachedMetadata(key: String): Task[Option[(String, Long)]] returns body and Unix timestamp seconds; cacheMetadata(key: String, body: String): Task[Unit] stores/replaces it.
- Jobs.cachedImage(image: ArchiveImage): Task[Option[Path]] checks an already-published native file without fetching it.
- MetadataService.make(repository: Repository, cachedFile: ArchiveImage => Task[Option[Path]], client: Client, tapEndpoint: String = "https://irsa.ipac.caltech.edu/TAP/sync"): Task[MetadataService]; get(frameId: String): Task[Json].
- EquipmentService.make(repository: Repository, dataDir: Path, client: Client, baseUrl: String = "https://nasa-irsa-spherex.s3.amazonaws.com/"): Task[EquipmentService]; catalog(release: String, detector: Option[Int]): Task[Json]; file(id: String): Task[EquipmentFile]. EquipmentFile has path: Path, fileName: String, contentType: String.
- Query adds deep: Boolean = false. A helper marks its normalized public document survey=deep for deep jobs, ensuring distinct deduplication and restart recovery. Existing wide requests omit survey and remain unchanged.

## Tasks and verification

- [ ] Establish a green baseline; write failing SQLite cache and deep-query boundary tests.
- [ ] Implement the persistent cache methods and cached native-file lookup; validate persistence after reopen.
- [ ] Implement metadata enrichment with real localhost TAP fixtures and actual FITS headers, including missing files, null fields, malformed replies and unavailable upstream behavior.
- [ ] Implement calibration discovery and actual file streaming with localhost directory/file fixtures, catalogue caching, deduplication, restart lookup, path/URL validation and bounded storage.
- [ ] Implement deep retrieval identity and release decoding; test emitted collections, preserved date filters, wide/deep cache separation and restart-compatible serialization.
- [ ] Expose HTTP routes and additive gRPC methods. Test validation, unknown IDs, real output files, geometry selection and transport errors using the shared services.
- [ ] Update OpenAPI and running documentation. Run all backend tests, build/stage and verify Swagger and representative real IRSA responses.
- [ ] Obtain an independent whole-change review; address material findings, open a PR and run CI. Continue the authorized merge/deploy flow and verify production Swagger before reporting completion.

## Review focus

- Unknown or malicious IDs must never become arbitrary network requests or filesystem paths.
- TAP nulls and upstream failures must not invent metadata or erase available SIA information.
- Native FITS arrays remain untouched; metadata reading must avoid loading scientific pixel arrays.
- Calibration files retain the upstream version/release/detector identity, remain valid after restart, and never masquerade as frame-specific science images.
- Wide and deep queries with identical geometry must never deduplicate to the same download job or omit the deep source identity.


## Additional user instruction: native FITS LRU

The user explicitly requested LRU eviction through a Q&A task relay. Use SQLite identity/path/size/last_accessed_at, touch real reuse and reads, and reserve capacity before transfers. Protect active processing, downloads and HTTP/gRPC readers; retain atomic publication, restart recovery and cache_missing/refetch. FitsCache is the single process coordinator; one service process owns a data directory. Administrative SQLite pages are excluded from the product-byte budget but naturally consume free disk space. The implementation adds scoped Jobs.cachedImage and Jobs.leasedResource and scopes HTTP handlers through the full streaming response lifetime.

Verification ledger: baseline48passed; persistent metadata cache RED(missingmethod)→GREEN; deep protocol/HTTP RED→GREEN; gRPC additive methods RED→GREEN; equipment upstream/client error mapping RED→GREEN. Metadata10, equipment14 and LRU11 focused tests passed. Integrated full suite100passed before final review. Standalone OpenAPI parsing and all-reference validation passed. Live archive checks and review remain tracked by the final delivery report.
