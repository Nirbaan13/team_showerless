package spaceapps.archive
import spaceapps.archive.providers.*
import spaceapps.archive.protocol.*
import zio.*
import zio.test.*
import zio.json.*
import java.nio.charset.StandardCharsets.UTF_8
object CustomProvidersSpec extends ZIOSpecDefault:
  def spec=suite("custom archive adapters")(
    test("BASS repeated multipart showcol, arcsecond radius and separate native date") {
      val q=ArchiveQuery(Circle(107.841375,34.74988889,1d/60),List("nadc-bass"))
      val parts=NadcBassProvider.parameters(q)
      val records=NadcBassProvider.decode(VoProtocolSpec.fixture("china-bass-cone.csv"),q)
      assertTrue(parts.count(_._1=="showcol")==2,parts.toMap.apply("pos.cradius").toDouble==60d,
        records.completeness==Completeness.unknown,records.records.head.native_id.contains("20150209"),
        records.records.head.time.start_utc.isEmpty,records.records.head.time.native("datetime").startsWith("2015-02-10"),
        !records.records.head.original)
    },
    test("BASS empty and application error are failures") {
      val q=ArchiveQuery(Circle(0,0,0.1),List("nadc-bass"))
      assertTrue(scala.util.Try(NadcBassProvider.decode(Array.emptyByteArray,q)).isFailure,
        scala.util.Try(NadcBassProvider.decode("{\"error\":\"bad\"}".getBytes,q)).isFailure)
    },
    test("ART-XC preserves native seconds, indexed coverage and provisional clocks") {
      val q=ArchiveQuery(Circle(325.76,6.91,0.3),List("iki-artxc"),List(ProductKind.coverage))
      val page=ArtXcProvider.decode(VoProtocolSpec.fixture("russia-artxc-observations.json"),q)
      val r=page.records.head
      assertTrue(page.completeness==Completeness.indexed_subset,r.product_kind==ProductKind.coverage,
        r.time.quality==TimeQuality.provisional,r.time.start_utc.isEmpty,r.time.native("mjdref")=="51543.875",
        r.provenance("coverage")=="indexed days only",r.provenance("effective_exposure")=="false",!r.original)
    },
    test("Gaia catalogue preserves exact string IDs and absent proper motion") {
      val rows=CsvCodec.decode(VoProtocolSpec.fixture("gaia-esa-region.csv"),Set("source_id","ra","dec","ref_epoch"))
      val records=rows.map(GaiaProvider.record)
      assertTrue(records.head.native_id=="1609227557512575232",records(1).native.get("pmra").isEmpty,
        records.head.time.reference_epoch.contains("2016.0"),records.head.product_kind==ProductKind.catalog_source)
    },
    test("LAMOST admits public release, preserves obsid and spectra only") {
      val q=ArchiveQuery(Circle(10.68,41.26,0.01),List("lamost"),List(ProductKind.spectrum))
      val releases=VoProtocolSpec.fixture("lamost-releases.json")
      val page=LamostProvider.decode(VoProtocolSpec.fixture("lamost-cone.json"),q)
      assertTrue(LamostProvider.isPublic(releases,"dr11","v2.0"),!LamostProvider.isPublic(releases,"dr14","v0"),
        page.records.head.native_id=="90206060",page.records.forall(_.product_kind==ProductKind.spectrum),
        scala.util.Try(LamostProvider.decode("{\"error\":\"bad query\"}".getBytes,q)).isFailure)
    },
    test("ART-XC catalogue uses spherical source positions and has no observation UTC") {
      val q=ArchiveQuery(Circle(0.38612688972499454,24.04494520406602,0.001),List("iki-artxc-catalog"),List(ProductKind.catalog_source))
      val page=ArtXcCatalogProvider.decode(VoProtocolSpec.fixture("artxc-catalog.csv"),q)
      assertTrue(page.records.size==1,page.records.head.native_id=="SRGA J000132.7+240242",
        page.records.head.time.start_utc.isEmpty,page.records.head.product_kind==ProductKind.catalog_source)
    },
    test("IRSA bridge preserves original circle, release, detector and frame metadata") {
      import spaceapps.domain.{ArchiveImage,Observation,Query}
      import zio.json.ast.Json
      for
        seen <- Ref.make(Option.empty[Query])
        dir <- ZIO.attempt(java.nio.file.Files.createTempDirectory("irsa-bridge-"))
        repo <- ArchiveRepository.open(dir.resolve("state.sqlite"))
        source=new spaceapps.service.Archive:
          def search(q: Query)=seen.set(Some(q)).as(List(ArchiveImage(Observation("native-frame","2026-01-01T00:00:00Z",3,"DR1",header_metadata=Map("obs_publisher_did"->Json.Str("ivo://irsa/test"))),"https://irsa.ipac.caltech.edu/native.fits")))
          def fetch(i: ArchiveImage,p: java.nio.file.Path)=ZIO.unit
        bridge=new IrsaProvider(source,repo)
        page <- bridge.search(ArchiveQuery(Circle(1,2,0.1),List("irsa-spherex")),None)
        q <- seen.get
        assets <- bridge.resolve(page.records.head,DeliveryRequest(DeliveryMode.original))
      yield assertTrue(q.exists(_.position=="CIRCLE 1.0 2.0 0.1"),page.records.head.native("detector_array")=="3",page.records.head.native("release")=="DR1",page.records.head.native_id=="native-frame",assets.head.url.endsWith("native.fits"))
    },
    test("pending inventory never claims working AST3 discovery or anonymous EP") {
      val inv=PendingProvider.inventory
      assertTrue(inv.find(_.id=="nadc-ast3").exists(_.capabilities.availability=="pending_qualification"),
        inv.find(_.id=="einstein-probe").exists(_.capabilities.availability=="requires_auth"))
    }
  )
