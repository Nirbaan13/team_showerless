package spaceapps.downloads.repository
import spaceapps.downloads.model.*
import spaceapps.infra.model.Event
import zio.*
import zio.json.*
import java.nio.file.{Files,Path}
import java.sql.{Connection,DriverManager}
import java.util.Base64
import java.nio.charset.StandardCharsets.UTF_8

final class DownloadsRepository private(path: Path):
  private def tx[A](f: Connection=>A): IO[ArchiveFailure,A] = ZIO.attemptBlocking {
    val c=DriverManager.getConnection(s"jdbc:sqlite:${path.toAbsolutePath}")
    try
      val s=c.createStatement()
      try { s.execute("PRAGMA busy_timeout=10000"); s.execute("BEGIN IMMEDIATE") } finally s.close()
      try
        val result=f(c)
        val end=c.createStatement(); try end.execute("COMMIT") finally end.close()
        result
      catch
        case e: Throwable =>
          val end=c.createStatement(); try end.execute("ROLLBACK") finally end.close()
          throw e
    finally c.close()
  }.mapError { case e: ArchiveFailure=>e; case _=>ArchiveFailure("storage_error","Archive state could not be accessed") }
  private def put(c: Connection,table: String,id: String,body: String): Unit =
    val s=c.prepareStatement(s"INSERT OR REPLACE INTO $table(id,body) VALUES (?,?)")
    try { s.setString(1,id);s.setString(2,body);s.executeUpdate();() } finally s.close()
  private def get[A:JsonDecoder](c: Connection,table: String,id: String): A =
    val s=c.prepareStatement(s"SELECT body FROM $table WHERE id=?")
    try
      s.setString(1,id); val r=s.executeQuery()
      try
        if !r.next() then throw ArchiveFailure("not_found","Archive job or record not found")
        r.getString(1).fromJson[A].fold(_=>throw ArchiveFailure("storage_error","Invalid stored archive metadata"),identity)
      finally r.close()
    finally s.close()
  def rememberIrsa(images: List[spaceapps.irsa.model.ArchiveImage]): IO[ArchiveFailure,Unit] = tx(c=>images.foreach(i=>put(c,"federated_irsa_products",i.observation.frame_id,i.toJson)))
  def irsaImage(id: String): IO[ArchiveFailure,spaceapps.irsa.model.ArchiveImage] = tx(get[spaceapps.irsa.model.ArchiveImage](_,"federated_irsa_products",id))
  def saveSearch(job: SearchSnapshot): IO[ArchiveFailure,Unit] = tx { c=>
    put(c,"federated_searches",job.id,job.toJson)
    job.records.foreach(r=>put(c,"federated_records",r.id,r.toJson))
  }
  def updateSearch(id: String)(f: SearchSnapshot=>SearchSnapshot): IO[ArchiveFailure,SearchSnapshot] = tx { c=>
    val next=f(get[SearchSnapshot](c,"federated_searches",id))
    put(c,"federated_searches",id,next.toJson)
    next.records.foreach(r=>put(c,"federated_records",r.id,r.toJson))
    next
  }
  def updateDownload(id: String,event: String = "job.updated")(f: DownloadSnapshot=>DownloadSnapshot): IO[ArchiveFailure,DownloadSnapshot] = tx { c=>
    val next=f(get[DownloadSnapshot](c,"federated_downloads",id)).manifest
    put(c,"federated_downloads",id,next.toJson)
    appendEvent(c,next,event)
    next
  }
  def search(id: String): IO[ArchiveFailure,SearchSnapshot] = tx(get[SearchSnapshot](_,"federated_searches",id))
  def record(id: String): IO[ArchiveFailure,ArchiveRecord] = tx(get[ArchiveRecord](_,"federated_records",id))
  def saveDownload(job: DownloadSnapshot): IO[ArchiveFailure,Unit] = tx { c=>
    put(c,"federated_downloads",job.id,job.manifest.toJson)
    appendEvent(c,job.manifest,"job.updated")
  }
  private def sequence(c:Connection,id:String):Long=
    val s=c.prepareStatement("SELECT COALESCE(MAX(sequence),0) FROM federated_download_events WHERE download_id=?")
    try
      s.setString(1,id)
      val r=s.executeQuery()
      try { r.next();r.getLong(1) } finally r.close()
    finally s.close()
  private def appendEvent(c:Connection,job:DownloadSnapshot,name:String):Unit=
    val next=sequence(c,job.id)+1
    val s=c.prepareStatement("INSERT INTO federated_download_events(download_id,sequence,name,data) VALUES(?,?,?,?)")
    try
      s.setString(1,job.id);s.setLong(2,next);s.setString(3,name);s.setString(4,job.toJson);s.executeUpdate();()
    finally s.close()
  /** Snapshot and cursor come from one transaction; updates cannot fall between them. */
  def snapshot(id:String):IO[ArchiveFailure,(DownloadSnapshot,Long)]=tx { c=>
    get[DownloadSnapshot](c,"federated_downloads",id)->sequence(c,id)
  }
  def eventsAfter(id:String,cursor:Long):IO[ArchiveFailure,List[Event]]=tx { c=>
    val s=c.prepareStatement("SELECT sequence,name,data FROM federated_download_events WHERE download_id=? AND sequence>? ORDER BY sequence LIMIT 256")
    try
      s.setString(1,id);s.setLong(2,cursor)
      val r=s.executeQuery()
      try
        val out=List.newBuilder[Event]
        while r.next() do out+=Event(r.getLong(1),r.getString(2),r.getString(3))
        out.result()
      finally r.close()
    finally s.close()
  }
  def download(id: String): IO[ArchiveFailure,DownloadSnapshot] = tx(get[DownloadSnapshot](_,"federated_downloads",id))
  def allSearches: IO[ArchiveFailure,List[SearchSnapshot]] = all[SearchSnapshot]("federated_searches")
  def allDownloads: IO[ArchiveFailure,List[DownloadSnapshot]] = all[DownloadSnapshot]("federated_downloads")
  private def all[A:JsonDecoder](table: String): IO[ArchiveFailure,List[A]] = tx { c=>
    val s=c.createStatement();val r=s.executeQuery(s"SELECT body FROM $table")
    try
      val b=List.newBuilder[A]
      while r.next() do b+=r.getString(1).fromJson[A].fold(_=>throw ArchiveFailure("storage_error","Invalid stored archive metadata"),identity)
      b.result()
    finally {r.close();s.close()}
  }
  def page(id: String,cursor: Option[String],limit: Int): IO[ArchiveFailure,SearchPage] = search(id).flatMap { job=>
    ZIO.attempt {
      if limit<1 || limit>200 then throw ArchiveFailure("invalid_cursor","Page limit must be 1 to 200")
      val offset=cursor.fold(0) { value=>
        val decoded=new String(Base64.getUrlDecoder.decode(value),UTF_8).split(":")
        if decoded.length!=3 || decoded(0)!=id || decoded(1).toLong!=job.generation then throw ArchiveFailure("stale_cursor","Cursor belongs to a different snapshot")
        decoded(2).toInt
      }
      if offset<0 || offset>job.records.size then throw ArchiveFailure("invalid_cursor","Invalid result offset")
      val records=job.records.slice(offset,offset+limit)
      val next=Option.when(offset+limit<job.records.size)(Base64.getUrlEncoder.withoutPadding().encodeToString(s"$id:${job.generation}:${offset+limit}".getBytes(UTF_8)))
      SearchPage(id,job.status,job.outcomes,records,records.size,next)
    }.mapError {case e: ArchiveFailure=>e;case _=>ArchiveFailure("invalid_cursor","Malformed result cursor")}
  }
object DownloadsRepository:
  def open(path: Path): IO[ArchiveFailure,DownloadsRepository] = ZIO.attemptBlocking {
    Option(path.toAbsolutePath.getParent).foreach(Files.createDirectories(_))
    val c=DriverManager.getConnection(s"jdbc:sqlite:${path.toAbsolutePath}")
    try
      val s=c.createStatement()
      try
        s.execute("PRAGMA busy_timeout=10000")
        s.execute("PRAGMA journal_mode=WAL")
        s.execute("CREATE TABLE IF NOT EXISTS federated_download_events(download_id TEXT NOT NULL,sequence INTEGER NOT NULL,name TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(download_id,sequence))")
        List("federated_searches","federated_records","federated_downloads","federated_irsa_products").foreach(t=>s.execute(s"CREATE TABLE IF NOT EXISTS $t(id TEXT PRIMARY KEY,body TEXT NOT NULL)"))
      finally s.close()
    finally c.close()
    new DownloadsRepository(path)
  }.mapError(_=>ArchiveFailure("storage_error","Cannot initialize archive SQLite tables"))
