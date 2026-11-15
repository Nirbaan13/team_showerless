package spaceapps.downloads.integrations.providers
import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.model.*
import spaceapps.downloads.integrations.protocol.*
import zio.*
import java.nio.charset.StandardCharsets.UTF_8
final class NadcBassProvider(transport: ArchiveTransport) extends ArchiveProvider:
  val id="nadc-bass"
  def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image),TimeFilterMode.native,restrictions=List("Footprint completeness and datetime clock unverified","Image host failed DNS in qualification; discovery remains operational")))
  def search(q: ArchiveQuery,cursor: Option[ProviderCursor]): IO[ArchiveFailure,ProviderPage] =
    if q.hasTime then ZIO.fail(ArchiveFailure("unsupported_filter","BASS native dates have no verified exact UTC clock"))
    else
      val boundary="archive-boundary"
      val body=NadcBassProvider.parameters(q).map((k,v)=>s"--$boundary\r\nContent-Disposition: form-data; name=\"$k\"\r\n\r\n$v\r\n").mkString+s"--$boundary--\r\n"
      transport.metadata("https://nadc.china-vo.org/data/data/bassdr3images/build.csvs",OriginPolicy.bass,"POST",body,s"multipart/form-data; boundary=$boundary").flatMap(b=>ZIO.attempt(NadcBassProvider.decode(b,q)).mapError(ArchiveFailure.from))
  def resolve(r: ArchiveRecord,d: DeliveryRequest)=ZIO.fail(ArchiveFailure("download_unavailable","BASS image host failed DNS during qualification; metadata is available"))
object NadcBassProvider:
  def parameters(q: ArchiveQuery): List[(String,String)] = List("pos.type"->"pos.cone","pos.cra"->q.region.ra_degrees.toString,"pos.cdec"->q.region.dec_degrees.toString,"pos.cradius"->(q.region.radius_degrees*3600d).toString,"showcol"->"single_image.fitsname","showcol"->"single_image.datetime")++q.time_start_utc.map(t=>"single_image.datetime.min"->t.take(10))++q.time_end_utc.map(t=>"single_image.datetime.max"->t.take(10))
  def decode(bytes: Array[Byte],q: ArchiveQuery): ProviderPage =
    val rows=CsvCodec.decode(bytes,Set("single_image_fitsname","single_image_datetime"))
    val records=rows.take(q.limit_per_provider).map { row=>
      val path=row("single_image_fitsname")
      if !path.startsWith("/bass/") || path.contains("..") then throw ArchiveFailure("invalid_response","Unexpected BASS file identity")
      ArchiveRecord.create("nadc-bass","BASS DR3",path,ProductKind.image,native=row).copy(
        mission=Some("BASS"),time=ObservationTime(quality=TimeQuality.native,native=Map("datetime"->row("single_image_datetime"))),
        provenance=Map("archive"->"NADC","image_host_state"->"DNS failed during qualification","spatial_semantics"->"cone metadata; image footprint unverified"))
    }
    ProviderPage(records,if rows.size>q.limit_per_provider then Completeness.truncated else Completeness.unknown,warnings=List("Native date clock and image footprint unverified"))
