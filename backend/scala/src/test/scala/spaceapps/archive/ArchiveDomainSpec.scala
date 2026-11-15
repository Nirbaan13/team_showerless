package spaceapps.archive
import spaceapps.domain.*
import spaceapps.archive.domain.*
import spaceapps.service.*
import spaceapps.archive.service.*
import spaceapps.archive.repository.ArchiveRepository
import spaceapps.archive.bootstrap.ArchiveRuntime
import spaceapps.archive.integrations.ArchiveProvider
import zio.test.*
import zio.json.*
object ArchiveDomainSpec extends ZIOSpecDefault:
  def spec = suite("archive domain")(
    test("validates finite degree coordinates and preserves radius") {
      val q=ArchiveQuery(Circle(210.8,54.35,0.1),List("eso"))
      assertTrue(q.validate.isRight,q.region.radius_degrees==0.1,
        q.copy(region=Circle(360,0,1)).validate.isLeft,
        q.copy(region=Circle(0,91,1)).validate.isLeft,
        q.copy(region=Circle(0,0,0)).validate.isLeft,
        q.copy(region=Circle(0,0,Double.NaN)).validate.isLeft,
        q.copy(time_start_utc=Some("2026-02-01T00:00:00Z"),time_end_utc=Some("2026-01-01T00:00:00Z")).validate.isLeft)
    },
    test("native time, string source IDs and unknown values survive JSON") {
      val r=ArchiveRecord.create("esa-gaia","DR3","1609227557512575232",ProductKind.catalog_source,
        native=Map("ref_epoch"->"2016.0"))
      assertTrue(r.toJson.fromJson[ArchiveRecord]==Right(r),r.brightness_unit.isEmpty,
        r.native.get("pmra").isEmpty,r.native_id=="1609227557512575232",
        r.copy(time=ObservationTime(quality=TimeQuality.provisional,native=Map("start_s"->"628642660.696336","mjdref"->"51543.875"))).toJson.fromJson[ArchiveRecord].isRight)
    },
    test("asset identity separates version, epoch and subset, ignoring retrieval grants") {
      val a=ArchiveRecord.create("eso","VISTA","id",ProductKind.image,version=Some("v1"))
      assertTrue(ArchiveAssetKey.key(a,DeliveryRequest())==ArchiveAssetKey.key(a,DeliveryRequest()),
        ArchiveAssetKey.key(a,DeliveryRequest())!=ArchiveAssetKey.key(a.copy(version=Some("v2")),DeliveryRequest()),
        ArchiveAssetKey.key(a,DeliveryRequest())!=ArchiveAssetKey.key(a.copy(time=ObservationTime(start_utc=Some("2020-01-01T00:00:00Z"))),DeliveryRequest()))
    }
  )
