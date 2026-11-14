package spaceapps

import spaceapps.domain.*
import spaceapps.integrations.irsa.LiveArchive
import spaceapps.integrations.fits.FitsHeaders
import zio.*
import zio.http.Client
import zio.json.*
import zio.json.ast.Json
import zio.test.*
import java.nio.file.Files

/** Optional known-product transport check; availability of SIA search is tested separately. */
object IrsaCutoutsLiveSpec extends ZIOSpecDefault:
  private val tests=suite("live IRSA cutouts")(
    test("known QR3 product returns a small valid MEF with every mission extension") {
      ZIO.scoped { for
        client <- ZIO.service[Client]
        path <- ZIO.acquireRelease(ZIO.attempt(Files.createTempFile("irsa-live-cutout-",".fits")))(p=>ZIO.attempt(Files.deleteIfExists(p)).orDie)
        parent="https://irsa.ipac.caltech.edu/ibe/data/spherex/qr3/level2/2026W21_2A/l2b-v27-2026-268/1/level2_2026W21_2A_0001_2D1_spx_l2b-v27-2026-268.fits"
        image=ArchiveImage(Observation("known-product-transport-probe","2026-05-21T12:08:41.580Z",1,"QR3"),parent)
        query=Query.fromParameters("default",Map("right_ascension_deg"->"337.8783221","declination_deg"->"-5.1891588","width_arcmin"->"5","height_arcmin"->"5")).toOption.get
        archive=LiveArchive(client,maxBytes=8L*1024*1024)
        selected <- archive.select(image,query)
        _ <- archive.fetch(selected,path)
        headers <- FitsHeaders.read(path)
        bytes <- ZIO.attempt(Files.size(path))
        hdus=headers.asObject.flatMap(_.get("hdus")).flatMap(_.asArray).getOrElse(zio.Chunk.empty)
        names=hdus.flatMap(_.asObject.flatMap(_.get("name")).flatMap(_.asString)).toList
        _ <- ZIO.logInfo(s"Verified IRSA adapter cutout: $bytes bytes; HDUs=${names.mkString(",")}; request=${selected.accessUrl}")
      yield assertTrue(bytes>2880,bytes<8L*1024*1024,hdus.size==7,names==List("IMAGE","FLAGS","VARIANCE","ZODI","EPSF","WCS-WAVE"),selected.sourceUrl.contains(parent)) }
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock @@ TestAspect.timeout(60.seconds)
  def spec=if sys.env.get("IRSA_CUTOUT_LIVE").contains("1") then tests else tests @@ TestAspect.ignore
