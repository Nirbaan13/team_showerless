package spaceapps.archive
import spaceapps.archive.protocol.*
import spaceapps.archive.providers.*
import zio.*
import zio.http.Client
import zio.test.*
import java.nio.file.Files
/** Optional bounded integration smoke; disabled in ordinary/offline CI. Never prints grants or URLs. */
object ArchiveLiveSpec extends ZIOSpecDefault:
  private val enabled=java.lang.System.getenv("ARCHIVE_LIVE_SMOKE")=="1"
  private def tests=suite("optional live archive qualification")(
    test("ESO discovery and native SODA cutout") {
      for
        client <- ZIO.service[Client]
        transport=new ArchiveTransport(client)
        provider=new ObsTapProvider("eso","https://archive.eso.org/tap_obs/sync",OriginPolicy.eso,transport)
        page <- provider.search(ArchiveQuery(Circle(266.4,-29,0.002),List("eso"),limit_per_provider=3),None)
        _ <- ZIO.fail(new RuntimeException("ESO discovery returned no image")).when(page.records.isEmpty)
        record=ArchiveRecord.create("eso","VISTA","ivo://eso.org/ID?ADP.2014-11-12T16:17:07.630",ProductKind.image)
        assets <- provider.resolve(record,DeliveryRequest(DeliveryMode.require_cutout,Some(Circle(266.4,-29,0.002))))
        dir <- ZIO.attempt(Files.createTempDirectory("eso-live-"))
        stored <- new StreamingDownloader(transport,dir,maxBytes=1024*1024).fetch(assets.head,provider.origins)
        _ <- ZIO.logInfo(s"ESO live discovery: ${page.records.size} records (${page.completeness}); validated cutout ${stored.bytes} bytes; sha256=${stored.sha256}")
      yield assertTrue(stored.bytes>0,!stored.analysisEligible)
    },
    test("CADC NEOSSat discovery and native SODA cutout") {
      for
        client <- ZIO.service[Client]
        transport=new ArchiveTransport(client)
        provider=new ObsTapProvider("cadc","https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/argus/sync",OriginPolicy.cadc,transport)
        page <- provider.search(ArchiveQuery(Circle(93.207,-17.583,0.002),List("cadc"),time_start_utc=Some("2024-11-30T00:00:00Z"),time_end_utc=Some("2024-12-01T00:00:00Z"),limit_per_provider=3),None)
        _ <- ZIO.fail(new RuntimeException("CADC discovery returned no image")).when(page.records.isEmpty)
        record=ArchiveRecord.create("cadc","NEOSSAT","ivo://cadc.nrc.ca/NEOSSAT?2024335070357/cord",ProductKind.image)
        assets <- provider.resolve(record,DeliveryRequest(DeliveryMode.require_cutout,Some(Circle(93.207,-17.583,0.002))))
        dir <- ZIO.attempt(Files.createTempDirectory("cadc-live-"))
        stored <- new StreamingDownloader(transport,dir,maxBytes=1024*1024).fetch(assets.head,provider.origins)
        _ <- ZIO.logInfo(s"CADC live discovery: ${page.records.size} records (${page.completeness}); validated cutout ${stored.bytes} bytes; sha256=${stored.sha256}")
      yield assertTrue(stored.bytes>0,!stored.analysisEligible)
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock @@ TestAspect.sequential
  def spec=if enabled then tests else tests @@ TestAspect.ignore
