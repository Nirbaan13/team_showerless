package spaceapps.archive.providers
import spaceapps.archive.*
import spaceapps.archive.protocol.*
import zio.*
import zio.json.ast.Json
final class ArtXcProvider(transport: ArchiveTransport) extends ArchiveProvider:
  val id="iki-artxc"
  def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.coverage),TimeFilterMode.provisional,restrictions=List("Indexed days only; effective_exposure=false","FITS TIMESYS unverified; provisional kinematic modes","fits-zip route returned 404; no image delivery","Radius at most 5 degrees")))
  def search(q: ArchiveQuery,cursor: Option[ProviderCursor]): IO[ArchiveFailure,ProviderPage] =
    if q.hasTime then ZIO.fail(ArchiveFailure("unsupported_filter","ART-XC provisional clock cannot evaluate exact UTC filtering"))
    else if q.region.radius_degrees>5 then ZIO.fail(ArchiveFailure("invalid_query","ART-XC supports radius at most 5 degrees"))
    else transport.metadata(ArchiveTransport.params("https://heaiki.ru/04/api/observations",List("ra"->q.region.ra_degrees.toString,"dec"->q.region.dec_degrees.toString,"radius"->q.region.radius_degrees.toString)),OriginPolicy.artxc).flatMap(b=>ZIO.attempt(ArtXcProvider.decode(b,q)).mapError(ArchiveFailure.from))
  def resolve(r: ArchiveRecord,d: DeliveryRequest)=ZIO.fail(ArchiveFailure("unsupported_delivery","ART-XC coverage is not a science image; fits-zip route is unavailable"))
object ArtXcProvider:
  def decode(bytes: Array[Byte],q: ArchiveQuery): ProviderPage =
    import JsonMetadata.*
    val root=fields(parse(bytes))
    val days=list(root.getOrElse("days",throw ArchiveFailure("invalid_response","Missing ART-XC days")))
    val coverage=root.get("coverage").map(text).getOrElse("unknown")
    val nativeRoot=root.filterNot((k,_)=>k=="days").map((k,v)=>k->text(v))
    val records=days.flatMap { day=>
      val d=fields(day)
      val observations=d.get("observations").map(list).getOrElse(List(day))
      observations.map { observation=>
        val n=native(observation)
        val stable=List(n.getOrElse("day",d.get("day").map(text).getOrElse("")),n.getOrElse("module",""),n.getOrElse("start_s",""),n.getOrElse("stop_s","")).mkString(":")
        ArchiveRecord.create("iki-artxc","ART-XC indexed observations",stable,ProductKind.coverage,native=n).copy(
          mission=Some("Spektr-RG"),instrument=Some("ART-XC"),time=ObservationTime(quality=TimeQuality.provisional,native=n),
          provenance=nativeRoot++Map("archive"->"IKI","coverage"->coverage,"effective_exposure"->"false","time_calibration"->"provisional; FITS TIMESYS unverified"))
      }
    }
    ProviderPage(records.take(q.limit_per_provider),Completeness.indexed_subset,warnings=List("Indexed days only; not effective exposure",if records.size>q.limit_per_provider then "Result budget truncated indexed intervals" else "Provisional native time and observation modes"))
