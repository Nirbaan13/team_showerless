package spaceapps.downloads

import spaceapps.downloads.integrations.protocol.ArchiveTransport
import spaceapps.downloads.integrations.providers.UnwiseProvider
import spaceapps.downloads.model.*
import zio.*
import zio.http.Client
import zio.test.*

/** Bounded live atlas/header qualification; never transfers image arrays or claims preparation. */
object UnwiseLiveSpec extends ZIOSpecDefault:
  private val enabled=java.lang.System.getenv("UNWISE_LIVE_METADATA")=="1"
  private def tests=suite("optional live unWISE metadata")(
    test("author atlas and bounded W2 headers preserve actual 2010 and April 2024 intervals") {
      for
        client <- ZIO.service[Client]
        provider=new UnwiseProvider(new ArchiveTransport(client))
        page <- provider.search(ArchiveQuery(Circle(134.237284,-7.572222,0.001),List("unwise-neo11")),None)
        e22=page.records.find(_.native_id=="1342m076:w2:e022")
        _ <- ZIO.logInfo(s"unWISE live metadata: ${page.records.size} records; ${page.completeness}; actual intervals ${page.records.map(r=>r.native_id+"="+r.time.start_utc.getOrElse("unknown")).mkString(",")}")
      yield assertTrue(page.records.exists(_.time.start_utc.exists(_.startsWith("2010-"))),
        e22.exists(r=>r.analysisEligible && r.time.start_utc.exists(_.startsWith("2024-04-14")) && r.native("MJDMAX")=="60419.93771457"),
        !page.records.exists(_.native_id.endsWith("e023")),page.completeness==Completeness.indexed_subset)
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock @@ TestAspect.timeout(180.seconds)
  def spec=if enabled then tests else tests @@ TestAspect.ignore
