package spaceapps.archive.providers
import spaceapps.archive.*
import spaceapps.archive.protocol.*
import zio.*
final class ArtXcCatalogProvider(transport: ArchiveTransport) extends ArchiveProvider:
  val id="iki-artxc-catalog"
  def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.catalog_source),restrictions=List("First-year aggregated catalogue; source positions, no observation epochs or image files")))
  def search(q: ArchiveQuery,cursor: Option[ProviderCursor]): IO[ArchiveFailure,ProviderPage] =
    if q.hasTime then ZIO.fail(ArchiveFailure("unsupported_filter","Aggregated ART-XC catalogue has no per-observation UTC filter"))
    else transport.metadata("https://www.srg.cosmos.ru/static/catalogs/artxc/artxc_1year_catalog.csv",OriginPolicy(Set("www.srg.cosmos.ru"))).flatMap(b=>ZIO.attempt(ArtXcCatalogProvider.decode(b,q)).mapError(ArchiveFailure.from))
  def resolve(r: ArchiveRecord,d: DeliveryRequest)=ZIO.fail(ArchiveFailure("unsupported_delivery","Aggregated catalogue entries are not image products"))
object ArtXcCatalogProvider:
  def distance(ra: Double,dec: Double,c: Circle): Double =
    val a=math.toRadians(ra-c.ra_degrees);val d=math.toRadians(dec);val center=math.toRadians(c.dec_degrees)
    math.toDegrees(math.acos(math.max(-1d,math.min(1d,math.sin(d)*math.sin(center)+math.cos(d)*math.cos(center)*math.cos(a)))))
  def decode(bytes: Array[Byte],q: ArchiveQuery): ProviderPage =
    val rows=CsvCodec.decode(bytes,Set("NAME","RAJ2000","DEJ2000"))
    val selected=rows.filter { row=>
      def n(k: String)=row(k).toDoubleOption.filter(_.isFinite).getOrElse(throw ArchiveFailure("invalid_response","Invalid ART-XC catalogue position"))
      distance(n("RAJ2000"),n("DEJ2000"),q.region)<=q.region.radius_degrees
    }
    ProviderPage(selected.take(q.limit_per_provider).map { r=>
      ArchiveRecord.create("iki-artxc-catalog","ART-XC first-year catalogue",r("NAME"),ProductKind.catalog_source,Some("first-year"),r).copy(mission=Some("Spektr-RG"),instrument=Some("ART-XC"),provenance=Map("archive"->"SRG","scope"->"first-year survey aggregated source catalogue"))
    },if selected.size>q.limit_per_provider then Completeness.truncated else Completeness.complete)
