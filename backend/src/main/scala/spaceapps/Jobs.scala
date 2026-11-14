package spaceapps

import zio.{Chunk as _, *}
import zio.stream.*
import java.nio.file.{Files, Path, StandardCopyOption}
import java.util.UUID

enum Resource:
  case Pending
  case Ready(path: Path)
  case Failed(error: ApiError)

final class Jobs private (repository: Repository, archive: Archive, processor: Processor, dataDir: Path,
  transfer: Semaphore, cacheLocks: Vector[Semaphore], maxJobs: Int):
  def search(query: Query): Task[List[Observation]] = archive.search(query).tap(repository.remember).map(_.map(_.observation))
  def submit(query: Query, mode: String, reference: Option[String]): Task[Download] =
    val validate = reference match
      case Some(id) => repository.image(id).flatMap {
        case Some(image) if image.observation.is_available => ZIO.unit
        case _ => ZIO.fail(ApiError("not_found", "Reference frame not found"))
      }
      case None => ZIO.unit
    validate *> repository.accept(query, mode, reference, maxJobs).flatMap { candidate =>
      if !candidate.terminal then ZIO.succeed(candidate)
      else
        repository.get(candidate.id).flatMap(checkFiles) *>
          repository.accept(query, mode, reference, maxJobs)
    }

  private def rawPath(image: ArchiveImage): Path = dataDir.resolve("raw").resolve(Hash.sha256(s"${image.observation.release}|${image.observation.frame_id}|${image.accessUrl}") + ".fits")
  private def preparedPath(job: String, chunk: String): Path = dataDir.resolve("jobs").resolve(job).resolve(chunk + ".fits")
  private def previewPath(job: String, chunk: String): Path = dataDir.resolve("jobs").resolve(job).resolve(chunk + ".png")
  private def fitsPath(record: JobRecord, chunk: Chunk): Path =
    if record.download.mode == "default" then rawPath(record.images.find(_.observation.frame_id == chunk.frame_id).get)
    else preparedPath(record.download.id, chunk.id)
  private def exists(path: Path): Task[Boolean] = ZIO.attemptBlocking(Files.isRegularFile(path) && Files.size(path) > 0)
  private def publish(output: Path)(produce: Path => Task[Unit]): Task[Unit] =
    val part = output.resolveSibling(output.getFileName.toString + "." + UUID.randomUUID().toString + ".part")
    (ZIO.attemptBlocking(Files.createDirectories(output.getParent)) *> produce(part) *> exists(part).flatMap { valid =>
      if !valid then ZIO.fail(ApiError("invalid_product", "The generated file was empty or absent"))
      else ZIO.attemptBlocking { Files.move(part, output, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); () }
    }).ensuring(ZIO.attemptBlocking(Files.deleteIfExists(part)).ignore)
  private def raw(image: ArchiveImage): Task[Path] =
    val path = rawPath(image)
    val lock = cacheLocks((java.lang.Long.parseLong(Hash.sha256(path.toString).take(8), 16) % cacheLocks.size).toInt)
    lock.withPermit(exists(path).flatMap { cached =>
      if cached then ZIO.succeed(path)
      else transfer.withPermit(publish(path)(archive.fetch(image, _))).as(path)
    })
  private def progress(chunks: List[Chunk]): Progress = Progress(true, chunks.size, chunks.count(_.status == "ready"), chunks.count(_.status == "failed"), chunks.count(_.status == "unavailable"))
  private def changeChunk(id: String, chunk: String, name: String)(f: Chunk => Chunk): Task[Unit] =
    repository.update(id, name, Some(chunk)) { record =>
      val chunks = record.download.chunks.map(c => if c.id == chunk then f(c) else c)
      record.copy(download = record.download.copy(chunks = chunks, progress = progress(chunks)))
    }.unit
  private def reference(record: JobRecord): Task[Option[Path]] = record.download.reference_frame_id match
    case None => ZIO.none
    case Some(id) => repository.image(id).flatMap {
      case Some(image) => raw(image).map(Some(_))
      case None => ZIO.fail(ApiError("not_found", "Reference frame not found"))
    }
  private def processChunk(record: JobRecord, image: ArchiveImage, chunk: Chunk): Task[Unit] =
    if !image.observation.is_available then ZIO.unit
    else
      val id = record.download.id
      val prepare = for
        source <- raw(image)
        ref <- if record.download.mode == "default" then ZIO.none else reference(record)
        path = if record.download.mode == "default" then source else preparedPath(id, chunk.id)
        _ <- if record.download.mode == "default" then ZIO.unit else publish(path)(processor.prepare(source, _, record.download.mode, ref, record.query))
        _ <- changeChunk(id, chunk.id, "chunk.ready")(_.copy(status = "ready", error = None))
      yield path
      prepare.foldZIO(
        error => changeChunk(id, chunk.id, "chunk.failed")(_.copy(status = "failed", preview_status = "failed", error = Some(ApiError.from(error)))),
        path => if !processor.supportsPreview then changeChunk(id, chunk.id, "job.updated")(_.copy(preview_status = "unavailable"))
        else publish(previewPath(id, chunk.id))(processor.preview(path, _)).foldZIO(
          error => changeChunk(id, chunk.id, "preview.failed")(_.copy(preview_status = "failed", error = Some(ApiError.from(error)))),
          _ => changeChunk(id, chunk.id, "preview.ready")(_.copy(preview_status = "ready"))
        )
      )
  private def runJob(claimed: JobRecord): Task[Unit] =
    val id = claimed.download.id
    val work = for
      images <- if claimed.images.nonEmpty || claimed.download.progress.discovery_complete then ZIO.succeed(claimed.images) else archive.search(claimed.query)
      _ <- repository.remember(images)
      record <- repository.update(id, "job.updated") { current =>
        val chunks = images.map { image =>
          val cid = Hash.sha256(s"$id|${image.observation.release}|${image.observation.frame_id}|${image.accessUrl}").take(40)
          val status = if image.observation.is_available then "pending" else "unavailable"
          Chunk(cid, image.observation.frame_id, status, status, s"/api/chunks/$cid/preview", s"/api/chunks/$cid")
        }
        current.copy(images = images, download = current.download.copy(status = "preparing", observations = images.map(_.observation), chunks = chunks, progress = progress(chunks)))
      }
      _ <- ZIO.foreachParDiscard(images.zip(record.download.chunks))((image, chunk) => processChunk(record, image, chunk)).withParallelism(4)
      _ <- repository.update(id, "job.completed") { current =>
        val failed = current.download.chunks.exists(c => c.status == "failed" || c.preview_status == "failed")
        current.copy(download = current.download.copy(status = if failed then "completed_with_errors" else "completed"))
      }
    yield ()
    work.catchAll(error => ZIO.logErrorCause(s"Download $id failed", Cause.fail(error)) *> repository.update(id, "job.completed") { current =>
      current.copy(download = current.download.copy(status = "failed", errors = List(ApiError.from(error))))
    }.unit)

  private[spaceapps] def worker: UIO[Unit] =
    (repository.claim.flatMap {
      case Some(record) => runJob(record)
      case None => ZIO.sleep(100.millis)
    }.catchAll(_ => ZIO.sleep(250.millis))).forever

  private def checkFiles(record: JobRecord): Task[Download] =
    ZIO.foldLeft(record.download.chunks)(record) { (current, chunk) =>
      val fit = if chunk.status == "ready" then exists(fitsPath(current, chunk)).map(!_) else ZIO.succeed(false)
      val png = if chunk.preview_status == "ready" then exists(previewPath(current.download.id, chunk.id)).map(!_) else ZIO.succeed(false)
      fit.zip(png).flatMap { (missingFit, missingPreview) =>
        if !missingFit && !missingPreview then ZIO.succeed(current)
        else repository.update(current.download.id, if missingFit then "chunk.failed" else "preview.failed", Some(chunk.id)) { latest =>
          val chunks = latest.download.chunks.map { c =>
            if c.id != chunk.id then c
            else c.copy(status = if missingFit then "failed" else c.status, preview_status = if missingPreview then "failed" else c.preview_status,
              error = Some(ApiError("cache_missing", "The cached resource is missing; submit the request again", true)))
          }
          latest.copy(download = latest.download.copy(chunks = chunks, progress = progress(chunks),
            status = if latest.download.terminal then "completed_with_errors" else latest.download.status))
        }
      }
    }.map(_.download)
  def get(id: String): Task[Download] = repository.get(id).flatMap(checkFiles)
  def resource(chunkId: String, preview: Boolean): Task[Resource] =
    for
      located <- repository.chunk(chunkId)
      _ <- checkFiles(located._1)
      latest <- repository.chunk(chunkId)
      (record, chunk) = latest
      status = if preview then chunk.preview_status else chunk.status
      result <- status match
        case "pending" => ZIO.succeed(Resource.Pending)
        case "unavailable" => ZIO.succeed(Resource.Failed(ApiError("unavailable", if preview then "Preview generation is unavailable" else "This archive product is unavailable")))
        case "failed" => ZIO.succeed(Resource.Failed(chunk.error.getOrElse(ApiError("resource_failed", "Resource preparation failed"))))
        case "ready" => ZIO.succeed(Resource.Ready(if preview then previewPath(record.download.id, chunk.id) else fitsPath(record, chunk)))
        case _ => ZIO.fail(ApiError("internal_error", "Unknown resource state"))
    yield result
  def events(id: String): ZStream[Any, Throwable, Event] = ZStream.unwrap {
    get(id) *> repository.snapshot(id).map { (download, cursor) =>
      val snapshot = ZStream.succeed(Event(cursor, "job.updated", Repository.payload(download)))
      if download.terminal then snapshot ++ ZStream.succeed(Event(cursor, "job.completed", Repository.payload(download)))
      else
        val updates = ZStream.unfoldChunkZIO(cursor) { next =>
          repository.eventsAfter(id, next).flatMap { events =>
            if events.isEmpty then ZIO.sleep(100.millis).as(Some((zio.Chunk.empty[Event], next)))
            else ZIO.succeed(Some((zio.Chunk.fromIterable(events), events.last.sequence)))
          }
        }.takeUntil(_.name == "job.completed")
        snapshot ++ updates
    }
  }

