package spaceapps

import zio.*
import zio.test.*
import java.nio.file.{Files, Path}

object JobsSpec extends ZIOSpecDefault:
  private val query = Query.fromParameters("default", Map("right_ascension_deg" -> "1", "declination_deg" -> "2")).toOption.get
  private val image = ArchiveImage(Observation("frame-1", "2026-01-01T00:00:00Z", 1, "dr1"), "https://example.test/product.fits")
  private def write(path: Path, value: String) = ZIO.attemptBlocking { Files.createDirectories(path.getParent); Files.writeString(path, value); () }
  private val processor = new Processor:
    def prepare(in: Path, out: Path, mode: String, reference: Option[Path], query: Query) = write(out, "prepared")
    def preview(in: Path, out: Path) = write(out, "preview")
  private def archive(gate: UIO[Unit] = ZIO.unit) = new Archive:
    def search(q: Query) = ZIO.succeed(List(image))
    def fetch(i: ArchiveImage, out: Path) = gate *> write(out, "SIMPLE  =                    T" + " " * 2850)
  private def temp = ZIO.acquireRelease(ZIO.attemptBlocking(Files.createTempDirectory("jobs-spec")))(p => ZIO.attemptBlocking {
    val paths = Files.walk(p)
    try paths.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally paths.close()
  }.orDie)
  private def awaitChunks(jobs: Jobs, id: String): Task[Download] =
    jobs.get(id).flatMap(d => if d.chunks.nonEmpty then ZIO.succeed(d) else Live.live(ZIO.sleep(20.millis)) *> awaitChunks(jobs, id))
  private def awaitDone(jobs: Jobs, id: String): Task[Download] =
    jobs.get(id).flatMap(d => if d.terminal then ZIO.succeed(d) else Live.live(ZIO.sleep(20.millis)) *> awaitDone(jobs, id))

  def spec = suite("Durable jobs")(
    test("concurrent submissions deduplicate while detached workers publish native data") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          gate <- Promise.make[Nothing, Unit]
          jobs <- Jobs.make(repo, archive(gate.await), processor, dir)
          accepted <- ZIO.foreachPar(1 to 12)(_ => jobs.submit(query, "default", None))
          _ <- gate.succeed(())
          done <- awaitDone(jobs, accepted.head.id)
          file <- jobs.resource(done.chunks.head.id, false)
          evs <- jobs.events(done.id).runCollect
        yield assertTrue(accepted.map(_.id).distinct.size == 1, done.status == "completed", done.chunks.size == 1,
          done.progress.ready_chunks == 1, file.isInstanceOf[Resource.Ready], evs.head.name == "job.updated", evs.last.name == "job.completed",
          evs.head.data.contains("job_id"))
      }
    },
    test("retrieval completes with preview unavailable when processing is disabled") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          disabled = new Processor:
            override def supportsPreview = false
            def prepare(in: Path, out: Path, mode: String, reference: Option[Path], q: Query) = ZIO.fail(ApiError("unsupported_processing", "Processing disabled"))
            def preview(in: Path, out: Path) = ZIO.fail(ApiError("unexpected_preview", "Preview must not be invoked"))
          jobs <- Jobs.make(repo, archive(), disabled, dir)
          accepted <- jobs.submit(query, "default", None)
          done <- awaitDone(jobs, accepted.id)
          fits <- jobs.resource(done.chunks.head.id, false)
          preview <- jobs.resource(done.chunks.head.id, true)
        yield assertTrue(done.status == "completed", done.chunks.head.preview_status == "unavailable", fits.isInstanceOf[Resource.Ready],
          preview match { case Resource.Failed(error) => error.code == "unavailable"; case _ => false })
      }
    },
    test("a channel filter selects native products without preparing science output") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          nativeOnly = new Processor:
            override def supportsPreview = false
            def prepare(in: Path, out: Path, mode: String, reference: Option[Path], q: Query) = ZIO.fail(ApiError("unexpected_prepare", "Native files must remain unchanged"))
            def preview(in: Path, out: Path) = ZIO.fail(ApiError("unexpected_preview", "Preview disabled"))
          jobs <- Jobs.make(repo, archive(), nativeOnly, dir)
          filtered = Query.fromParameters("default", Map("right_ascension_deg" -> "1", "declination_deg" -> "2", "channel_index" -> "4")).toOption.get
          accepted <- jobs.submit(filtered, "default", None)
          done <- awaitDone(jobs, accepted.id)
          file <- jobs.resource(done.chunks.head.id, false)
        yield assertTrue(done.status == "completed", done.chunks.head.status == "ready", file.isInstanceOf[Resource.Ready])
      }
    },
    test("preview failure preserves published FITS and terminates with a safe error") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          failing = new Processor:
            def prepare(in: Path, out: Path, mode: String, reference: Option[Path], q: Query) = write(out, "prepared")
            def preview(in: Path, out: Path) = ZIO.fail(new RuntimeException("secret upstream token"))
          jobs <- Jobs.make(repo, archive(), failing, dir)
          accepted <- jobs.submit(query, "default", None)
          done <- awaitDone(jobs, accepted.id)
          fits <- jobs.resource(done.chunks.head.id, false)
          preview <- jobs.resource(done.chunks.head.id, true)
        yield assertTrue(done.status == "completed_with_errors", done.chunks.head.status == "ready", done.chunks.head.preview_status == "failed",
          fits.isInstanceOf[Resource.Ready], preview.isInstanceOf[Resource.Failed], !done.toString.contains("secret"))
      }
    },
    test("unknown references reject before admission and missing science is terminal") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          missing = new Processor:
            def prepare(in: Path, out: Path, mode: String, reference: Option[Path], q: Query) = ZIO.fail(ApiError("processing_unavailable", "No processor configured"))
            def preview(in: Path, out: Path) = ZIO.fail(ApiError("processing_unavailable", "No processor configured"))
          jobs <- Jobs.make(repo, archive(), missing, dir)
          ref <- jobs.submit(query, "epoch", Some("absent")).either
          accepted <- jobs.submit(query, "channel", None)
          done <- awaitDone(jobs, accepted.id)
          res <- jobs.resource(done.chunks.head.id, false)
        yield assertTrue(ref.left.exists { case e: ApiError => e.code == "not_found"; case _ => false },
          done.status == "completed_with_errors", res.isInstanceOf[Resource.Failed], done.chunks.head.error.exists(_.code == "processing_unavailable"))
      }
    },
    test("accepted work resumes after application restart and absent files stop being ready") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          gate <- Promise.make[Nothing, Unit]
          accepted <- ZIO.scoped { Jobs.make(repo, archive(gate.await), processor, dir).flatMap(_.submit(query, "default", None)) }
          reopened <- Repository.open(dir.resolve("jobs.db"))
          jobs <- Jobs.make(reopened, archive(), processor, dir)
          done <- awaitDone(jobs, accepted.id)
          resource <- jobs.resource(done.chunks.head.id, false)
          _ <- resource match
            case Resource.Ready(path) => ZIO.attemptBlocking(Files.delete(path))
            case _ => ZIO.unit
          gone <- jobs.resource(done.chunks.head.id, false)
        yield assertTrue(done.status == "completed", gone.isInstanceOf[Resource.Failed])
      }
    },
    test("one worker overlaps transfers while respecting the global transfer limit") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          gate <- Promise.make[Nothing, Unit]
          overlapping <- Promise.make[Nothing, Unit]
          counts <- Ref.make((0, 0))
          source = new Archive:
            def search(q: Query) = ZIO.succeed((1 to 5).toList.map(n => image.copy(observation = image.observation.copy(frame_id = s"frame-$n"), accessUrl = s"https://example.test/$n.fits")))
            def fetch(i: ArchiveImage, out: Path) =
              (for
                state <- counts.modify { (current, maximum) => val next = (current + 1, maximum.max(current + 1)); (next, next) }
                _ <- overlapping.succeed(()).when(state._1 >= 2)
                _ <- gate.await
                _ <- write(out, "native data")
              yield ()).ensuring(counts.update((current, maximum) => (current - 1, maximum)))
          jobs <- Jobs.make(repo, source, processor, dir, workers = 1, transfers = 2)
          accepted <- jobs.submit(query, "default", None)
          observed <- overlapping.await.timeout(3.seconds)
          _ <- gate.succeed(())
          done <- awaitDone(jobs, accepted.id)
          count <- counts.get
        yield assertTrue(observed.isDefined, count._2 == 2, done.progress.ready_chunks == 5)
      }
    },
    test("admission bounds queued work") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          gate <- Promise.make[Nothing, Unit]
          jobs <- Jobs.make(repo, archive(gate.await), processor, dir, maxJobs = 1)
          first <- jobs.submit(query, "default", None)
          rejected <- jobs.submit(query, "channel", None).either
          _ <- jobs.events(first.id).take(1).runDrain
          _ <- gate.succeed(())
          done <- awaitDone(jobs, first.id)
        yield assertTrue(done.status == "completed", rejected.left.exists { case e: ApiError => e.code == "capacity_exceeded"; case _ => false })
      }
    },
    test("restart detects evicted completed files before deduplication") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          accepted <- ZIO.scoped {
            for
              jobs <- Jobs.make(repo, archive(), processor, dir)
              accepted <- jobs.submit(query, "default", None)
              done <- awaitDone(jobs, accepted.id)
              file <- jobs.resource(done.chunks.head.id, false)
              _ <- file match
                case Resource.Ready(path) => ZIO.attemptBlocking(Files.delete(path))
                case _ => ZIO.unit
            yield accepted
          }
          jobs <- Jobs.make(repo, archive(), processor, dir)
          retried <- jobs.submit(query, "default", None)
          done <- awaitDone(jobs, retried.id)
        yield assertTrue(retried.id != accepted.id, done.status == "completed")
      }
    },
    test("unavailable products expose terminal missing coverage without fetching") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          unavailable = new Archive:
            def search(q: Query) = ZIO.succeed(List(image.copy(observation = image.observation.copy(is_available = false, skip_reason = Some("not released")))))
            def fetch(i: ArchiveImage, out: Path) = ZIO.fail(ApiError("unexpected_fetch", "Unavailable images must not be fetched"))
          jobs <- Jobs.make(repo, unavailable, processor, dir)
          accepted <- jobs.submit(query, "default", None)
          done <- awaitDone(jobs, accepted.id)
          resource <- jobs.resource(done.chunks.head.id, false)
        yield assertTrue(done.status == "completed", done.progress.unavailable_chunks == 1, done.chunks.head.preview_status == "unavailable",
          resource match { case Resource.Failed(error) => error.code == "unavailable"; case _ => false })
      }
    },
    test("known search metadata enables references and raw products are reused across jobs") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          count <- Ref.make(0)
          source = new Archive:
            def search(q: Query) = ZIO.succeed(List(image))
            def fetch(i: ArchiveImage, out: Path) = count.update(_ + 1) *> write(out, "native data")
          jobs <- Jobs.make(repo, source, processor, dir)
          _ <- jobs.search(query)
          first <- jobs.submit(query, "default", None)
          _ <- awaitDone(jobs, first.id)
          second <- jobs.submit(query, "epoch", Some("frame-1"))
          done <- awaitDone(jobs, second.id)
          fetched <- count.get
        yield assertTrue(done.status == "completed", done.reference_frame_id.contains("frame-1"), fetched == 1)
      }
    },
    test("SSE disconnect does not cancel accepted work and pending resources stay hidden") {
      ZIO.scoped {
        for
          dir <- temp
          repo <- Repository.open(dir.resolve("jobs.db"))
          gate <- Promise.make[Nothing, Unit]
          jobs <- Jobs.make(repo, archive(gate.await), processor, dir)
          accepted <- jobs.submit(query, "default", None)
          discovered <- awaitChunks(jobs, accepted.id)
          pending <- jobs.resource(discovered.chunks.head.id, false)
          snapshot <- jobs.events(accepted.id).take(1).runCollect
          _ <- gate.succeed(())
          done <- awaitDone(jobs, accepted.id)
          all <- repo.eventsAfter(done.id, 0)
          chunkEvent = all.find(_.name == "chunk.ready").get
          unknown <- jobs.resource("unknown", false).either
        yield assertTrue(pending == Resource.Pending, snapshot.head.name == "job.updated", done.status == "completed", all.exists(_.name == "chunk.ready"), all.exists(_.name == "preview.ready"),
          all.last.name == "job.completed", !chunkEvent.data.contains("observations"), !chunkEvent.data.contains("\"chunks\""), chunkEvent.data.contains("fits_cutout_url"), unknown.left.exists { case e: ApiError => e.code == "not_found"; case _ => false })
      }
    }
  ) @@ TestAspect.withLiveClock @@ TestAspect.timeout(30.seconds)
