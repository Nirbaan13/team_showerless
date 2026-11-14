package spaceapps

import spaceapps.domain.*
import spaceapps.integrations.irsa.LiveArchive
import spaceapps.repository.Repository
import zio.*
import zio.http.Client
import zio.json.*
import zio.test.*
import com.sun.net.httpserver.HttpServer
import java.net.{InetSocketAddress, URLDecoder}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.Files
import java.util.concurrent.ConcurrentLinkedQueue

object DeepArchiveSpec extends ZIOSpecDefault:
  private val region = Map("right_ascension_min_deg" -> "1", "right_ascension_max_deg" -> "1.01",
    "declination_min_deg" -> "2", "declination_max_deg" -> "2.01")
  private def query(deep: Boolean): Query = Query.fromParameters("range", region ++
    Option.when(deep)("survey" -> "deep")).toOption.get
  def spec = suite("Deep survey retrieval")(
    test("deep scope survives query serialization and never deduplicates to a wide job") {
      for
        dir <- ZIO.attempt(Files.createTempDirectory("deep-query-"))
        repo <- Repository.open(dir.resolve("jobs.sqlite"))
        wide <- repo.accept(query(false), "default", None, 10)
        deep <- repo.accept(query(true), "default", None, 10)
        reopened <- Repository.open(dir.resolve("jobs.sqlite"))
        saved <- reopened.get(deep.id)
      yield assertTrue(wide.id != deep.id, saved.query.deep, saved.query.document.toJson.contains("\"survey\":\"deep\""),
        query(true).toJson.fromJson[Query].exists(_.deep), !query(false).document.toJson.contains("survey"))
    },
    test("search accepts deep selection and rejects unknown or nontext surveys") {
      assertTrue(Query.fromJson("""{"right_ascension_deg":1,"declination_deg":2,"survey":"deep"}""").exists(_.deep),
        Query.fromParameters("range", region.updated("survey", "unknown")).isLeft,
        Query.fromJson("""{"right_ascension_deg":1,"declination_deg":2,"survey":true}""").isLeft)
    },
    test("deep discovery requests both deep collections and preserves IRSA TIME without downloading images") {
      val requests = new ConcurrentLinkedQueue[String]()
      ZIO.scoped {
        for
          http <- ZIO.acquireRelease(ZIO.attempt {
            val server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0)
            server.createContext("/SIA", ex => {
              requests.add(URLDecoder.decode(ex.getRequestURI.toString, UTF_8))
              val base = s"http://127.0.0.1:${server.getAddress.getPort}"
              val fields = List("obs_publisher_did", "obs_collection", "energy_bandpassname", "t_min", "access_url")
              val rows = List("spherex_dr1_deep", "spherex_qr3_deep").map(c =>
                s"<TR><TD>ivo://irsa/$c/one</TD><TD>$c</TD><TD>SPHEREx-D1</TD><TD>60000.0</TD><TD>$base/native.fits</TD></TR>").mkString
              val bytes = ("<VOTABLE><RESOURCE><INFO name=\"QUERY_STATUS\" value=\"OK\"/><TABLE>" +
                fields.map(f => s"<FIELD name=\"$f\"/>").mkString + s"<DATA><TABLEDATA>$rows</TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>").getBytes(UTF_8)
              ex.sendResponseHeaders(200, bytes.length)
              try ex.getResponseBody.write(bytes) finally ex.close()
            })
            server.start(); server
          })(s => ZIO.succeed(s.stop(0)))
          client <- ZIO.service[Client]
          images <- LiveArchive(client, s"http://127.0.0.1:${http.getAddress.getPort}/SIA").search(query(true).copy(
            after = Some("2023-02-25T00:00:00Z"), before = Some("2023-02-26T00:00:00Z")))
          url = requests.peek()
        yield assertTrue(requests.size == 1, url.contains("COLLECTION=spherex_dr1_deep&"),
          url.contains("COLLECTION=spherex_qr3_deep&"), url.contains("TIME=60000.0 60001.0"),
          images.map(_.observation.release) == List("DR1", "QR3"),
          images.forall(_.observation.header_metadata("obs_collection").toJson.contains("_deep")))
      }
    }
  ).provideLayerShared(Client.default)
