package spaceapps

import spaceapps.domain.{ArchiveImage, Observation, ApiError, Query as DomainQuery}
import spaceapps.service.{Archive, Jobs, NoProcessing}
import spaceapps.repository.Repository
import spaceapps.integrations.grpc.GrpcServer
import spaceapps.integrations.grpc.v1.*
import spaceapps.integrations.grpc.v1.ZioRetrieval.RetrievalServiceClient
import io.grpc.{Status, StatusException}
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder
import scalapb.zio_grpc.ZManagedChannel
import zio.*
import zio.test.*
import zio.json.ast.Json
import java.nio.file.{Files, Path}

object GrpcSpec extends ZIOSpecDefault:
  private val bytes = Array.tabulate[Byte](200003)(n => (n % 251).toByte)
  private val observation = Observation("native-frame", "2026-01-01T00:00:00Z", 1, "dr1", channel_index = Some(4),
    header_metadata = Map("EXPTIME" -> Json.Num(12.5), "FLAGS" -> Json.Arr(zio.Chunk(Json.Bool(true), Json.Null))))
  private val query = Query(region = Query.Region.Center(Center(1, 2)))
  private val image = ArchiveImage(observation, "https://example.test/native.fits")
  private def temp = ZIO.acquireRelease(ZIO.attemptBlocking(Files.createTempDirectory("grpc-spec")))(p => ZIO.attemptBlocking {
    val paths = Files.walk(p)
    try paths.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally paths.close()
  }.orDie)
  private def archive(gate: UIO[Unit] = ZIO.unit, error: Option[ApiError] = None) = new Archive:
    def search(q: DomainQuery) = error.fold[Task[List[ArchiveImage]]](ZIO.succeed(List(image)))(ZIO.fail(_))
    def fetch(i: ArchiveImage, out: Path) = gate *> ZIO.attemptBlocking { Files.write(out, bytes); () }
  private def fixture(gate: UIO[Unit] = ZIO.unit, error: Option[ApiError] = None, maxJobs: Int = 32) = for
    dir <- temp
    repo <- Repository.open(dir.resolve("jobs.db"))
    jobs <- Jobs.make(repo, archive(gate, error), NoProcessing, dir, maxJobs = maxJobs)
    port <- GrpcServer.start(jobs, "test-revision", "127.0.0.1", 0, Set(4))
    client <- RetrievalServiceClient.scoped(ZManagedChannel(NettyChannelBuilder.forAddress("127.0.0.1", port).usePlaintext()))
  yield (jobs, repo, client)
  private def status[A](result: Either[StatusException,A], code: Status.Code) = result.left.exists(_.getStatus.getCode == code)
  private def awaitDiscovered(jobs: Jobs, id: String): Task[spaceapps.domain.Download] =
    jobs.get(id).flatMap(d => if d.chunks.nonEmpty then ZIO.succeed(d) else ZIO.sleep(10.millis) *> awaitDiscovered(jobs, id))

  def spec = suite("Native gRPC TCP adapter")(
    test("serves revision and typed observations over a real ephemeral TCP port") {
      ZIO.scoped {
        for
          f <- fixture()
          (_, _, client) = f
          version <- client.getVersion(VersionRequest())
          response <- client.searchObservations(SearchRequest(Some(query)))
          item = response.observations.head
        yield assertTrue(version.revision == "test-revision", version.apiVersion == "spaceapps.retrieval.v1",
          item.frameId == "native-frame", item.channelIndex.contains(4), item.headerMetadata.exists(_.fields.contains("EXPTIME")))
      }
    },
    test("rejects missing, invalid geometry and unmapped channels before durable admission") {
      ZIO.scoped {
        for
          f <- fixture()
          (_, repo, client) = f
          missing <- client.prepareObservations(PrepareRequest()).either
          invalid <- client.searchObservations(SearchRequest(Some(Query(region = Query.Region.Center(Center(360, 2)))))).either
          unavailable <- client.prepareObservations(PrepareRequest(Some(query.copy(channelIndex = Some(5))))).either
          malformed <- ZIO.foreach(List(
            Query(), query.copy(detectorArray = Some(7)), query.copy(channelIndex = Some(0)),
            query.copy(observedAfter = Some("yesterday")),
            Query(region = Query.Region.Range(Range(2, 1, 3, 4))),
            Query(region = Query.Region.Polygon(Polygon(Seq(Vertex(1, 1), Vertex(2, 2))))),
            Query(region = Query.Region.Center(Center(Double.NaN, 2)))
          ))(q => client.prepareObservations(PrepareRequest(Some(q))).either)
          records <- repo.records
        yield assertTrue(status(missing, Status.Code.INVALID_ARGUMENT), status(invalid, Status.Code.INVALID_ARGUMENT),
          status(unavailable, Status.Code.INVALID_ARGUMENT), malformed.forall(status(_, Status.Code.INVALID_ARGUMENT)), records.isEmpty)
      }
    },
    test("round trips range, correctly spelled polygon vertices and optional filters") {
      ZIO.scoped {
        for
          f <- fixture()
          (_, _, client) = f
          range = Query(region = Query.Region.Range(Range(1, 2, 3, 4)), detectorArray = Some(2), channelIndex = Some(4), observedAfter = Some("2026-01-01T00:00:00Z"))
          polygon = Query(region = Query.Region.Polygon(Polygon(Seq(Vertex(1, 1), Vertex(2, 1), Vertex(2, 2), Vertex(1, 2)))))
          r <- client.prepareObservations(PrepareRequest(Some(range)))
          p <- client.prepareObservations(PrepareRequest(Some(polygon)))
          done <- client.watchDownload(DownloadRequest(r.id)).runCollect
        yield assertTrue(r.query.contains(range), p.query.contains(polygon), done.last.getDownload.query.contains(range))
      }
    },
    test("deduplicates asynchronous submissions and emits typed compact chunk updates and complete manifests") {
      ZIO.scoped {
        for
          gate <- Promise.make[Nothing, Unit]
          f <- fixture(gate.await)
          (jobs, _, client) = f
          accepted <- ZIO.foreachPar(1 to 6)(_ => client.prepareObservations(PrepareRequest(Some(query))))
          discovered <- awaitDiscovered(jobs, accepted.head.id)
          pending <- client.getChunk(ChunkRequest(discovered.chunks.head.id)).runCollect.either
          snapshot <- Promise.make[Nothing, Unit]
          watching <- client.watchDownload(DownloadRequest(accepted.head.id)).tap(_ => snapshot.succeed(())).runCollect.fork
          _ <- snapshot.await
          _ <- gate.succeed(())
          events <- watching.join
          manifest <- client.getDownload(DownloadRequest(accepted.head.id))
          chunks <- client.getChunk(ChunkRequest(manifest.chunks.head.id)).runCollect
          joined = chunks.flatMap(c => zio.Chunk.fromArray(c.data.toByteArray)).toArray
        yield assertTrue(accepted.map(_.id).distinct.size == 1, status(pending, Status.Code.FAILED_PRECONDITION),
          events.last.name == "job.completed", events.last.getDownload.chunks.head.status == "ready",
          events.filter(_.name == "job.updated").forall(_.payload.isDownload), events.exists(_.payload.isChunkUpdate),
          manifest.mode == "default", manifest.chunks.head.previewStatus == "unavailable", chunks.size > 1,
          chunks.forall(_.data.size <= 65536), java.util.Arrays.equals(joined, bytes))
      }
    },
    test("maps unknown resources, archive failures and full queues to gRPC statuses") {
      ZIO.scoped {
        for
          gate <- Promise.make[Nothing, Unit]
          f <- fixture(gate.await, maxJobs = 1)
          (_, _, client) = f
          unknown <- client.getDownload(DownloadRequest("absent")).either
          unknownWatch <- client.watchDownload(DownloadRequest("absent")).runCollect.either
          unknownChunk <- client.getChunk(ChunkRequest("absent")).runCollect.either
          first <- client.prepareObservations(PrepareRequest(Some(query)))
          full <- client.prepareObservations(PrepareRequest(Some(Query(region = Query.Region.Center(Center(3, 4)))))).either
          failed <- fixture(error = Some(ApiError("archive_unavailable", "Archive unavailable", true)))
          archiveFailure <- failed._3.searchObservations(SearchRequest(Some(query))).either
        yield assertTrue(status(unknown, Status.Code.NOT_FOUND), status(unknownWatch, Status.Code.NOT_FOUND),
          status(unknownChunk, Status.Code.NOT_FOUND), status(full, Status.Code.RESOURCE_EXHAUSTED), status(archiveFailure, Status.Code.UNAVAILABLE))
      }
    },
    test("missing published files produce a typed failed-precondition error") {
      ZIO.scoped {
        for
          f <- fixture()
          (jobs, _, client) = f
          accepted <- client.prepareObservations(PrepareRequest(Some(query)))
          events <- client.watchDownload(DownloadRequest(accepted.id)).runCollect
          chunkId = events.last.getDownload.chunks.head.id
          resource <- jobs.resource(chunkId, false)
          _ <- resource match
            case spaceapps.service.Resource.Ready(path) => ZIO.attemptBlocking(Files.delete(path))
            case _ => ZIO.fail(new IllegalStateException("Expected native file"))
          missing <- client.getChunk(ChunkRequest(chunkId)).runCollect.either
          detail = missing.left.toOption.flatMap(e => Option(e.getTrailers).flatMap(t =>
            Option(t.get(io.grpc.Metadata.Key.of("spaceapps-error-bin", io.grpc.Metadata.BINARY_BYTE_MARSHALLER))))).map(spaceapps.integrations.grpc.v1.ApiError.parseFrom)
        yield assertTrue(status(missing, Status.Code.FAILED_PRECONDITION), detail.exists(_.code == "cache_missing"))
      }
    },
    test("server scope shutdown closes an active watch within five seconds without cancelling durable work") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          gate <- Promise.make[Nothing, Unit]
          jobs <- Jobs.make(repo, archive(gate.await), NoProcessing, dir)
          serverScope <- Scope.make
          _ <- ZIO.addFinalizer(serverScope.close(Exit.unit))
          port <- GrpcServer.start(jobs, "shutdown-test", "127.0.0.1", 0).provideEnvironment(ZEnvironment[Scope](serverScope))
          client <- RetrievalServiceClient.scoped(ZManagedChannel(NettyChannelBuilder.forAddress("127.0.0.1", port).usePlaintext()))
          accepted <- client.prepareObservations(PrepareRequest(Some(query)))
          snapshot <- Promise.make[Nothing, Unit]
          watching <- client.watchDownload(DownloadRequest(accepted.id)).tap(_ => snapshot.succeed(())).runDrain.either.forkScoped
          _ <- snapshot.await
          closing <- (serverScope.close(Exit.unit) *> watching.await).forkDaemon
          bounded <- closing.await.timeout(5.seconds)
          active <- jobs.get(accepted.id)
          disconnected <- watching.poll
          _ <- gate.succeed(())
          finished <- jobs.events(accepted.id).runCollect
          _ <- closing.await
          result <- watching.join
          persisted <- repo.get(accepted.id)
        yield assertTrue(bounded.isDefined, disconnected.isDefined, result.isLeft, !active.terminal,
          finished.last.name == "job.completed", persisted.download.status == "completed")
      }
    },
    test("cancelling watchers and byte streams leaves accepted work and server usable") {
      ZIO.scoped {
        for
          gate <- Promise.make[Nothing, Unit]
          f <- fixture(gate.await)
          (jobs, _, client) = f
          accepted <- client.prepareObservations(PrepareRequest(Some(query)))
          _ <- client.watchDownload(DownloadRequest(accepted.id)).take(1).runDrain
          _ <- gate.succeed(())
          events <- client.watchDownload(DownloadRequest(accepted.id)).runCollect
          chunkId = events.last.getDownload.chunks.head.id
          _ <- client.getChunk(ChunkRequest(chunkId)).take(1).runDrain
          all <- client.getChunk(ChunkRequest(chunkId)).runCollect
          done <- jobs.get(accepted.id)
        yield assertTrue(done.status == "completed", all.map(_.data.size).sum == bytes.length)
      }
    }
  ) @@ TestAspect.withLiveClock @@ TestAspect.timeout(30.seconds) @@ TestAspect.sequential
