package spaceapps.downloads.integrations.providers
import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.model.*
import spaceapps.downloads.integrations.protocol.*
import zio.*
final class LamostProvider(transport: ArchiveTransport) extends ArchiveProvider:
  val id="lamost"
  private val base="https://www.lamost.org/openapi/dr11/v2.0/lrs"
  def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.spectrum),TimeFilterMode.native,original=true,restrictions=List("Public DR11 v2.0 LRS spectra; full file validation occurs at transfer","Native dates have no verified exact UTC interval; no image products")))
  private def publicRelease: IO[ArchiveFailure,Unit] = transport.metadata("https://www.lamost.org/openapi/dr_versions",OriginPolicy.lamost).flatMap { b=>
    ZIO.attempt(LamostProvider.isPublic(b,"dr11","v2.0")).mapError(ArchiveFailure.from).flatMap(ok=>if ok then ZIO.unit else ZIO.fail(ArchiveFailure("requires_auth","LAMOST release is not public in current release-status API")))
  }
  def search(q: ArchiveQuery,cursor: Option[ProviderCursor]): IO[ArchiveFailure,ProviderPage] =
    if q.hasTime then ZIO.fail(ArchiveFailure("unsupported_filter","LAMOST native date is not a verified exact UTC interval"))
    else publicRelease *> transport.metadata(ArchiveTransport.params(base+"/voservice/conesearch",List("ra"->q.region.ra_degrees.toString,"dec"->q.region.dec_degrees.toString,"sr"->q.region.radius_degrees.toString,"output.fmt"->"json")),OriginPolicy.lamost).flatMap(b=>ZIO.attempt(LamostProvider.decode(b,q)).mapError(ArchiveFailure.from))
  def resolve(r: ArchiveRecord,d: DeliveryRequest): IO[ArchiveFailure,List[ArchiveAsset]] =
    if d.mode==DeliveryMode.require_cutout then ZIO.fail(ArchiveFailure("unsupported_cutout","A spectrum is not a spatial image cutout"))
    else publicRelease.as(List(ArchiveAsset(ArchiveAssetKey.key(r,d),id,ArchiveTransport.params(base+"/spectrum/fits",List("obsid"->r.native_id)))))
object LamostProvider:
  def isPublic(bytes: Array[Byte],release: String,version: String): Boolean =
    import JsonMetadata.*
    val root=fields(parse(bytes))
    list(root.getOrElse("versions",throw ArchiveFailure("invalid_response","Missing release status"))).exists { v=>
      val n=native(v);n.get("dr_version").contains(release) && n.get("sub_version").contains(version) && n.get("public_status").contains("public")
    }
  def decode(bytes: Array[Byte],q: ArchiveQuery): ProviderPage =
    import JsonMetadata.*
    val rows=list(parse(bytes))
    val records=rows.take(q.limit_per_provider).map { row=>
      val n=native(row)
      val obsid=n.getOrElse("obsid",throw ArchiveFailure("invalid_response","Missing LAMOST observation ID"))
      if !obsid.matches("[0-9]+") then throw ArchiveFailure("invalid_response","Invalid LAMOST observation ID")
      ArchiveRecord.create("lamost","DR11 v2.0 LRS",obsid,ProductKind.spectrum,Some("DR11-v2.0"),n).copy(mission=Some("LAMOST"),instrument=Some("LRS"),time=ObservationTime(quality=TimeQuality.native,native=n.filter((k,_)=>Set("mjd","lmjd","obsdate")(k))),original=true,provenance=Map("archive"->"LAMOST OpenAPI","public_release"->"DR11 v2.0","compression"->"gzip observed; validated at transfer"))
    }
    ProviderPage(records,if rows.size>q.limit_per_provider then Completeness.truncated else Completeness.unknown,warnings=List("Cone result exhaustion is not independently proven"))
