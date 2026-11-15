package spaceapps.repository

import spaceapps.domain.*

import zio.{Chunk as _, *}
import zio.json.*
import java.nio.file.{Files, Path}
import java.sql.{Connection, DriverManager, ResultSet}
import java.util.UUID
import java.nio.charset.StandardCharsets.UTF_8

/** Short transactions keep claims, manifests and ordered events consistent across workers. */
final class Repository private (path: Path, metadataCacheBytes: Long):
  private def transaction[A](body: Connection => A): Task[A] = ZIO.attemptBlocking {
    val connection = DriverManager.getConnection(s"jdbc:sqlite:${path.toAbsolutePath}")
    try
      val s = connection.createStatement()
      try
        s.execute("PRAGMA busy_timeout=10000")
        s.execute("BEGIN IMMEDIATE")
      finally s.close()
      try
        val result = body(connection)
        val commit = connection.createStatement()
        try commit.execute("COMMIT") finally commit.close()
        result
      catch
        case error: Throwable =>
          val rollback = connection.createStatement()
          try rollback.execute("ROLLBACK") finally rollback.close()
          throw error
    finally connection.close()
  }
  private def rows[A](c: Connection, sql: String, args: List[Any] = Nil)(read: ResultSet => A): List[A] =
    val statement = c.prepareStatement(sql)
    try
      args.zipWithIndex.foreach((a, i) => statement.setObject(i + 1, a))
      val result = statement.executeQuery()
      val values = List.newBuilder[A]
      try while result.next() do values += read(result)
      finally result.close()
      values.result()
    finally statement.close()
  private def execute(c: Connection, sql: String, args: List[Any] = Nil): Unit =
    val statement = c.prepareStatement(sql)
    try
      args.zipWithIndex.foreach((a, i) => statement.setObject(i + 1, a))
      statement.executeUpdate()
      ()
    finally statement.close()
  private def decode[A: JsonDecoder](body: String): A = body.fromJson[A].fold(_ => throw ApiError("storage_error", "Stored job metadata could not be read"), identity)
  private def load(c: Connection, id: String): JobRecord = rows(c, "SELECT body FROM jobs WHERE id=?", List(id))(r => decode[JobRecord](r.getString(1))).headOption.getOrElse(throw ApiError("not_found", "Download not found"))
  private def store(c: Connection, record: JobRecord): Unit =
    execute(c, "UPDATE jobs SET body=?,status=? WHERE id=?", List(record.toJson, record.download.status, record.download.id))
    record.download.chunks.foreach(chunk => execute(c, "INSERT OR REPLACE INTO chunks(id,job_id) VALUES (?,?)", List(chunk.id, record.download.id)))
  private def event(c: Connection, record: JobRecord, name: String, chunk: Option[String] = None): Unit =
    execute(c, "INSERT INTO events(job_id,name,data) VALUES (?,?,?)", List(record.download.id, name, Repository.payload(record.download, chunk)))

  private[spaceapps] def initialize: Task[Unit] = ZIO.attemptBlocking {
    Option(path.toAbsolutePath.getParent).foreach(Files.createDirectories(_))
    val c = DriverManager.getConnection(s"jdbc:sqlite:${path.toAbsolutePath}")
    try
      val s = c.createStatement()
      try
        s.execute("PRAGMA journal_mode=WAL")
        s.execute("PRAGMA busy_timeout=10000")
        s.execute("CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, request_key TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL)")
        s.execute("CREATE INDEX IF NOT EXISTS jobs_request ON jobs(request_key)")
        s.execute("CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, job_id TEXT NOT NULL)")
        s.execute("CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL,name TEXT NOT NULL,data TEXT NOT NULL)")
        s.execute("CREATE INDEX IF NOT EXISTS events_job ON events(job_id,sequence)")
        s.execute("CREATE TABLE IF NOT EXISTS images(frame_id TEXT PRIMARY KEY,body TEXT NOT NULL)")
        s.execute("CREATE TABLE IF NOT EXISTS archive_metadata(cache_key TEXT PRIMARY KEY,body TEXT NOT NULL,stored_at INTEGER NOT NULL)")
        s.execute("CREATE INDEX IF NOT EXISTS archive_metadata_age ON archive_metadata(stored_at)")
      finally s.close()
    finally c.close()
  }
  def remember(images: List[ArchiveImage]): Task[Unit] = transaction { c =>
    images.foreach { image =>
      val previous = rows(c, "SELECT body FROM images WHERE frame_id=?", List(image.observation.frame_id))(r => decode[ArchiveImage](r.getString(1))).headOption
      // Metadata rediscovery must not discard the last selected subset of the same artifact.
      val stored = previous.filter(old => image.sourceUrl.isEmpty && old.sourceUrl.contains(image.accessUrl))
        .fold(image)(old => old.copy(observation = image.observation))
      execute(c, "INSERT OR REPLACE INTO images(frame_id,body) VALUES (?,?)", List(stored.observation.frame_id, stored.toJson))
    }
  }
  def image(id: String): Task[Option[ArchiveImage]] = transaction(c => rows(c, "SELECT body FROM images WHERE frame_id=?", List(id))(r => decode[ArchiveImage](r.getString(1))).headOption)
  def cachedMetadata(key: String): Task[Option[(String, Long)]] = transaction { c =>
    rows(c, "SELECT body,stored_at FROM archive_metadata WHERE cache_key=?", List(key))(r => (r.getString(1), r.getLong(2))).headOption
  }
  def cacheMetadata(key: String, body: String): Task[Unit] = ZIO.suspendSucceed {
    val bodyLimit = 4 * 1024 * 1024
    if body.length > bodyLimit || body.getBytes(UTF_8).length > bodyLimit then
      ZIO.fail(ApiError("metadata_cache_size_limit", "Metadata cache body exceeds the 4 MiB limit"))
    else transaction { c =>
      execute(c, "INSERT OR REPLACE INTO archive_metadata(cache_key,body,stored_at) VALUES (?,?,?)",
        List(key, body, java.time.Instant.now().getEpochSecond))
      var used = rows(c, "SELECT COALESCE(SUM(length(CAST(body AS BLOB))),0) FROM archive_metadata")(_.getLong(1)).head
      while used > metadataCacheBytes do
        val candidates = rows(c,
          "SELECT cache_key,length(CAST(body AS BLOB)) FROM archive_metadata WHERE cache_key <> ? AND cache_key NOT GLOB 'equipment:file:*' ORDER BY stored_at,rowid LIMIT 128",
          List(key))(r => (r.getString(1), r.getLong(2)))
        if candidates.isEmpty then throw ApiError("metadata_cache_capacity", "Protected calibration identities and the current entry exceed metadata cache capacity")
        candidates.iterator.takeWhile(_ => used > metadataCacheBytes).foreach { (candidate, bytes) =>
          execute(c, "DELETE FROM archive_metadata WHERE cache_key=?", List(candidate))
          used -= bytes
        }
    }
  }
  def accept(query: Query, mode: String, reference: Option[String], maxJobs: Int): Task[Download] = transaction { c =>
    val key = query.key(mode, reference)
    val existing = rows(c, "SELECT body FROM jobs WHERE request_key=? AND status NOT IN ('failed','completed_with_errors') ORDER BY rowid DESC LIMIT 1", List(key))(r => decode[JobRecord](r.getString(1)))
    existing.headOption match
      case Some(record) => record.download
      case None =>
        val active = rows(c, "SELECT COUNT(*) FROM jobs WHERE status NOT IN ('failed','completed','completed_with_errors')")(_.getInt(1)).head
        if active >= maxJobs then throw ApiError("capacity_exceeded", "The download queue is full; retry later", true)
        val id = UUID.randomUUID().toString
        val download = Download(id, "queued", mode, query.document, status_url = s"/api/downloads/$id", events_url = s"/api/downloads/$id/events", reference_frame_id = reference)
        val record = JobRecord(download, query, key)
        execute(c, "INSERT INTO jobs(id,request_key,status,body) VALUES (?,?,?,?)", List(id, key, download.status, record.toJson))
        event(c, record, "job.updated")
        download
  }
  def records: Task[List[JobRecord]] = transaction(c => rows(c, "SELECT body FROM jobs")(r => decode[JobRecord](r.getString(1))))
  def get(id: String): Task[JobRecord] = transaction(load(_, id))
  def chunk(id: String): Task[(JobRecord, Chunk)] = transaction { c =>
    val job = rows(c, "SELECT job_id FROM chunks WHERE id=?", List(id))(_.getString(1)).headOption.getOrElse(throw ApiError("not_found", "Chunk not found"))
    val record = load(c, job)
    (record, record.download.chunks.find(_.id == id).getOrElse(throw ApiError("not_found", "Chunk not found")))
  }
  def update(id: String, name: String, chunk: Option[String] = None)(f: JobRecord => JobRecord): Task[JobRecord] = transaction { c =>
    val record = f(load(c, id))
    store(c, record)
    event(c, record, name, chunk)
    record
  }
  def claim: Task[Option[JobRecord]] = transaction { c =>
    rows(c, "SELECT body FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1")(r => decode[JobRecord](r.getString(1))).headOption.map { old =>
      val claimed = old.copy(download = old.download.copy(status = "discovering"))
      store(c, claimed)
      event(c, claimed, "job.updated")
      claimed
    }
  }
  def recover: Task[Unit] = transaction { c =>
    rows(c, "SELECT body FROM jobs WHERE status NOT IN ('failed','completed','completed_with_errors')")(r => decode[JobRecord](r.getString(1))).foreach { old =>
      val next = old.copy(download = old.download.copy(status = "queued"))
      store(c, next)
      event(c, next, "job.updated")
    }
  }
  def snapshot(id: String): Task[(Download, Long)] = transaction { c =>
    val record = load(c, id)
    val cursor = rows(c, "SELECT COALESCE(MAX(sequence),0) FROM events WHERE job_id=?", List(id))(_.getLong(1)).head
    (record.download, cursor)
  }
  def eventsAfter(id: String, cursor: Long): Task[List[Event]] = transaction(c => rows(c, "SELECT sequence,name,data FROM events WHERE job_id=? AND sequence>? ORDER BY sequence LIMIT 256", List(id, cursor))(r => Event(r.getLong(1), r.getString(2), r.getString(3))))

object Repository:
  def open(path: Path, metadataCacheBytes: Long = 64L * 1024 * 1024): Task[Repository] =
    if metadataCacheBytes <= 0 then ZIO.fail(ApiError("metadata_cache_configuration", "Metadata cache capacity must be positive"))
    else
      val repository = new Repository(path, metadataCacheBytes)
      repository.initialize.as(repository)
  def payload(download: Download, chunk: Option[String] = None): String =
    val job = s",\"job_id\":${download.id.toJson}"
    chunk.flatMap(id => download.chunks.find(_.id == id)) match
      case Some(value) => value.toJson.dropRight(1) + job + s",\"chunk_id\":${value.id.toJson},\"progress\":${download.progress.toJson}}"
      case None => download.toJson.dropRight(1) + job + "}"
