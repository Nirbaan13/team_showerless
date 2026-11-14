package spaceapps.archive.providers
import spaceapps.archive.*
import spaceapps.archive.protocol.*
import spaceapps.domain.Query
import spaceapps.service.Archive
import zio.*
import zio.json.*
import zio.json.ast.Json
final class IrsaProvider(source: Archive,repository: ArchiveRepository) extends ArchiveProvider:
  val id="irsa-spherex"
  def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image),TimeFilterMode.exact_utc,original=true,restrictions=List("Uses existing native SPHEREx SIA2 search; new API stores native products")))
  def search(q: ArchiveQuery,cursor: Option[ProviderCursor]): IO[ArchiveFailure,ProviderPage] =
    val c=q.region
    val legacy=Query(Json.Obj(),s"CIRCLE ${c.ra_degrees} ${c.dec_degrees} ${c.radius_degrees}",after=q.time_start_utc,before=q.time_end_utc)
    source.search(legacy).mapError {
      case e: spaceapps.domain.ApiError=>ArchiveFailure(e.code,e.message,e.retryable)
      case e=>ArchiveFailure.from(e)
    }.flatMap { images=>repository.rememberIrsa(images).as {
      val records=images.take(q.limit_per_provider).map { image=>
        val o=image.observation
        val native=o.header_metadata.collect {case (k,Json.Str(v)) if !k.contains("url")=>k->v}++Map("frame_id"->o.frame_id,"release"->o.release,"detector_array"->o.detector_array.toString)
        ArchiveRecord.create(id,"spherex_"+o.release.toLowerCase,o.frame_id,ProductKind.image,Some(o.release),native).copy(mission=Some("SPHEREx"),instrument=Some("SPHEREx"),time=ObservationTime(Some(o.observation_date),quality=TimeQuality.verified),wavelength_min_m=o.wavelength_min_um.map(_*1e-6),wavelength_max_m=o.wavelength_max_um.map(_*1e-6),original=true,provenance=Map("archive"->"NASA IRSA","bridge"->"existing SIA2 native release/frame/detector contract"))
      }
      ProviderPage(records,if images.size>=q.limit_per_provider then Completeness.truncated else Completeness.unknown,warnings=List("Legacy SIA limits remain authoritative"))
    }}
  def resolve(r: ArchiveRecord,d: DeliveryRequest): IO[ArchiveFailure,List[ArchiveAsset]] =
    if d.mode==DeliveryMode.require_cutout then ZIO.fail(ArchiveFailure("unsupported_cutout","IRSA bridge exposes native originals; subset processing uses the existing SPHEREx API"))
    else repository.irsaImage(r.native_id).map(image=>List(ArchiveAsset(AssetCache.key(r,d),id,image.accessUrl)))
