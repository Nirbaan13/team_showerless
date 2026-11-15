package spaceapps

import spaceapps.irsa.model.*

import spaceapps.irsa.service.*
import spaceapps.irsa.repository.Repository
import spaceapps.irsa.integrations.LiveArchive
import spaceapps.infra.controller.Api

import zio.*
import zio.http.Client
import zio.json.ast.Json
import zio.test.*
import com.sun.net.httpserver.{HttpExchange, HttpServer}
import java.net.{InetSocketAddress, URLDecoder}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files, Path}
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicInteger

object ArchiveSpec extends ZIOSpecDefault:
  private val query = Query(Json.Obj(), "POLYGON 359 -1 1 -1 1 1 359 1")
  private val fields = List("obs_publisher_did", "obs_collection", "energy_bandpassname", "t_min", "em_min", "em_max", "access_url", "obs_id")
  private def table(rows: List[List[String]], status: String = "OK"): String =
    "<VOTABLE xmlns=\"http://www.ivoa.net/xml/VOTable/v1.3\"><RESOURCE type=\"results\"><INFO name=\"QUERY_STATUS\" value=\"OK\"/><TABLE>" +
      fields.map(f => s"<FIELD name=\"$f\" datatype=\"char\" arraysize=\"*\"/>").mkString + "<DATA><TABLEDATA>" +
      rows.map(r => "<TR>" + r.map(v => "<TD>" + v.replace("&", "&amp;") + "</TD>").mkString + "</TR>").mkString +
      s"</TABLEDATA></DATA></TABLE><INFO name=\"QUERY_STATUS\" value=\"$status\"/></RESOURCE></VOTABLE>"
  private def row(url: String, detector: Int = 1, release: String = "spherex_dr1", did: String = "ivo://irsa/product/one") =
    List(did, release, s"SPHEREx-D$detector", "60000.5", "0.75e-6", "1.09e-6", url, "shared-exposure")
  private def respond(ex: HttpExchange, status: Int, bytes: Array[Byte]): Unit =
    ex.sendResponseHeaders(status, bytes.length.toLong)
    val output = ex.getResponseBody
    try output.write(bytes) finally output.close()
  private def server[A](f: (String, HttpExchange) => Unit)(use: String => ZIO[Client, Throwable, A]): ZIO[Client, Throwable, A] =
    ZIO.scoped:
      for
        http <- ZIO.acquireRelease(ZIO.attempt {
          val s = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0)
          s.createContext("/", exchange => f(s"http://127.0.0.1:${s.getAddress.getPort}", exchange))
          s.start()
          s
        })(s => ZIO.succeed(s.stop(0)))
        result <- use(s"http://127.0.0.1:${http.getAddress.getPort}")
      yield result
  private def code(result: Either[Throwable, Any]): Option[String] = result.left.toOption.collect { case e: ApiError => e.code }
  private def temporary[A](use: Path => ZIO[Client, Throwable, A]): ZIO[Client, Throwable, A] = ZIO.scoped {
    ZIO.acquireRelease(ZIO.attempt(Files.createTempFile("archive-spec-", ".fits")))(p => ZIO.attempt(Files.deleteIfExists(p)).orDie).flatMap(use)
  }
  private val fits = "SIMPLE  =                    T".padTo(2880, ' ').getBytes(UTF_8)
  def spec = suite("ArchiveSpec")(
    test("search preserves geometry and retrieves native DR1 and QR3 metadata without downloading bytes") {
      val requests = new ConcurrentLinkedQueue[String]()
      server((base, ex) => { requests.add(ex.getRequestURI.toString); respond(ex, 200, table(List(row(base + "/a"), row(base + "/b", 4, "spherex_qr3"))).getBytes(UTF_8)) }) { base =>
        for
          client <- ZIO.service[Client]
          images <- LiveArchive(client, base + "/SIA").search(query)
          decoded = URLDecoder.decode(requests.peek(), UTF_8)
        yield assertTrue(images.size == 2, images.map(_.observation.detector_array) == List(1, 4), images.head.observation.observation_date == "2023-02-25T12:00:00Z",
          images.head.observation.wavelength_min_um.contains(0.75), images.map(_.observation.frame_id).distinct.size == 2, requests.size == 1,
          decoded.contains("POS=" + query.position), decoded.contains("COLLECTION=spherex_dr1"), decoded.contains("COLLECTION=spherex_qr3"), decoded.contains("CALIB=2"), decoded.contains("DPTYPE=image"))
      }
    },
    test("configured metre channel bands and ISO dates become BAND and MJD while detector selection filters rows") {
      val requests = new ConcurrentLinkedQueue[String]()
      server((base, ex) => { requests.add(ex.getRequestURI.toString); respond(ex, 200, table(List(row(base + "/a"), row(base + "/b", 4))).getBytes(UTF_8)) }) { base =>
        for
          client <- ZIO.service[Client]
          images <- LiveArchive(client, base + "/SIA", channelBands = Map(7 -> (8e-7, 9e-7))).search(query.copy(detector = Some(4), channel = Some(7), after = Some("2023-02-25T00:00:00Z"), before = Some("2023-02-26T00:00:00Z")))
          decoded = URLDecoder.decode(requests.peek(), UTF_8)
        yield assertTrue(images.map(_.observation.detector_array) == List(4), decoded.contains("TIME=60000.0 60001.0"), decoded.contains("BAND=8.0E-7 9.0E-7"))
      }
    },
    test("missing channel calibration fails before networking") {
      ZIO.serviceWithZIO[Client](client => LiveArchive(client, "http://127.0.0.1:1/SIA").search(query.copy(channel = Some(7))).either).map(r => assertTrue(code(r).contains("unsupported_channel")))
    },
    test("QUERY_STATUS overflow never becomes partial success") {
      server((base, ex) => respond(ex, 200, table(List(row(base + "/a")), "OVERFLOW").getBytes(UTF_8))) { base =>
        ZIO.serviceWithZIO[Client](client => LiveArchive(client, base + "/SIA").search(query).either).map(r => assertTrue(code(r).contains("archive_overflow")))
      }
    },
    test("upstream error, unsupported serialization and external XML entities fail") {
      val docs = List(table(Nil, "ERROR"), "<VOTABLE><RESOURCE><INFO name=\"QUERY_STATUS\" value=\"OK\"/><TABLE><DATA><BINARY><STREAM>abc</STREAM></BINARY></DATA></TABLE></RESOURCE></VOTABLE>",
        "<!DOCTYPE VOTABLE [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><VOTABLE><RESOURCE><TABLE><DATA><TABLEDATA><TR><TD>&xxe;</TD></TR></TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>")
      ZIO.foreach(docs)(doc => server((_, ex) => respond(ex, 200, doc.getBytes(UTF_8)))(base => ZIO.serviceWithZIO[Client](c => LiveArchive(c, base + "/SIA").search(query).either))).map(rs => assertTrue(rs.map(code) == List(Some("archive_query_error"), Some("archive_invalid_response"), Some("archive_invalid_response"))))
    },
    test("missing or untrusted URLs cannot become downloadable products") {
      ZIO.foreach(List("https://evil.example/a", ""))(url => server((_, ex) => respond(ex, 200, table(List(row(url))).getBytes(UTF_8)))(base => ZIO.serviceWithZIO[Client](c => LiveArchive(c, base + "/SIA").search(query).either))).map(rs => assertTrue(rs.map(code) == List(Some("archive_untrusted_url"), Some("archive_invalid_response"))))
    },
    test("native product identity includes release and detector even when exposure obs_id matches") {
      server((base, ex) => respond(ex, 200, table(List(row(base + "/a"), row(base + "/b", 4), row(base + "/c", 1, "spherex_qr3"))).getBytes(UTF_8))) { base =>
        ZIO.serviceWithZIO[Client](c => LiveArchive(c, base + "/SIA").search(query)).map(images => assertTrue(images.map(_.observation.frame_id).distinct.size == 3))
      }
    },
    test("native FITS streams to disk unchanged") {
      server((_, ex) => respond(ex, 200, fits)) { base => temporary { path => for
        client <- ZIO.service[Client]
        _ <- LiveArchive(client, base + "/SIA").fetch(ArchiveImage(Observation("one", "", 1, "DR1"), base + "/native.fits"), path)
        bytes <- ZIO.attempt(Files.readAllBytes(path))
      yield assertTrue(bytes.toList == fits.toList) } }
    },
    test("preparation fetches an IRSA cutout while discovery retains its parent identity") {
      val requests = new ConcurrentLinkedQueue[String]()
      server((base, ex) => {
        requests.add(ex.getRequestURI.toString)
        if ex.getRequestURI.getPath == "/SIA" then respond(ex, 200, table(List(row(base + "/ibe/data/spherex/dr1/level2/native.fits"))).getBytes(UTF_8))
        else if Option(ex.getRequestURI.getRawQuery).exists(_.contains("center=")) then respond(ex, 200, fits)
        else respond(ex, 500, "Full image download is forbidden".getBytes(UTF_8))
      }) { base => ZIO.scoped { for
        client <- ZIO.service[Client]
        source = LiveArchive(client, base + "/SIA")
        q = Query.fromParameters("default", Map("right_ascension_deg" -> "1", "declination_deg" -> "2", "width_arcmin" -> "3", "height_arcmin" -> "5")).toOption.get
        dir <- ZIO.attempt(Files.createTempDirectory("cutout-job-"))
        repo <- Repository.open(dir.resolve("jobs.sqlite"))
        bounded <- CapacityArchive.make(source, dir, 1024*1024, 2880, 0)
        jobs <- Jobs.make(repo, bounded, NoProcessing, dir)
        originals <- jobs.search(q)
        accepted <- jobs.submit(q, "default", None)
        done <- (ZIO.sleep(20.millis) *> jobs.get(accepted.id)).repeatUntil(_.terminal)
        stored <- repo.get(done.id)
        firstFile <- jobs.resource(done.chunks.head.id, false)
        wider = Query.fromParameters("default", Map("right_ascension_deg" -> "1", "declination_deg" -> "2", "width_arcmin" -> "5", "height_arcmin" -> "5")).toOption.get
        second <- jobs.submit(wider, "default", None)
        secondDone <- (ZIO.sleep(20.millis) *> jobs.get(second.id)).repeatUntil(_.terminal)
        secondFile <- jobs.resource(secondDone.chunks.head.id, false)
        secondStored <- repo.get(second.id)
        reselected <- source.select(stored.images.head, wider)
        reused <- jobs.submit(q, "default", None)
        decoded = URLDecoder.decode(requests.toArray.toList.last.toString, UTF_8)
        _ <- jobs.search(q)
        remembered <- repo.image(originals.head.frame_id)
      yield assertTrue(done.status == "completed", secondDone.status == "completed", requests.size == 6, stored.images.head.observation == originals.head,
        remembered.contains(secondStored.images.head),
        firstFile != secondFile, reused.id == accepted.id, reselected == secondStored.images.head,
        originals.head.header_metadata("access_url").toString.contains("native.fits"), decoded.contains("center=1,2deg"), decoded.contains("size=")) } }
    } @@ TestAspect.withLiveClock @@ TestAspect.timeout(15.seconds),
    test("failed cutouts do not fall back to downloading a full image") {
      val fullRequests = new AtomicInteger()
      server((base, ex) => {
        if ex.getRequestURI.getPath == "/SIA" then respond(ex, 200, table(List(row(base + "/ibe/data/spherex/dr1/level2/native.fits"))).getBytes(UTF_8))
        else if Option(ex.getRequestURI.getRawQuery).exists(_.contains("center=")) then respond(ex, 404, "Cutout unavailable".getBytes(UTF_8))
        else { fullRequests.incrementAndGet(); respond(ex, 200, fits) }
      }) { base => ZIO.scoped { for
        client <- ZIO.service[Client]
        dir <- ZIO.attempt(Files.createTempDirectory("cutout-failure-"))
        repo <- Repository.open(dir.resolve("jobs.sqlite"))
        jobs <- Jobs.make(repo, LiveArchive(client, base + "/SIA"), NoProcessing, dir)
        q = Query.fromParameters("default", Map("right_ascension_deg" -> "1", "declination_deg" -> "2")).toOption.get
        accepted <- jobs.submit(q, "default", None)
        done <- (ZIO.sleep(20.millis) *> jobs.get(accepted.id)).repeatUntil(_.terminal)
      yield assertTrue(done.status == "completed_with_errors", done.chunks.head.error.exists(_.code == "archive_http_error"), fullRequests.get == 0) } }
    } @@ TestAspect.withLiveClock @@ TestAspect.timeout(15.seconds),
    test("false FITS, truncated records and oversize streams remove partial destinations") {
      ZIO.foreach(List("<html>failure</html>".getBytes(UTF_8), fits.take(100), fits ++ fits)) { bytes =>
        server((_, ex) => respond(ex, 200, bytes)) { base => temporary { path => for
          client <- ZIO.service[Client]
          result <- LiveArchive(client, base + "/SIA", maxBytes = 2880).fetch(ArchiveImage(Observation("one", "", 1, "DR1"), base + "/native.fits"), path).either
          exists <- ZIO.attempt(Files.exists(path))
        yield result.isLeft && !exists } }
      }.map(rs => assertTrue(rs.forall(identity)))
    },
    test("transient HTTP errors retry boundedly") {
      val attempts = new AtomicInteger()
      server((_, ex) => { if attempts.incrementAndGet() < 3 then respond(ex, 503, Array.emptyByteArray) else respond(ex, 200, table(Nil).getBytes(UTF_8)) }) { base =>
        ZIO.serviceWithZIO[Client](c => LiveArchive(c, base + "/SIA").search(query)).map(images => assertTrue(images.isEmpty, attempts.get == 3))
      }
    } @@ TestAspect.withLiveClock,
    test("transport failures are explicit retryable archive errors") {
      ZIO.serviceWithZIO[Client](c=>LiveArchive(c,"http://127.0.0.1:1/SIA").search(query).either).map { result=>
        assertTrue(result.left.toOption.exists { case e:ApiError=>e.code=="archive_unavailable" && e.retryable;case _=>false })
      }
    } @@ TestAspect.withLiveClock,
    test("metadata size and record limits fail explicitly") {
      val docs = List(" " * (8 * 1024 * 1024 + 1), table(List(row("https://irsa.ipac.caltech.edu/a"), row("https://irsa.ipac.caltech.edu/b"))))
      ZIO.foreach(docs)(doc => server((_, ex) => respond(ex, 200, doc.getBytes(UTF_8)))(base => ZIO.serviceWithZIO[Client](c => LiveArchive(c, base + "/SIA", maxRecords = 1).search(query).either))).map(rs => assertTrue(rs.map(code) == List(Some("archive_size_limit"), Some("archive_overflow"))))
    }
  ).provideLayerShared(Client.default) @@ TestAspect.sequential
