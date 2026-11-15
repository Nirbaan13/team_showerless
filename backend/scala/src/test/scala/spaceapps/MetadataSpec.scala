package spaceapps

import spaceapps.irsa.model.*
import spaceapps.irsa.repository.Repository

import spaceapps.irsa.service.MetadataService
import spaceapps.infra.integrations.fits.FitsHeaders
import zio.*
import zio.http.Client
import zio.json.*
import zio.json.ast.Json
import zio.test.*
import com.sun.net.httpserver.{HttpExchange, HttpServer}
import java.net.{InetSocketAddress, URLDecoder}
import java.nio.charset.StandardCharsets.{US_ASCII, UTF_8}
import java.nio.file.{Files, Path}
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.{CountDownLatch, TimeUnit}
import scala.jdk.CollectionConverters.*

object MetadataSpec extends ZIOSpecDefault:
  private def obj(json: Json, names: String*): Json = names.foldLeft(json) { (j, name) => j match
    case Json.Obj(fields) => fields.find(_._1 == name).map(_._2).getOrElse(Json.Null)
    case _ => Json.Null
  }
  private def arr(json: Json): List[Json] = json match
    case Json.Arr(values) => values.toList
    case _ => Nil
  private def image(base: String, did: String = "ivo://irsa/product/one"): ArchiveImage =
    ArchiveImage(Observation("frame-one", "2025-05-01T00:00:00Z", 1, "DR1", header_metadata = Map(
      "obs_publisher_did" -> Json.Str(did), "obs_collection" -> Json.Str("spherex_dr1"),
      "access_url" -> Json.Str(base + "/ibe/data/spherex/dr1/one.fits"), "t_min" -> Json.Str("60794.5"))), base + "/ibe/data/spherex/dr1/one.fits")
  private val votable = """<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE type="results"><INFO name="QUERY_STATUS" value="OK"/><TABLE>
    <FIELD name="contentchecksum" datatype="char" arraysize="*"/><FIELD name="contentlength" datatype="long" unit="bytes"/>
    <FIELD name="quality_flag" datatype="int"><VALUES null="-999"/></FIELD><FIELD name="provenance_version" datatype="char" arraysize="*"/>
    <FIELD name="metrics_background" datatype="double" unit="Jy/pix"/><FIELD name="metrics_fluxdensitylimit" datatype="double" unit="Jy"/>
    <DATA><TABLEDATA><TR><TD>md5:abc</TD><TD>63492480</TD><TD>-999</TD><TD>7.0.5</TD><TD></TD><TD>1.2e-4</TD></TR></TABLEDATA></DATA>
    </TABLE></RESOURCE></VOTABLE>"""
  private def respond(ex: HttpExchange, status: Int, value: String): Unit =
    val bytes = value.getBytes(UTF_8)
    ex.sendResponseHeaders(status, bytes.length.toLong)
    try ex.getResponseBody.write(bytes) finally ex.close()
  private def server[A](handler: HttpExchange => Unit)(use: String => ZIO[Client & Scope, Throwable, A]): ZIO[Client, Throwable, A] = ZIO.scoped {
    for
      http <- ZIO.acquireRelease(ZIO.attempt {
        val s = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0)
        s.createContext("/", ex => handler(ex))
        s.start()
        s
      })(s => ZIO.succeed(s.stop(0)))
      result <- use(s"http://127.0.0.1:${http.getAddress.getPort}")
    yield result
  }
  private def temporary[A](use: Path => ZIO[Client & Scope, Throwable, A]): ZIO[Client, Throwable, A] = ZIO.scoped {
    ZIO.acquireRelease(ZIO.attempt(Files.createTempDirectory("metadata-spec-")))(p => ZIO.attemptBlocking {
      val files = Files.walk(p)
      try files.iterator().asScala.toList.reverse.foreach(Files.deleteIfExists(_)) finally files.close()
    }.orDie).flatMap(use)
  }
  private def header(cards: String*): Array[Byte] =
    val body = (cards.toList :+ "END").map(_.padTo(80, ' ')).mkString
    body.padTo(((body.length + 2879) / 2880) * 2880, ' ').getBytes(US_ASCII)
  private def multiFits(path: Path, large: Boolean = false): Unit =
    val primary = header("SIMPLE  =                    T", "BITPIX  =                    8", "NAXIS   =                    0", "EXTEND  =                    T", "VERSION = 'pipeline-v27'", "COMMENT first comment", "COMMENT second comment", "HISTORY first history", "HISTORY second history")
    val extension = header("XTENSION= 'IMAGE   '", "BITPIX  =                   16", "NAXIS   =                    2", s"NAXIS1  = ${if large then "1000000000" else "2"}", "NAXIS2  =                    2", "PCOUNT  =                    0", "GCOUNT  =                    1", "EXTNAME = 'IMAGE'", "BUNIT   = 'MJy/sr'", "CRVAL1  =                129.5 / degrees")
    val file = new java.io.RandomAccessFile(path.toFile, "rw")
    try
      file.write(primary)
      file.write(extension)
      val dataSize = if large then 4000000000L else 8L
      file.setLength(primary.length + extension.length + ((dataSize + 2879) / 2880) * 2880)
    finally file.close()

  def spec = suite("MetadataSpec")(
    test("cutout FITS headers are labelled and TAP continues to identify the parent artifact") {
      val requests=new ConcurrentLinkedQueue[String]()
      server(ex=>{requests.add(URLDecoder.decode(ex.getRequestURI.toString,UTF_8));respond(ex,200,votable)}) { base=>temporary {dir=>for
        repository <- Repository.open(dir.resolve("db.sqlite"))
        parent=image(base)
        subset=parent.copy(observation=parent.observation.copy(header_metadata=parent.observation.header_metadata-"access_url"),accessUrl=parent.accessUrl+"?center=1,2deg&size=0.1deg",sourceUrl=Some(parent.accessUrl))
        _ <- repository.remember(List(subset))
        path=dir.resolve("cutout.fits")
        _ <- ZIO.attemptBlocking(multiFits(path))
        client <- ZIO.service[Client]
        service <- MetadataService.make(repository,_=>ZIO.some(path),client,base+"/tap")
        result <- service.get("frame-one")
      yield assertTrue(obj(result,"fits","status")==Json.Str("available"),obj(result,"fits","spatial_subset")==Json.Bool(true),
        requests.peek().contains("a.uri = 'ibe/data/spherex/dr1/one.fits'"),!requests.peek().contains("center=")) }}
    },
    test("unknown frame fails before TAP or cached file lookup") {
      val requests = new AtomicInteger()
      server(ex => { requests.incrementAndGet(); respond(ex, 200, votable) }) { base => temporary { dir => for
        repository <- Repository.open(dir.resolve("db.sqlite"))
        callbacks <- Ref.make(0)
        client <- ZIO.service[Client]
        service <- MetadataService.make(repository, _ => callbacks.update(_ + 1).as(None), client, base + "/tap")
        result <- service.get("unknown").either
        count <- callbacks.get
      yield assertTrue(result.left.toOption.collect { case e: ApiError => e.code }.contains("not_found"), requests.get == 0, count == 0) } }
    },
    test("TAP preserves numeric types, declared nulls and units while SIA and observation remain available") {
      val requests = new ConcurrentLinkedQueue[String]()
      server(ex => { requests.add(URLDecoder.decode(ex.getRequestURI.toString, UTF_8)); respond(ex, 200, votable) }) { base => temporary { dir => for
        repository <- Repository.open(dir.resolve("db.sqlite"))
        _ <- repository.remember(List(image(base, "ivo://irsa/a'quoted")))
        client <- ZIO.service[Client]
        service <- MetadataService.make(repository, _ => ZIO.none, client, base + "/tap")
        result <- service.get("frame-one")
        row = arr(obj(result, "tap", "rows")).headOption.getOrElse(Json.Null)
        fields = arr(obj(result, "tap", "fields"))
        query = requests.peek()
      yield assertTrue(obj(result, "frame_id") == Json.Str("frame-one"), obj(result, "observation", "detector_array") == Json.Num(1),
        obj(result, "sia", "data", "t_min") == Json.Str("60794.5"), obj(result, "tap", "status") == Json.Str("available"),
        obj(row, "contentlength") == Json.Num(63492480), obj(row, "quality_flag") == Json.Null, obj(row, "metrics_background") == Json.Null,
        obj(row, "metrics_fluxdensitylimit") == Json.Num(BigDecimal("0.00012")), fields.exists(f => obj(f, "unit") == Json.Str("Jy/pix")),
        obj(result, "fits", "status") == Json.Str("not_downloaded"), requests.size == 1,
        query.contains("p.obs_publisher_did = 'ivo://irsa/a''quoted'"), query.contains("o.collection = 'spherex_dr1'"), query.contains("a.uri = 'ibe/data/spherex/dr1/one.fits'")) } }
    },
    test("real multi-HDU FITS preserves ordered COMMENT and HISTORY duplicates and extension structure") {
      server(ex => respond(ex, 200, votable)) { base => temporary { dir => for
        repository <- Repository.open(dir.resolve("db.sqlite"))
        _ <- repository.remember(List(image(base)))
        path = dir.resolve("native.fits")
        _ <- ZIO.attemptBlocking(multiFits(path))
        client <- ZIO.service[Client]
        service <- MetadataService.make(repository, _ => ZIO.some(path), client, base + "/tap")
        result <- service.get("frame-one")
        hdus = arr(obj(result, "fits", "hdus"))
        cards = hdus.headOption.toList.flatMap(h => arr(obj(h, "cards")))
        comments = cards.filter(c => obj(c, "key") == Json.Str("COMMENT"))
        history = cards.filter(c => obj(c, "key") == Json.Str("HISTORY"))
      yield assertTrue(obj(result, "status") == Json.Str("complete"), hdus.size == 2, comments.size == 2, history.size == 2,
        obj(comments.headOption.getOrElse(Json.Null), "comment") == Json.Str("first comment"),
        hdus.lift(1).exists(h => obj(h, "name") == Json.Str("IMAGE") && obj(h, "axes") == Json.Arr(Json.Num(2), Json.Num(2)))) } }
    },
    test("large sparse FITS is inspected without reading image arrays") {
      temporary { dir => for
        path <- ZIO.succeed(dir.resolve("large.fits"))
        _ <- ZIO.attemptBlocking(multiFits(path, large = true))
        result <- FitsHeaders.read(path)
      yield assertTrue(arr(obj(result, "hdus")).size == 2) }
    },
    test("overflowing FITS dimensions cannot masquerade as an empty data segment") {
      temporary { dir => for
        path <- ZIO.succeed(dir.resolve("overflow.fits"))
        bytes = header("SIMPLE  =                    T", "BITPIX  =                    8", "NAXIS   =                    2", "NAXIS1  =           4294967296", "NAXIS2  =           4294967296")
        _ <- ZIO.attempt(Files.write(path, bytes))
        result <- FitsHeaders.read(path).either
      yield assertTrue(result.isLeft) }
    },
    test("TAP failures and malformed FITS return explicit partial sources without losing persisted metadata") {
      ZIO.foreach(List((503, "busy"), (200, "<invalid/>"), (200, votable.replace("1.2e-4", "garbled")), (200, votable.replace("value=\"OK\"", "value=\"OVERFLOW\"")))) { (status, body) =>
        server(ex => respond(ex, status, body)) { base => temporary { dir => for
          repository <- Repository.open(dir.resolve("db.sqlite"))
          _ <- repository.remember(List(image(base)))
          path = dir.resolve("bad.fits")
          _ <- ZIO.attempt(Files.writeString(path, "not FITS"))
          client <- ZIO.service[Client]
          service <- MetadataService.make(repository, _ => ZIO.some(path), client, base + "/tap")
          result <- service.get("frame-one")
        yield obj(result, "status") == Json.Str("partial") && obj(result, "tap", "status") == Json.Str("error") && obj(result, "fits", "status") == Json.Str("error") && obj(result, "observation", "release") == Json.Str("DR1") } }
      }.map(results => assertTrue(results.forall(identity)))
    },
    test("TAP cache persists after reopen, coalesces concurrent calls and newly cached FITS becomes visible") {
      val requests = new AtomicInteger()
      server(ex => { requests.incrementAndGet(); respond(ex, 200, votable) }) { base => temporary { dir => for
        repository <- Repository.open(dir.resolve("db.sqlite"))
        _ <- repository.remember(List(image(base)))
        path = dir.resolve("native.fits")
        local <- Ref.make(Option.empty[Path])
        client <- ZIO.service[Client]
        service <- MetadataService.make(repository, _ => local.get, client, base + "/tap")
        results <- ZIO.collectAllPar(List.fill(12)(service.get("frame-one")))
        reopened <- Repository.open(dir.resolve("db.sqlite"))
        _ <- ZIO.attemptBlocking(multiFits(path))
        _ <- local.set(Some(path))
        next <- MetadataService.make(reopened, _ => local.get, client, base + "/tap")
        result <- next.get("frame-one")
      yield assertTrue(results.size == 12, requests.get == 1, obj(result, "fits", "status") == Json.Str("available")) } }
    },
    test("missing persisted TAP identity reports unavailable without sending an underconstrained query") {
      val requests = new AtomicInteger()
      server(ex => { requests.incrementAndGet(); respond(ex, 200, votable) }) { base => temporary { dir => for
        repository <- Repository.open(dir.resolve("db.sqlite"))
        _ <- repository.remember(List(ArchiveImage(Observation("frame-one", "", 1, "DR1"), base + "/native.fits")))
        client <- ZIO.service[Client]
        service <- MetadataService.make(repository, _ => ZIO.none, client, base + "/tap")
        result <- service.get("frame-one")
      yield assertTrue(obj(result, "tap", "status") == Json.Str("unavailable"), requests.get == 0) } }
    },
    test("cancelling the first metadata caller leaves its shared TAP lookup available to followers") {
      val entered = new CountDownLatch(1)
      val release = new CountDownLatch(1)
      val requests = new AtomicInteger()
      server(ex => {
        requests.incrementAndGet()
        entered.countDown()
        release.await(10, TimeUnit.SECONDS)
        try respond(ex, 200, votable) catch case _: java.io.IOException => ex.close()
      }) { base => temporary { dir => (for
        repository <- Repository.open(dir.resolve("db.sqlite"))
        _ <- repository.remember(List(image(base)))
        client <- ZIO.service[Client]
        service <- MetadataService.make(repository, _ => ZIO.none, client, base + "/tap")
        owner <- service.get("frame-one").forkScoped
        started <- ZIO.attemptBlocking(entered.await(3, TimeUnit.SECONDS))
        _ <- ZIO.fail(new RuntimeException("TAP fixture did not receive the first request")).unless(started)
        follower <- service.get("frame-one").forkScoped
        _ <- follower.status.repeatUntil {
          case suspended: Fiber.Status.Suspended => suspended.blockingOn == owner.id
          case _ => false
        }.timeoutFail(new RuntimeException("Follower did not await the shared promise"))(3.seconds)
        cancelled <- owner.interrupt.timeout(3.seconds)
        _ <- ZIO.succeed(release.countDown())
        completed <- follower.await.timeout(3.seconds)
        metadata = completed match
          case Some(Exit.Success(value)) => value
          case _ => Json.Null
        row = arr(obj(metadata, "tap", "rows")).headOption.getOrElse(Json.Null)
      yield assertTrue(cancelled.exists(_.isInterrupted), completed.exists(_.isSuccess),
        obj(metadata, "tap", "status") == Json.Str("available"), obj(row, "contentlength") == Json.Num(63492480), requests.get == 1))
        .ensuring(ZIO.succeed(release.countDown())) } }
    },
    test("expired TAP cache refreshes and retains explicitly stale values during upstream failure") {
      val requests = new AtomicInteger()
      server(ex => {
        if requests.incrementAndGet() == 1 then respond(ex, 200, votable) else respond(ex, 503, "temporarily unavailable")
      }) { base => temporary { dir => for
        repository <- Repository.open(dir.resolve("db.sqlite"))
        _ <- repository.remember(List(image(base)))
        client <- ZIO.service[Client]
        service <- MetadataService.make(repository, _ => ZIO.none, client, base + "/tap")
        first <- service.get("frame-one")
        _ <- ZIO.attemptBlocking {
          val connection = java.sql.DriverManager.getConnection(s"jdbc:sqlite:${dir.resolve("db.sqlite")}")
          try
            val statement = connection.createStatement()
            try statement.executeUpdate("UPDATE archive_metadata SET stored_at = 0") finally statement.close()
          finally connection.close()
        }
        result <- service.get("frame-one")
        row = arr(obj(result, "tap", "rows")).headOption.getOrElse(Json.Null)
      yield assertTrue(requests.get == 2, obj(first, "tap", "status") == Json.Str("available"),
        obj(result, "tap", "status") == Json.Str("stale"), obj(result, "tap", "error", "code") == Json.Str("metadata_http_error"),
        obj(row, "contentchecksum") == Json.Str("md5:abc"), obj(result, "status") == Json.Str("partial")) } }
    },
    test("application scope shutdown interrupts shared TAP work and releases its pending callers") {
      val entered = new CountDownLatch(1)
      val release = new CountDownLatch(1)
      val requests = new AtomicInteger()
      server(ex => {
        requests.incrementAndGet()
        entered.countDown()
        release.await(10, TimeUnit.SECONDS)
        try respond(ex, 200, votable) catch case _: java.io.IOException => ex.close()
      }) { base => temporary { dir => (for
        repository <- Repository.open(dir.resolve("db.sqlite"))
        _ <- repository.remember(List(image(base)))
        client <- ZIO.service[Client]
        applicationScope <- ZIO.acquireRelease(Scope.make)(_.close(Exit.unit))
        service <- MetadataService.make(repository, _ => ZIO.none, client, base + "/tap")
          .provideEnvironment(ZEnvironment[Scope](applicationScope))
        owner <- service.get("frame-one").forkScoped
        started <- ZIO.attemptBlocking(entered.await(3, TimeUnit.SECONDS))
        _ <- ZIO.fail(new RuntimeException("TAP fixture did not receive the first request")).unless(started)
        follower <- service.get("frame-one").forkScoped
        _ <- follower.status.repeatUntil {
          case suspended: Fiber.Status.Suspended => suspended.blockingOn == owner.id
          case _ => false
        }.timeoutFail(new RuntimeException("Follower did not await the shared promise"))(3.seconds)
        closed <- applicationScope.close(Exit.unit).timeout(3.seconds)
        ownerExit <- owner.await.timeout(500.millis)
        followerExit <- follower.await.timeout(500.millis)
      yield assertTrue(closed.isDefined, ownerExit.exists(_.isInterrupted), followerExit.exists(_.isInterrupted), requests.get == 1))
        .ensuring(ZIO.succeed(release.countDown())) } }
    },
    test("TAP metadata rejects oversized replies, unsafe XML and ambiguous exact-product matches") {
      val docs = List(" " * (2 * 1024 * 1024 + 1),
        "<!DOCTYPE VOTABLE [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><VOTABLE><RESOURCE>&xxe;</RESOURCE></VOTABLE>",
        votable.replace("</TR>", "</TR><TR><TD>md5:other</TD><TD>1</TD><TD></TD><TD>old</TD><TD></TD><TD></TD></TR>"))
      ZIO.foreach(docs) { doc => server(ex => respond(ex, 200, doc)) { base => temporary { dir => for
        repository <- Repository.open(dir.resolve("db.sqlite"))
        _ <- repository.remember(List(image(base)))
        client <- ZIO.service[Client]
        service <- MetadataService.make(repository, _ => ZIO.none, client, base + "/tap")
        result <- service.get("frame-one")
      yield obj(result, "tap", "error", "code") } } }.map(codes => assertTrue(codes == List(
        Json.Str("metadata_size_limit"), Json.Str("metadata_invalid_response"), Json.Str("metadata_ambiguous"))))
    }
  ).provideLayerShared(Client.default) @@ TestAspect.sequential @@ TestAspect.withLiveClock
