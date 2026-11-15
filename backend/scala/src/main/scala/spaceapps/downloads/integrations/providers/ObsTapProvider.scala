package spaceapps.downloads.integrations.providers
import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.model.*
import spaceapps.downloads.integrations.protocol.*
import zio.*
import java.time.Instant
import java.net.{URI,URLDecoder}
import java.nio.charset.StandardCharsets.UTF_8

final class ObsTapProvider(val id: String,endpoint: String,policy: OriginPolicy,transport: ArchiveTransport) extends ArchiveProvider:
  override def origins=policy
  def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image,ProductKind.cube,ProductKind.spectrum),TimeFilterMode.exact_utc,original=true,cutout=true,restrictions=List("Native products only; instrument processing is unqualified")))
  def search(q: ArchiveQuery,cursor: Option[ProviderCursor]) =
    if cursor.nonEmpty then ZIO.fail(ArchiveFailure("unsupported_continuation","Provider supplies no qualified continuation"))
    else new TapClient(transport).query(endpoint,policy,TapClient.obsQuery(q),q.limit_per_provider).flatMap(t=>ZIO.attempt {
      val records=t.rows.map(ObsTapProvider.record(id,_))
      ProviderPage(records,if t.completeness==Completeness.truncated || records.size>=q.limit_per_provider then Completeness.truncated else t.completeness)
    }.mapError(ArchiveFailure.from))
  def resolve(record: ArchiveRecord,delivery: DeliveryRequest): IO[ArchiveFailure,List[ArchiveAsset]] =
    val linksUrl=if id=="eso" then ArchiveTransport.params("https://archive.eso.org/datalink/links",List("ID"->record.native_id)) else ArchiveTransport.params("https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/caom2ops/datalink",List("ID"->record.native_id))
    new DataLinkResolver(transport).resolve(linksUrl,policy).flatMap(links=>ZIO.attempt(SodaResolver.select(record,delivery,links)).mapError(ArchiveFailure.from))
object ObsTapProvider:
  def utc(mjd: Double): String =
    val seconds=(mjd-40587d)*86400d;val whole=math.floor(seconds).toLong
    Instant.ofEpochSecond(whole,math.round((seconds-whole)*1e9)).toString
  def record(provider: String,row: Map[String,String]): ArchiveRecord =
    def required(k: String)=row.getOrElse(k,throw ArchiveFailure("invalid_response",s"Missing ObsCore $k"))
    def num(k: String)=row.get(k).map(v=>v.toDoubleOption.filter(_.isFinite).getOrElse(throw ArchiveFailure("invalid_response",s"Invalid ObsCore $k")))
    val nativeId=row.get("obs_publisher_did").orElse(row.get("access_url").flatMap { u=>
      Option(URI.create(u).getRawQuery).toList.flatMap(_.split("&")).find(_.startsWith("ID=")).map(s=>URLDecoder.decode(s.drop(3),UTF_8))
    }).getOrElse(required("obs_id"))
    val kind=required("dataproduct_type") match
      case "image"=>ProductKind.image
      case "cube"=>ProductKind.cube
      case "spectrum"=>ProductKind.spectrum
      case _=>throw ArchiveFailure("invalid_response","Unexpected ObsCore product kind")
    ArchiveRecord.create(provider,required("obs_collection"),nativeId,kind,version=row.get("obs_id"),native=row.filterNot((k,_)=>k.contains("url"))).copy(
      mission=row.get("facility_name"),instrument=row.get("instrument_name"),sky_coverage=row.get("s_region"),
      time=ObservationTime(num("t_min").map(utc),num("t_max").map(utc),TimeQuality.verified,row.filter((k,_)=>Set("t_min","t_max")(k))),
      wavelength_min_m=num("em_min"),wavelength_max_m=num("em_max"),original=true,cutout=true,
      provenance=Map("archive"->provider,"metadata_standard"->"ObsCore","native_product"->"true"))
