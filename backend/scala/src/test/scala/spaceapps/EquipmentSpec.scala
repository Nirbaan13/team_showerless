package spaceapps
import spaceapps.infra.service.FileCache

import spaceapps.irsa.model.*
import spaceapps.equipment.service.EquipmentService

import spaceapps.irsa.service.*
import spaceapps.irsa.repository.Repository
import spaceapps.equipment.integrations.CalibrationLimits
import zio.*
import zio.http.Client
import zio.json.*
import zio.json.ast.Json
import zio.test.*
import com.sun.net.httpserver.{HttpExchange, HttpServer}
import java.net.InetSocketAddress
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files, Path}
import java.util.concurrent.atomic.AtomicInteger

object EquipmentSpec extends ZIOSpecDefault:
  private val yaml = "detectors:\n  1: [1.0, 2.0]\n".getBytes(UTF_8)
  private val ecsv = "# %ECSV 1.0\n# ---\n# datatype:\n# - {name: scale, datatype: float64}\nscale\n1.0\n".getBytes(UTF_8)
  private val fits = "SIMPLE  =                    T".padTo(2880, ' ').getBytes(UTF_8)
  private def reply(ex: HttpExchange, status: Int, body: Array[Byte]): Unit =
    ex.sendResponseHeaders(status, body.length.toLong)
    try ex.getResponseBody.write(body) finally ex.close()
  private def fixture[A](bad: Boolean = false, transferBody: Option[Array[Byte]] = None, truncatedListing: Boolean = false, extraDetector: Boolean = false, transferStatus: Int = 200, directoryHits: AtomicInteger = new AtomicInteger(), listingPayload: Option[String] = None, paginated: Boolean = false)(use: (String, Path, AtomicInteger) => ZIO[Client, Throwable, A]): ZIO[Client, Throwable, A] = ZIO.scoped {
    for
      dir <- ZIO.attempt(Files.createTempDirectory("equipment-spec-"))
      serverHits = new AtomicInteger()
      server <- ZIO.acquireRelease(ZIO.attempt {
        val s = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0)
        s.createContext("/", ex => {
          val q = Option(ex.getRequestURI.getQuery).getOrElse("")
          if q.contains("prefix=dr1/") || q.contains("prefix=qr3/") then
            directoryHits.incrementAndGet()
            val rel = if q.contains("qr3/") then "qr3" else "dr1"
            val contents = if q.contains("gain_factors/") then
              s"<Contents><Key>$rel/gain_factors/base-2026-191/gain_factors_spx_base-2026-191.yaml</Key><Size>${yaml.length}</Size></Contents>" +
                (if bad then "<Contents><Key>../secret.yaml</Key><Size>5</Size></Contents>" else "")
            else if q.contains("xtalk_class1/") then s"<Contents><Key>$rel/xtalk_class1/base-2026-191/1/xtalk_class1_D1_spx_base-2026-191.ecsv</Key><Size>${ecsv.length}</Size></Contents>"
            else if q.contains("dark/") then s"<Contents><Key>$rel/dark/cal-drk-v4-2026-191/4/dark_D4_spx_cal-drk-v4-2026-191.fits</Key><Size>${fits.length}</Size></Contents>"
            else s"<CommonPrefixes><Prefix>$rel/gain_factors/</Prefix></CommonPrefixes><CommonPrefixes><Prefix>$rel/level2/</Prefix></CommonPrefixes>" +
              (if extraDetector then s"<CommonPrefixes><Prefix>$rel/xtalk_class1/</Prefix></CommonPrefixes><CommonPrefixes><Prefix>$rel/dark/</Prefix></CommonPrefixes>" else "")
            val page = if paginated && q.contains("gain_factors/") && !q.contains("continuation-token=") then
              "<ListBucketResult><IsTruncated>true</IsTruncated><NextContinuationToken>next-page</NextContinuationToken></ListBucketResult>"
            else s"<ListBucketResult><IsTruncated>$truncatedListing</IsTruncated>$contents</ListBucketResult>"
            reply(ex,200,listingPayload.getOrElse(page).getBytes(UTF_8))
          else { serverHits.incrementAndGet(); if transferStatus == 302 then ex.getResponseHeaders.add("Location", "http://127.0.0.1:1/private"); reply(ex,transferStatus,transferBody.getOrElse(if ex.getRequestURI.getPath.endsWith(".ecsv") then ecsv else if ex.getRequestURI.getPath.endsWith(".fits") then fits else yaml)) }
        })
        s.start(); s
      })(s => ZIO.succeed(s.stop(0)))
      out <- use(s"http://127.0.0.1:${server.getAddress.getPort}/",dir,serverHits)
    yield out
  }
  private def products(j: Json): List[Json] = j.asObject.flatMap(_.get("calibration_products")).flatMap(_.asArray).toList.flatten.toList
  private def id(j: Json): String = j.asObject.flatMap(_.get("id")).flatMap(_.asString).get
  def spec = suite("EquipmentSpec")(
    test("discovers versions and persisted YAML downloads without science FITS validation") {
      fixture() { (base,dir,hits) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base)
        result <- equipment.catalog("DR1",Some(4))
        product = products(result).head
        file <- equipment.file(id(product))
        reopened <- Repository.open(dir.resolve("db.sqlite"))
        restarted <- EquipmentService.make(reopened,dir,client,base)
        again <- restarted.file(id(product))
        bytes <- ZIO.attempt(Files.readAllBytes(file.path))
      yield assertTrue(products(result).size == 1, product.toJson.contains("base-2026-191"), file.fileName.endsWith(".yaml"), bytes.toList == yaml.toList, file.path == again.path, hits.get == 1)
      }
    },
    test("equipment files participate in LRU eviction and can be downloaded again") {
      fixture(extraDetector=true) { (base,dir,hits) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base,CalibrationLimits(maxFileBytes=3000,cacheBytes=100,minFreeBytes=0))
        result <- equipment.catalog("DR1",None)
        all=products(result)
        firstId=id(all.find(_.toJson.contains(".yaml")).get)
        secondId=id(all.find(_.toJson.contains(".ecsv")).get)
        first <- equipment.file(firstId)
        second <- equipment.file(secondId)
        evicted <- ZIO.attempt(!Files.exists(first.path))
        again <- equipment.file(firstId)
      yield assertTrue(evicted,Files.exists(again.path),!Files.exists(second.path),hits.get==3)
      }
    },
    test("HTTP calibration responses share the global reader lease until their scope closes") {
      fixture() { (base,dir,hits) => ZIO.scoped { for
        repo <- Repository.open(dir.resolve("jobs.sqlite"))
        client <- ZIO.service[Client]
        cache <- FileCache.open(dir,dir.resolve("jobs.sqlite"),yaml.length,yaml.length,0)
        equipment <- EquipmentService.make(repo,dir,client,base,capacity=Some(cache))
        catalogue <- equipment.catalog("DR1",None)
        productId=id(products(catalogue).head)
        source=new Archive:
          def search(q:Query)=ZIO.succeed(Nil)
          def fetch(i:ArchiveImage,p:Path)=ZIO.unit
        jobs <- Jobs.make(repo,source,NoProcessing,dir)
        api <- spaceapps.infra.controller.Api.make(jobs,"test",Path.of("docs/openapi.yaml"),equipment=Some(equipment))
        scope <- Scope.make
        response <- scope.extend(api.routes.runZIO(zio.http.Request.get(s"http://localhost/api/equipment/calibrations/$productId")))
        next=dir.resolve("raw").resolve("f"*64+".fits")
        produce=(p:Path)=>ZIO.attempt {Files.write(p,yaml);()}
        blocked <- cache.publish(next)(produce).exit
        bytes <- response.body.asChunk
        _ <- scope.close(Exit.unit)
        released <- cache.publish(next)(produce).exit
      yield assertTrue(response.status==zio.http.Status.Ok,bytes.toArray.toList==yaml.toList,blocked.isFailure,released.isSuccess,hits.get==1) } }
    },
    test("catalogue cache survives reopen and refreshes when its persisted TTL expires") {
      val directories = new AtomicInteger()
      fixture(directoryHits=directories) { (base,dir,_) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        first <- EquipmentService.make(repo,dir,client,base)
        _ <- first.catalog("DR1",None)
        _ <- first.catalog("DR1",Some(1))
        reopened <- Repository.open(dir.resolve("db.sqlite"))
        next <- EquipmentService.make(reopened,dir,client,base)
        _ <- next.catalog("DR1",None)
        cachedCalls = directories.get
        _ <- ZIO.attemptBlocking {
          val connection=java.sql.DriverManager.getConnection(s"jdbc:sqlite:${dir.resolve("db.sqlite")}")
          try
            val statement=connection.createStatement()
            try statement.executeUpdate("UPDATE archive_metadata SET stored_at=1 WHERE cache_key LIKE 'equipment:catalog:%'") finally statement.close()
          finally connection.close()
        }
        _ <- next.catalog("DR1",None)
      yield assertTrue(cachedCalls == 2, directories.get == 4)
      }
    },
    test("bounded pagination discovers files after the first page") {
      val directories = new AtomicInteger()
      fixture(paginated=true,directoryHits=directories) { (base,dir,_) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base)
        result <- equipment.catalog("DR1",None)
      yield assertTrue(products(result).size == 1, directories.get == 3)
      }
    },
    test("malformed, entity-bearing and oversized directory responses fail explicitly") {
      val docs=List("<html>error</html>","<!DOCTYPE ListBucketResult [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><ListBucketResult><IsTruncated>false</IsTruncated></ListBucketResult>"," " * (2*1024*1024+1))
      ZIO.foreach(docs) { doc => fixture(listingPayload=Some(doc)) { (base,dir,_) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base)
        result <- equipment.catalog("DR1",None).either
      yield result.isLeft
      } }.map(results => assertTrue(results.forall(identity)))
    },
    test("unknown and malicious IDs never issue file requests") {
      fixture() { (base,dir,hits) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base)
        outcomes <- ZIO.foreach(List("../../passwd", "a" * 64))(equipment.file(_).either)
      yield assertTrue(outcomes.forall(_.isLeft), hits.get == 0)
      }
    },
    test("concurrent download calls share one completed atomic file") {
      fixture() { (base,dir,hits) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base)
        result <- equipment.catalog("QR3",None)
        files <- ZIO.foreachPar(1 to 8)(_ => equipment.file(id(products(result).head)))
      yield assertTrue(files.map(_.path).distinct.size == 1, hits.get == 1)
      }
    },
    test("unsafe upstream keys reject discovery") {
      fixture(true) { (base,dir,_) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base)
        result <- equipment.catalog("DR1",None).either
      yield assertTrue(result.isLeft)
      }
    },
    test("detector filter retains shared products and selects exact detector products") {
      fixture(extraDetector=true) { (base,dir,_) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base)
        one <- equipment.catalog("DR1",Some(1))
        four <- equipment.catalog("DR1",Some(4))
        table <- equipment.file(id(products(one).find(_.toJson.contains(".ecsv")).get))
        image <- equipment.file(id(products(four).find(_.toJson.contains(".fits")).get))
        tableBytes <- ZIO.attempt(Files.readAllBytes(table.path))
        imageBytes <- ZIO.attempt(Files.readAllBytes(image.path))
      yield assertTrue(products(one).size == 2, products(four).size == 2, table.contentType == "text/plain", image.contentType == "application/fits", tableBytes.toList == ecsv.toList, imageBytes.toList == fits.toList)
      }
    },
    test("truncated transfers remove partial cache files") {
      fixture(transferBody=Some(yaml.take(5))) { (base,dir,hits) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base)
        result <- equipment.catalog("DR1",None)
        failure <- equipment.file(id(products(result).head)).either
        entries <- ZIO.attempt { val stream=Files.list(dir.resolve("calibration-cache")); try stream.count() finally stream.close() }
      yield assertTrue(failure.isLeft, hits.get == 1, entries == 0)
      }
    },
    test("missing pagination token rejects incomplete catalogue") {
      fixture(truncatedListing=true) { (base,dir,_) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base)
        result <- equipment.catalog("DR1",None).either
      yield assertTrue(result.isLeft)
      }
    },
    test("redirect responses cannot become downloaded calibration files") {
      fixture(transferStatus=302) { (base,dir,hits) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base)
        result <- equipment.catalog("DR1",None)
        failure <- equipment.file(id(products(result).head)).either
      yield assertTrue(failure.left.toOption.collect { case e:ApiError => e.code }.contains("calibration_unavailable"), hits.get == 1)
      }
    },
    test("free-space reserve cannot overflow and bypass admission") {
      fixture() { (base,dir,hits) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base,CalibrationLimits(minFreeBytes=Long.MaxValue))
        result <- equipment.catalog("DR1",None)
        failure <- equipment.file(id(products(result).head)).either
      yield assertTrue(failure.isLeft, hits.get == 0)
      }
    },
    test("oversized transfers remove partial cache files") {
      fixture(transferBody=Some(yaml ++ yaml)) { (base,dir,hits) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base)
        result <- equipment.catalog("DR1",None)
        failure <- equipment.file(id(products(result).head)).either
        entries <- ZIO.attempt { val stream=Files.list(dir.resolve("calibration-cache")); try stream.count() finally stream.close() }
      yield assertTrue(failure.isLeft, hits.get == 1, entries == 0)
      }
    },
    test("startup reclaims abandoned owned partial files and preserves unrelated files") {
      fixture() { (base,dir,hits) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        cache <- ZIO.attempt(Files.createDirectories(dir.resolve("calibration-cache")))
        abandoned = cache.resolve("a" * 64 + ".part")
        sentinel = cache.resolve("unrelated.part")
        _ <- ZIO.attempt {
          Files.write(abandoned,Array.fill[Byte](128)(7))
          Files.write(sentinel,Array[Byte](9,8,7))
        }
        equipment <- EquipmentService.make(repo,dir,client,base,CalibrationLimits(maxFileBytes=128,cacheBytes=yaml.length+3,minFreeBytes=0))
        result <- equipment.catalog("DR1",None)
        file <- equipment.file(id(products(result).head))
        retained <- ZIO.attempt(Files.readAllBytes(sentinel))
        bytes <- ZIO.attempt(Files.readAllBytes(file.path))
      yield assertTrue(!Files.exists(abandoned),retained.toList == List[Byte](9,8,7),bytes.toList == yaml.toList,hits.get == 1)
      }
    },
    test("startup rejects symlink partial files without changing their targets") {
      fixture() { (base,dir,hits) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        cache <- ZIO.attempt(Files.createDirectories(dir.resolve("calibration-cache")))
        target = dir.resolve("sentinel")
        abandoned = cache.resolve("b" * 64 + ".part")
        _ <- ZIO.attempt {
          Files.write(target,Array[Byte](9,8,7))
          Files.createSymbolicLink(abandoned,target)
        }
        result <- EquipmentService.make(repo,dir,client,base).either
        retained <- ZIO.attempt(Files.readAllBytes(target))
      yield assertTrue(result.isLeft,Files.isSymbolicLink(abandoned),retained.toList == List[Byte](9,8,7),hits.get == 0)
      }
    },
    test("quota failure precedes transfer") {
      fixture() { (base,dir,hits) => for
        repo <- Repository.open(dir.resolve("db.sqlite"))
        client <- ZIO.service[Client]
        equipment <- EquipmentService.make(repo,dir,client,base,CalibrationLimits(maxFileBytes=128,cacheBytes=1,minFreeBytes=0))
        result <- equipment.catalog("DR1",None)
        failure <- equipment.file(id(products(result).head)).either
      yield assertTrue(failure.isLeft, hits.get == 0)
      }
    }
  ).provideLayerShared(Client.default) @@ TestAspect.sequential
