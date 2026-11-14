package spaceapps.archive
import zio.*
import zio.json.*
import java.nio.file.{Files,Path}
import java.sql.{Connection,DriverManager}
import java.util.Base64
import java.nio.charset.StandardCharsets.UTF_8

final class ArchiveRepository private(path: Path):
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
  def rememberIrsa(images: List[spaceapps.domain.ArchiveImage]): IO[ArchiveFailure,Unit] = tx(c=>images.foreach(i=>put(c,"federated_irsa_products",i.observation.frame_id,i.toJson)))
  def irsaImage(id: String): IO[ArchiveFailure,spaceapps.domain.ArchiveImage] = tx(get[spaceapps.domain.ArchiveImage](_,"federated_irsa_products",id))
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
  def updateDownload(id: String)(f: DownloadSnapshot=>DownloadSnapshot): IO[ArchiveFailure,DownloadSnapshot] = tx { c=>
    val next=f(get[DownloadSnapshot](c,"federated_downloads",id));put(c,"federated_downloads",id,next.toJson);next
  }
  def search(id: String): IO[ArchiveFailure,SearchSnapshot] = tx(get[SearchSnapshot](_,"federated_searches",id))
  def record(id: String): IO[ArchiveFailure,ArchiveRecord] = tx(get[ArchiveRecord](_,"federated_records",id))
  def saveDownload(job: DownloadSnapshot): IO[ArchiveFailure,Unit] = tx(put(_,"federated_downloads",job.id,job.toJson))
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
object ArchiveRepository:
  def open(path: Path): IO[ArchiveFailure,ArchiveRepository] = ZIO.attemptBlocking {
    Option(path.toAbsolutePath.getParent).foreach(Files.createDirectories(_))
    val c=DriverManager.getConnection(s"jdbc:sqlite:${path.toAbsolutePath}")
    try
      val s=c.createStatement()
      try
        s.execute("PRAGMA busy_timeout=10000")
        s.execute("PRAGMA journal_mode=WAL")
        List("federated_searches","federated_records","federated_downloads","federated_irsa_products").foreach(t=>s.execute(s"CREATE TABLE IF NOT EXISTS $t(id TEXT PRIMARY KEY,body TEXT NOT NULL)"))
      finally s.close()
    finally c.close()
    new ArchiveRepository(path)
  }.mapError(_=>ArchiveFailure("storage_error","Cannot initialize archive SQLite tables"))
