package spaceapps.archive
import spaceapps.domain.*
import spaceapps.archive.domain.*
import spaceapps.service.*
import spaceapps.archive.service.*
import spaceapps.archive.repository.ArchiveRepository
import spaceapps.archive.bootstrap.ArchiveRuntime
import spaceapps.archive.integrations.ArchiveProvider
import spaceapps.archive.integrations.protocol.*
import zio.*
import zio.http.Client
import zio.test.*
import java.nio.file.{Files,Path}
import java.net.{InetSocketAddress,URLDecoder}
import java.nio.charset.StandardCharsets.UTF_8
import java.io.ByteArrayOutputStream
import java.util.zip.GZIPOutputStream
import com.sun.net.httpserver.HttpServer
object ArchiveTransferSpec extends ZIOSpecDefault:
  val fits=(List("SIMPLE  =                    T","BITPIX  =                    8","NAXIS   =                    0","END").map(_.padTo(80,' ')).mkString).padTo(2880,' ').getBytes(UTF_8)
  def gzip(bytes: Array[Byte]): Array[Byte] =
    val out=new ByteArrayOutputStream();val gz=new GZIPOutputStream(out);gz.write(bytes);gz.close();out.toByteArray
  def server[A](bytes: Array[Byte],status: Int = 200)(use: (String,OriginPolicy)=>ZIO[Client,Throwable,A]): ZIO[Client,Throwable,A] = ZIO.scoped {
    for
      s <- ZIO.acquireRelease(ZIO.attempt {
        val s=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
        s.createContext("/",e=> { e.getResponseHeaders.add("Content-Type","application/octet-stream");e.sendResponseHeaders(status,if status==204 then -1 else bytes.length);if status!=204 then e.getResponseBody.write(bytes);e.close() });s.start();s
      })(s=>ZIO.succeed(s.stop(0)))
      base=s"http://127.0.0.1:${s.getAddress.getPort}"
      result <- use(base,OriginPolicy(Set.empty,Set(base)))
    yield result
  }
  def spec=suite("archive transfer")(
    test("SODA keeps native identifier and degree circle") {
      val d=DataLinkResolver.decode(VoProtocolSpec.fixture("cadc-neossat-links.xml")).services.head
      val url=URLDecoder.decode(SodaResolver.url(d,Circle(93.2,-17.58,0.01)),UTF_8)
      assertTrue(url.contains("ID=cadc:NEOSSAT/NEOS_SCI_2024335070357_cord.fits"),url.contains("CIRCLE=93.2 -17.58 0.01"))
    },
    test("origin policy permits qualified CANFAR hosts and rejects attacker subdomains") {
      assertTrue(scala.util.Try(OriginPolicy.cadc.validate("https://cadc-west-01.canfar.net/raven/f")).isSuccess,
        scala.util.Try(OriginPolicy.cadc.validate("https://cadc-west-01.canfar.net.evil.test/f")).isFailure)
    },
    test("octet-stream plain and gzip FITS validate, native compression preserved") {
      ZIO.foreach(List(fits,gzip(fits))) { bytes=>server(bytes) { (base,policy)=>for
        client <- ZIO.service[Client]
        dir <- ZIO.attempt(Files.createTempDirectory("archive-transfer-"))
        stored <- new StreamingDownloader(new ArchiveTransport(client),dir).fetch(ArchiveAsset("key","eso",base+"/fits"),policy)
        actual <- ZIO.attempt(Files.readAllBytes(dir.resolve("key")))
      yield stored.bytes==bytes.length && actual.toList==bytes.toList && stored.brightness_unit.isEmpty && !stored.analysisEligible } }.map(xs=>assertTrue(xs.forall(identity)))
    },
    test("decoded gzip budget breach removes every partial file") {
      server(gzip(fits)) { (base,policy)=>for
        client <- ZIO.service[Client]
        dir <- ZIO.attempt(Files.createTempDirectory("archive-limit-"))
        result <- new StreamingDownloader(new ArchiveTransport(client),dir,maxBytes=1000).fetch(ArchiveAsset("key","eso",base),policy).either
        count <- ZIO.attempt { val stream=Files.list(dir);try stream.count() finally stream.close() }
      yield assertTrue(result.left.toOption.exists(_.code=="byte_limit"),count==0) }
    },
    test("every redirect is checked before following a different origin") {
      ZIO.foreach(List(false,true)) { untrusted=>ZIO.scoped {
        val followed=new java.util.concurrent.atomic.AtomicInteger(0)
        for
          client <- ZIO.service[Client]
          server <- ZIO.acquireRelease(ZIO.attempt {
            val s=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
            s.createContext("/",e=> {
              if e.getRequestURI.getPath=="/redirect" then
                e.getResponseHeaders.add("Location",if untrusted then s"http://localhost:${s.getAddress.getPort}/final?grant=temporary-secret" else "/final")
                e.sendResponseHeaders(302,-1)
              else
                followed.incrementAndGet();e.sendResponseHeaders(200,fits.length);e.getResponseBody.write(fits)
              e.close()
            });s.start();s
          })(s=>ZIO.succeed(s.stop(0)))
          base=s"http://127.0.0.1:${server.getAddress.getPort}"
          dir <- ZIO.attempt(Files.createTempDirectory("archive-redirect-"))
          result <- new StreamingDownloader(new ArchiveTransport(client),dir).fetch(ArchiveAsset("key","cadc",base+"/redirect"),OriginPolicy(Set.empty,Set(base))).either
        yield if untrusted then result.left.toOption.exists(e=>e.code=="untrusted_origin" && !e.getMessage.contains("temporary-secret")) && followed.get()==0 else result.isRight && followed.get()==1
      }}.map(results=>assertTrue(results.forall(identity)))
    },
    test("startup recovery removes abandoned partial files and preserves complete artifacts") {
      for
        client <- ZIO.service[Client]
        dir <- ZIO.attempt(Files.createTempDirectory("archive-recovery-"))
        _ <- ZIO.attempt {Files.write(dir.resolve("abandoned.part"),fits);Files.write(dir.resolve("complete"),fits)}
        downloader=new StreamingDownloader(new ArchiveTransport(client),dir)
        _ <- downloader.recover
      yield assertTrue(!Files.exists(dir.resolve("abandoned.part")),Files.exists(dir.resolve("complete")))
    },
    test("307 metadata redirects preserve POST method and body") {
      ZIO.scoped {
        val observed=new java.util.concurrent.atomic.AtomicReference[(String,String)]()
        for
          client <- ZIO.service[Client]
          server <- ZIO.acquireRelease(ZIO.attempt {
            val s=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
            s.createContext("/",e=> {
              if e.getRequestURI.getPath=="/redirect" then
                e.getResponseHeaders.add("Location","/final");e.sendResponseHeaders(307,-1)
              else
                observed.set(e.getRequestMethod->new String(e.getRequestBody.readAllBytes(),UTF_8))
                e.sendResponseHeaders(200,2);e.getResponseBody.write("ok".getBytes(UTF_8))
              e.close()
            });s.start();s
          })(s=>ZIO.succeed(s.stop(0)))
          base=s"http://127.0.0.1:${server.getAddress.getPort}"
          _ <- new ArchiveTransport(client).metadata(base+"/redirect",OriginPolicy(Set.empty,Set(base)),"POST","ADQL=select","application/x-www-form-urlencoded")
        yield assertTrue(observed.get()==("POST"->"ADQL=select"))
      }
    },
    test("interrupted response stream removes its partial cache entry") {
      ZIO.scoped {
        for
          client <- ZIO.service[Client]
          dir <- ZIO.attempt(Files.createTempDirectory("archive-interrupt-"))
          server <- ZIO.acquireRelease(ZIO.attempt {
            val s=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
            s.createContext("/",e=> { e.sendResponseHeaders(200,0);e.getResponseBody.write(fits);e.getResponseBody.flush();Thread.sleep(1500);e.close() });s.start();s
          })(s=>ZIO.succeed(s.stop(0)))
          base=s"http://127.0.0.1:${server.getAddress.getPort}"
          fiber <- new StreamingDownloader(new ArchiveTransport(client),dir).fetch(ArchiveAsset("interrupted","eso",base),OriginPolicy(Set.empty,Set(base))).fork
          _ <- ZIO.sleep(100.millis)
          _ <- fiber.interrupt
          files <- ZIO.attempt {val s=Files.list(dir);try s.count() finally s.close()}
        yield assertTrue(files==0)
      }
    },
    test("invalid gzip is a permanent format error") {
      server(Array[Byte](0x1f,0x8b.toByte,1,2,3)) { (base,policy)=>for
        client <- ZIO.service[Client]
        dir <- ZIO.attempt(Files.createTempDirectory("archive-gzip-"))
        result <- new StreamingDownloader(new ArchiveTransport(client),dir).fetch(ArchiveAsset("key","eso",base),policy).either
      yield assertTrue(result.left.toOption.exists(e=>e.code=="invalid_fits" && !e.retryable),!Files.exists(dir.resolve("key"))) }
    },
    test("invalid FITS and NoContent never create cached assets") {
      ZIO.foreach(List(("bad".getBytes,200),(fits,204))) { (bytes,status)=>server(bytes,status) { (base,policy)=>for
        client <- ZIO.service[Client]
        dir <- ZIO.attempt(Files.createTempDirectory("archive-invalid-"))
        result <- new StreamingDownloader(new ArchiveTransport(client),dir).fetch(ArchiveAsset("key","eso",base),policy).either
      yield result.isLeft && !Files.exists(dir.resolve("key")) } }.map(xs=>assertTrue(xs.forall(identity)))
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock
