package spaceapps

import spaceapps.irsa.repository.Repository
import spaceapps.irsa.model.{ApiError, ArchiveImage, Observation}

import spaceapps.irsa.service.MetadataService
import zio.*
import zio.http.Client
import zio.json.ast.Json
import zio.test.*
import java.nio.file.{Files, Path}
import java.nio.charset.StandardCharsets.UTF_8
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import scala.jdk.CollectionConverters.*

object MetadataCacheSpec extends ZIOSpecDefault:
  private def temporary[A](use: Path => ZIO[Client & Scope, Throwable, A]): ZIO[Client, Throwable, A] = ZIO.scoped {
    ZIO.acquireRelease(ZIO.attempt(Files.createTempDirectory("metadata-quota-")))(p => ZIO.attemptBlocking {
      val files = Files.walk(p)
      try files.iterator().asScala.toList.reverse.foreach(Files.deleteIfExists(_)) finally files.close()
    }.orDie).flatMap(use)
  }
  private def code(result: Either[Throwable, Any]): Option[String] = result.left.toOption.collect { case e: ApiError => e.code }
  private def field(json: Json, names: String*): Json = names.foldLeft(json) { (value, name) => value match
    case Json.Obj(fields) => fields.find(_._1 == name).map(_._2).getOrElse(Json.Null)
    case _ => Json.Null
  }
  def spec = suite("Archive metadata persistence")(
    test("independent catalogue and frame cache entries survive reopening and replacement") {
      for
        dir <- ZIO.attempt(Files.createTempDirectory("metadata-cache-"))
        path = dir.resolve("state.sqlite")
        first <- Repository.open(path)
        absent <- first.cachedMetadata("frame:one")
        _ <- first.cacheMetadata("frame:one", "{\"version\":1}")
        _ <- first.cacheMetadata("equipment:DR1", "{\"files\":[]}")
        second <- Repository.open(path)
        saved <- second.cachedMetadata("frame:one")
        _ <- second.cacheMetadata("frame:one", "{\"version\":2}")
        updated <- first.cachedMetadata("frame:one")
        catalogue <- first.cachedMetadata("equipment:DR1")
      yield assertTrue(absent.isEmpty, saved.exists(_._1 == "{\"version\":1}"),
        saved.exists(_._2 > 0), updated.exists(_._1 == "{\"version\":2}"),
        catalogue.exists(_._1 == "{\"files\":[]}"))
    },
    test("quota evicts the oldest disposable entries while current and calibration identities survive reopening") {
      temporary { dir => for
        repository <- Repository.open(dir.resolve("state.sqlite"), metadataCacheBytes = 18)
        _ <- repository.cacheMetadata("equipment:file:protected", "\"keep\"")
        _ <- repository.cacheMetadata("frame:oldest", "\"old1\"")
        _ <- repository.cacheMetadata("frame:recent", "\"old2\"")
        _ <- repository.cacheMetadata("frame:current", "\"new1\"")
        reopened <- Repository.open(dir.resolve("state.sqlite"), metadataCacheBytes = 18)
        oldest <- reopened.cachedMetadata("frame:oldest")
        recent <- reopened.cachedMetadata("frame:recent")
        current <- reopened.cachedMetadata("frame:current")
        protectedEntry <- reopened.cachedMetadata("equipment:file:protected")
      yield assertTrue(oldest.isEmpty, recent.exists(_._1 == "\"old2\""), current.exists(_._1 == "\"new1\""), protectedEntry.exists(_._1 == "\"keep\"")) }
    },
    test("oversized UTF-8 bodies fail before replacing existing metadata") {
      temporary { dir => for
        repository <- Repository.open(dir.resolve("state.sqlite"))
        _ <- repository.cacheMetadata("frame:one", "\"old\"")
        result <- repository.cacheMetadata("frame:one", "é" * (2 * 1024 * 1024 + 1)).either
        original <- repository.cachedMetadata("frame:one")
        unchanged = original.exists(_._1 == "\"old\"")
      yield assertTrue(code(result).contains("metadata_cache_size_limit"), unchanged) }
    },
    test("insufficient protected-identity capacity rolls back the upsert and any attempted eviction") {
      temporary { dir => for
        repository <- Repository.open(dir.resolve("state.sqlite"), metadataCacheBytes = 12)
        _ <- repository.cacheMetadata("equipment:file:protected", "\"keep\"")
        _ <- repository.cacheMetadata("frame:disposable", "\"old1\"")
        result <- repository.cacheMetadata("equipment:file:new", "\"new123\"").either
        reopened <- Repository.open(dir.resolve("state.sqlite"), metadataCacheBytes = 12)
        original <- reopened.cachedMetadata("equipment:file:protected")
        disposable <- reopened.cachedMetadata("frame:disposable")
        rejected <- reopened.cachedMetadata("equipment:file:new")
      yield assertTrue(code(result).contains("metadata_cache_capacity"), original.exists(_._1 == "\"keep\""),
        disposable.exists(_._1 == "\"old1\""), rejected.isEmpty) }
    },
    test("a current replacement is never evicted to make its own oversized quota request fit") {
      temporary { dir => for
        repository <- Repository.open(dir.resolve("state.sqlite"), metadataCacheBytes = 12)
        _ <- repository.cacheMetadata("equipment:file:protected", "\"keep\"")
        _ <- repository.cacheMetadata("frame:current", "\"old1\"")
        result <- repository.cacheMetadata("frame:current", "\"new123\"").either
        current <- repository.cachedMetadata("frame:current")
      yield assertTrue(code(result).contains("metadata_cache_capacity"), current.exists(_._1 == "\"old1\"")) }
    },
    test("live TAP metadata remains available when protected entries exhaust the cache quota") {
      ZIO.scoped {
        val document = """<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE type="results"><INFO name="QUERY_STATUS" value="OK"/><TABLE><FIELD name="contentchecksum" datatype="char" arraysize="*"/><FIELD name="contentlength" datatype="long" unit="byte"/><DATA><TABLEDATA><TR><TD>md5:actual</TD><TD>63492480</TD></TR></TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>"""
        for
          server <- ZIO.acquireRelease(ZIO.attempt {
            val http = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0)
            http.createContext("/tap", exchange => {
              val bytes = document.getBytes(UTF_8)
              exchange.sendResponseHeaders(200, bytes.length.toLong)
              try exchange.getResponseBody.write(bytes) finally exchange.close()
            })
            http.start()
            http
          })(http => ZIO.succeed(http.stop(0)))
          result <- temporary { dir => for
            repository <- Repository.open(dir.resolve("state.sqlite"), metadataCacheBytes = 6)
            _ <- repository.cacheMetadata("equipment:file:protected", "\"keep\"")
            image = ArchiveImage(Observation("known", "", 1, "DR1", header_metadata = Map(
              "obs_publisher_did" -> Json.Str("ivo://irsa/one"), "obs_collection" -> Json.Str("spherex_dr1"))), "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/one.fits")
            _ <- repository.remember(List(image))
            client <- ZIO.service[Client]
            service <- MetadataService.make(repository, _ => ZIO.none, client, s"http://127.0.0.1:${server.getAddress.getPort}/tap")
            metadata <- service.get("known")
            protectedEntry <- repository.cachedMetadata("equipment:file:protected")
          yield assertTrue(field(metadata, "tap", "status") == Json.Str("available"),
            field(metadata, "tap", "rows") == Json.Arr(Json.Obj("contentchecksum" -> Json.Str("md5:actual"), "contentlength" -> Json.Num(63492480))),
            protectedEntry.exists(_._1 == "\"keep\"")) }
        yield result
      }
    }
  ).provideLayerShared(Client.default) @@ TestAspect.sequential @@ TestAspect.withLiveClock