object Jobs:
  def make(repository: Repository, archive: Archive, processor: Processor, dataDir: Path,
    workers: Int = 2, transfers: Int = 4, maxJobs: Int = 32): ZIO[Scope, Throwable, Jobs] =
    for
      _ <- ZIO.fail(ApiError("invalid_configuration", "Worker and queue limits must be positive")).when(workers < 1 || transfers < 1 || maxJobs < 1)
      _ <- ZIO.attemptBlocking(Files.createDirectories(dataDir))
      _ <- ZIO.attemptBlocking {
        val uuid = "[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
        val owned = List("raw" -> s"[0-9a-f]{64}[.]fits[.]$uuid[.]part", "jobs" -> s"[0-9a-f]{40}[.](?:fits|png)[.]$uuid[.]part")
        owned.foreach { (directory, expression) =>
          val root = dataDir.resolve(directory)
          if Files.isDirectory(root) then
            val pattern = java.util.regex.Pattern.compile(expression)
            val paths = Files.walk(root)
            try paths.filter(p => Files.isRegularFile(p) && pattern.matcher(p.getFileName.toString).matches()).forEach(p => Files.deleteIfExists(p))
            finally paths.close()
        }
      }
      _ <- repository.recover
      semaphore <- Semaphore.make(transfers.toLong)
      locks <- ZIO.foreach(1 to 64)(_ => Semaphore.make(1))
      jobs = new Jobs(repository, archive, processor, dataDir, semaphore, locks.toVector, maxJobs)
      records <- repository.records
      _ <- ZIO.foreachDiscard(records)(jobs.checkFiles)
      _ <- ZIO.foreachDiscard(1 to workers)(_ => jobs.worker.forkScoped)
    yield jobs
