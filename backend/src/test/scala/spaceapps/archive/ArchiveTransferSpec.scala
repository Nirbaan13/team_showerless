package spaceapps.archive
import spaceapps.archive.protocol.*
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
    test("invalid FITS and NoContent never create cached assets") {
      ZIO.foreach(List(("bad".getBytes,200),(fits,204))) { (bytes,status)=>server(bytes,status) { (base,policy)=>for
        client <- ZIO.service[Client]
        dir <- ZIO.attempt(Files.createTempDirectory("archive-invalid-"))
        result <- new StreamingDownloader(new ArchiveTransport(client),dir).fetch(ArchiveAsset("key","eso",base),policy).either
      yield result.isLeft && !Files.exists(dir.resolve("key")) } }.map(xs=>assertTrue(xs.forall(identity)))
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock
