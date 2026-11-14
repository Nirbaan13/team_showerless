package spaceapps.archive.providers
import spaceapps.archive.*
import spaceapps.archive.protocol.*
import zio.*
final class GaiaProvider(transport: ArchiveTransport) extends ArchiveProvider:
  val id="esa-gaia"
  def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.catalog_source),restrictions=List("DR3 source reference epoch is not an exposure date")))
  def search(q: ArchiveQuery,cursor: Option[ProviderCursor]): IO[ArchiveFailure,ProviderPage] =
    if q.hasTime then ZIO.fail(ArchiveFailure("unsupported_filter","Gaia catalogue reference epochs cannot filter observation UTC intervals"))
    else
      val c=q.region
      val adql=s"SELECT source_id,ra,dec,pmra,pmdec,ref_epoch FROM gaiadr3.gaia_source WHERE CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',${c.ra_degrees},${c.dec_degrees},${c.radius_degrees}))=1"
      new TapClient(transport).query("https://gea.esac.esa.int/tap-server/tap/sync",OriginPolicy.gaia,adql,q.limit_per_provider).map(t=>ProviderPage(t.rows.map(GaiaProvider.record),if t.rows.size>=q.limit_per_provider then Completeness.truncated else t.completeness))
  def resolve(r: ArchiveRecord,d: DeliveryRequest)=ZIO.fail(ArchiveFailure("unsupported_delivery","Catalogue sources have no science image asset"))
object GaiaProvider:
  def record(row: Map[String,String]): ArchiveRecord =
    val id=row.getOrElse("source_id",throw ArchiveFailure("invalid_response","Missing Gaia source ID"))
    ArchiveRecord.create("esa-gaia","gaiadr3.gaia_source",id,ProductKind.catalog_source,native=row).copy(
      mission=Some("Gaia"),time=ObservationTime(quality=TimeQuality.reference_epoch,reference_epoch=row.get("ref_epoch")),provenance=Map("archive"->"ESA Gaia","release"->"DR3"))
