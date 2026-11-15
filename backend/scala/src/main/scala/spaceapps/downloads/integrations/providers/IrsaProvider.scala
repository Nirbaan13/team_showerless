package spaceapps.downloads.integrations.providers
import spaceapps.downloads.repository.DownloadsRepository
import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.model.*
import spaceapps.downloads.integrations.protocol.*
import spaceapps.irsa.model.Query

import spaceapps.irsa.service.Archive
import zio.*
import zio.json.*
import zio.json.ast.Json
final class IrsaProvider(source: Archive,repository: DownloadsRepository) extends ArchiveProvider:
  val id="irsa-spherex"
  def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image),TimeFilterMode.exact_utc,original=true,cutout=true,restrictions=List("Uses SIA2 or the public S3 mirror index; native IBE spatial selection has no reprojection")))
  def search(q: ArchiveQuery,cursor: Option[ProviderCursor]): IO[ArchiveFailure,ProviderPage] =
    val c=q.region
    val legacy=Query(Json.Obj(),s"CIRCLE ${c.ra_degrees} ${c.dec_degrees} ${c.radius_degrees}",after=q.time_start_utc,before=q.time_end_utc)
    source.search(legacy).mapError {
      case e: spaceapps.infra.model.ApiError=>ArchiveFailure(e.code,e.message,e.retryable)
      case e=>ArchiveFailure.from(e)
    }.flatMap { images=>repository.rememberIrsa(images).as {
      val records=images.take(q.limit_per_provider).map { image=>
        val o=image.observation
        val native=o.header_metadata.collect {case (k,Json.Str(v)) if !k.contains("url")=>k->v}++Map("frame_id"->o.frame_id,"release"->o.release,"detector_array"->o.detector_array.toString)
        ArchiveRecord.create(id,"spherex_"+o.release.toLowerCase,o.frame_id,ProductKind.image,Some(o.release),native).copy(mission=Some("SPHEREx"),instrument=Some("SPHEREx"),time=ObservationTime(Some(o.observation_date),quality=TimeQuality.verified),wavelength_min_m=o.wavelength_min_um.map(_*1e-6),wavelength_max_m=o.wavelength_max_um.map(_*1e-6),original=true,cutout=true,provenance=Map("archive"->"NASA IRSA","bridge"->o.header_metadata.get("discovery_source").collect{case Json.Str(v)=>v}.getOrElse("irsa_sia")))
      }
      val incomplete=images.exists(_.observation.header_metadata.get("discovery_complete").contains(Json.Str("false")))
      val warnings=if incomplete then List("Partial real S3 mirror index: additional observations may become available as indexing progresses") else List("Native archive limits remain authoritative")
      ProviderPage(records,if images.size>=q.limit_per_provider then Completeness.truncated else Completeness.unknown,warnings=warnings)
    }}
  def resolve(r: ArchiveRecord,d: DeliveryRequest): IO[ArchiveFailure,List[ArchiveAsset]] =
    repository.irsaImage(r.native_id).flatMap { image=>
      val selected=if d.mode==DeliveryMode.original then ZIO.succeed(image)
        else d.region match
          case Some(c)=>source.select(image,Query(Json.Obj(),s"CIRCLE ${c.ra_degrees} ${c.dec_degrees} ${c.radius_degrees}"))
          case None if d.mode==DeliveryMode.require_cutout=>ZIO.fail(ArchiveFailure("invalid_selection","require_cutout needs a spatial region"))
          case None=>ZIO.succeed(image)
      selected.map(result=>List(ArchiveAsset(ArchiveAssetKey.key(r,d),id,result.accessUrl))).mapError(ArchiveFailure.from)
    }
