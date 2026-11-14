# Native retrieval gRPC adapter

The service is `spaceapps.retrieval.v1.RetrievalService`. Its authoritative wire schema is
`src/main/protobuf/spaceapps/retrieval/v1/retrieval.proto`; ScalaPB generates Scala messages
and stubs in `spaceapps.integrations.grpc.v1`. ZIO gRPC generates `ZioRetrieval` service
and client interfaces. Generated sources belong in `target`, not source control.

`spaceapps.integrations.grpc.GrpcServer.start(jobs, revision, host = "0.0.0.0", port = 50051,
channels = Set.empty)` returns `ZIO[Scope, Throwable, Int]`. The returned integer is the bound
TCP port; `0` requests an ephemeral port. The application owns its scope and supplies the
same `Jobs` instance as HTTP. `channels` contains channel indexes with configured authoritative
wavelength intervals; a channel filter without a mapping rejects before job submission.
The transport uses native HTTP/2 gRPC and plaintext on its internal listener. Node can call
this listener directly with a generated native gRPC client. Browsers use the HTTP gateway;
gRPC-Web is not implemented.

| RPC | Behavior |
| --- | --- |
| `SearchObservations` | Validates a typed region and filters, then returns typed native observation metadata. |
| `PrepareObservations` | Accepts a durable, deduplicated native download and returns its current manifest immediately. |
| `GetDownload` | Returns the latest typed manifest, including progress and per-product failures. |
| `WatchDownload` | Sends an initial manifest snapshot, then typed updates through completion. A reconnect obtains a fresh snapshot. |
| `GetChunk` | Sends the original FITS bytes in ordered protobuf byte fields of at most 65,536 bytes. |
| `GetVersion` | Returns the application revision and `spaceapps.retrieval.v1` API identifier. |

The region is a protobuf `oneof` containing center, range, or polygon coordinates. Polygon
`vertices_degrees` is correctly spelled on the wire; the adapter translates it into the
legacy HTTP/domain `verices_degrees` parameter. Detector, channel and time filters retain
presence through proto3 optional fields. Geometry and date rules remain centralized in
`domain.Query.fromParameters`; the adapter does not duplicate scientific validation.
Manifests contain typed queries, observations, chunks, progress, and errors. Arbitrary
header values use `google.protobuf.Struct`. Each `job.updated` and `job.completed` event
contains a full manifest. Chunk and preview events contain a typed chunk update with its
owning download ID and progress. The internal repository currently stores JSON events;
only the adapter decodes those, so JSON is not an RPC envelope.

Preparation always uses the shared native `default` mode. One archive product is one
chunk. No PNG, slicing, resampling, channel extraction, or subtraction method is exposed.
Client stream cancellation releases stream resources without cancelling the durable job.
File streams use ZIO's scoped file reader, avoiding loading the entire product into memory.

| Failure | gRPC status |
| --- | --- |
| Missing/invalid query, invalid geometry or filters, unmapped channel | `INVALID_ARGUMENT` |
| Unknown download/chunk | `NOT_FOUND` |
| Archive failure during discovery | `UNAVAILABLE` |
| Full admission queue or exhausted cache storage | `RESOURCE_EXHAUSTED` |
| Pending, unavailable, failed, or missing cached product | `FAILED_PRECONDITION` |
| Unexpected internal failure | `INTERNAL`, with a safe description |

Error trailers include `spaceapps-error-bin`, a serialized `spaceapps.retrieval.v1.ApiError`
with code, safe message, and retryable flag. Asynchronous preparation failures remain in the
typed manifest, including terminal job errors; a successful acceptance is not a promise of
upstream availability. No accepted job belongs to a request fiber.

# Released dependency selection

The pinned generator/runtime pair is ZIO gRPC **0.6.4**, with ScalaPB **0.11.21**,
gRPC Java **1.84.2**, sbt-protoc **1.0.8**, and protoc **3.25.8**. The sbt build uses
Scala **2.12.21**, so codegen/compilerplugin resolve as `_2.12`; application runtimes
resolve as `_3` for application Scala **3.9.0**. All ZIO modules stay on the project's
**2.1.27** release. All gRPC core modules resolve at **1.84.2**. The transport is
`grpc-netty-shaded`, avoiding an unshaded Netty collision with ZIO HTTP.

The older installation guide contains a stale compatibility table; released artifact
POMs and tagged sources provide the authoritative pins:

- [ZIO gRPC 0.6.4 runtime POM](https://repo.maven.apache.org/maven2/com/thesamet/scalapb/zio-grpc/zio-grpc-core_3/0.6.4/zio-grpc-core_3-0.6.4.pom)
  declares ZIO 2.1.26 (aligned to the application's newer 2.1.27) and gRPC services 1.84.2.
- [ZIO gRPC 0.6.4 code generator POM](https://repo.maven.apache.org/maven2/com/thesamet/scalapb/zio-grpc/zio-grpc-codegen_2.12/0.6.4/zio-grpc-codegen_2.12-0.6.4.pom)
  declares Scala 2.12.21 and ScalaPB compilerplugin 0.11.21.
- [Tagged upstream versions](https://github.com/scalapb/zio-grpc/blob/v0.6.4/project/Versions.scala)
  independently confirm ZIO 2.1.26 and gRPC 1.84.2.
- [Tagged installation guide](https://github.com/scalapb/zio-grpc/blob/v0.6.4/docs/installation.md)
  documents generating ScalaPB and ZIO stubs together.

# Verification

Run `backend/sbtw 'testOnly spaceapps.GrpcSpec'` from the repository root. Tests use a real
TCP server on port 0, the generated ZIO gRPC client, real SQLite, scoped temporary storage,
and a deterministic fake archive. They cover typed metadata/revision, region/filter
validation before durable admission, range/polygon round trips, concurrent deduplication,
watch snapshots and compact events, pending/unknown/missing resources, archive and queue
status mapping, ordered native byte streaming across multiple messages, typed error trailers,
and cancellation followed by continued job completion and complete file retrieval. They make
no requests to IRSA. The complete suite is `backend/sbtw test`.
