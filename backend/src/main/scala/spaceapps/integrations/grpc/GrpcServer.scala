package spaceapps.integrations.grpc

import spaceapps.domain.ApiError
import spaceapps.service.{Jobs, Resource}
import spaceapps.integrations.grpc.v1.*
import spaceapps.integrations.grpc.v1.ZioRetrieval.{RCRetrievalService, GRetrievalService}
import io.grpc.{Status, StatusException, Metadata}
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder
import com.google.protobuf.ByteString
import scalapb.zio_grpc.RequestContext
import zio.*
import zio.stream.*
import java.net.InetSocketAddress
import java.util.concurrent.TimeUnit

object GrpcServer:
  /** The server lifetime belongs to the application scope; port 0 binds an ephemeral port. */
  def start(jobs: Jobs, revision: String, host: String = "0.0.0.0", port: Int = 50051,
    channels: Set[Int] = Set.empty): ZIO[Scope, Throwable, Int] =
    for
      definition <- GRetrievalService.genericBindable.bind(new Retrieval(jobs, revision, channels))
      server <- ZIO.acquireRelease(ZIO.attempt {
        NettyServerBuilder.forAddress(new InetSocketAddress(host, port)).addService(definition).build()
      })(shutdown)
      _ <- ZIO.attemptBlocking(server.start())
    yield server.getPort

  private def shutdown(server: io.grpc.Server): UIO[Unit] =
    ZIO.attemptBlocking {
      server.shutdown()
      if !server.awaitTermination(2, TimeUnit.SECONDS) then
        server.shutdownNow()
        server.awaitTermination(1, TimeUnit.SECONDS)
      ()
    }.catchAll(error =>
      ZIO.logWarningCause("gRPC server shutdown failed", Cause.fail(error)) *>
        ZIO.attempt(server.shutdownNow()).ignore)

private final class Retrieval(jobs: Jobs, revision: String, channels: Set[Int]) extends RCRetrievalService:
  private def failure(t: Throwable): StatusException =
    val e = ApiError.from(t)
    val status = e.code match
      case "invalid_request" | "unsupported_channel" => Status.INVALID_ARGUMENT
      case "not_found" => Status.NOT_FOUND
      case code if code.startsWith("archive_") || code == "upstream_error" => Status.UNAVAILABLE
      case "capacity_exceeded" | "cache_capacity" | "storage_full" | "insufficient_storage" => Status.RESOURCE_EXHAUSTED
      case "unsupported_processing" | "preview_unavailable" => Status.UNIMPLEMENTED
      case _ => Status.INTERNAL
    statusError(status, e)
  private def statusError(status: Status, error: ApiError): StatusException =
    val trailers = new Metadata()
    trailers.put(Metadata.Key.of("spaceapps-error-bin", Metadata.BINARY_BYTE_MARSHALLER), GrpcMapping.error(error).toByteArray)
    status.withDescription(error.message).asException(trailers)
  // ZIO gRPC closes calls with responseMetadata rather than StatusException trailers.
  private def preserve(error: StatusException, context: RequestContext): UIO[Unit] =
    Option(error.getTrailers).fold[UIO[Unit]](ZIO.unit)(trailers => context.responseMetadata.wrap(_.merge(trailers)))
  private def run[A](context: RequestContext)(effect: Task[A]): IO[StatusException,A] =
    effect.mapError(failure).tapError(preserve(_, context))
  private def query(input: Option[Query]) = ZIO.fromEither(GrpcMapping.query(input, channels))
  def searchObservations(request: SearchRequest, context: RequestContext): IO[StatusException, SearchResponse] = run(context) {
    query(request.query).flatMap(jobs.search).map(os => SearchResponse(os.map(GrpcMapping.observation)))
  }
  def prepareObservations(request: PrepareRequest, context: RequestContext): IO[StatusException, Download] = run(context) {
    query(request.query).flatMap(jobs.submit(_, "default", None)).flatMap(v => ZIO.attempt(GrpcMapping.download(v)))
  }
  def getDownload(request: DownloadRequest, context: RequestContext): IO[StatusException, Download] = run(context) {
    jobs.get(request.downloadId).flatMap(v => ZIO.attempt(GrpcMapping.download(v)))
  }
  def watchDownload(request: DownloadRequest, context: RequestContext): Stream[StatusException, DownloadEvent] =
    jobs.events(request.downloadId).mapZIO(v => ZIO.attempt(GrpcMapping.event(v))).mapError(failure).tapError(preserve(_, context))
  def getChunk(request: ChunkRequest, context: RequestContext): Stream[StatusException, ChunkBytes] = ZStream.unwrap {
    run(context)(jobs.resource(request.chunkId, false)).flatMap {
      case Resource.Pending => ZIO.fail(statusError(Status.FAILED_PRECONDITION, ApiError("resource_pending", "The native chunk is not ready", true)))
      case Resource.Failed(e) => ZIO.fail(statusError(Status.FAILED_PRECONDITION, e))
      case Resource.Ready(path) => ZIO.succeed(
        ZStream.fromFile(path.toFile, chunkSize = 64 * 1024).chunks.map(bytes => ChunkBytes(ByteString.copyFrom(bytes.toArray))).mapError(failure))
    }
  }.tapError(preserve(_, context))
  def getVersion(request: VersionRequest, context: RequestContext): IO[StatusException, VersionResponse] =
    ZIO.succeed(VersionResponse(revision, "spaceapps.retrieval.v1"))
