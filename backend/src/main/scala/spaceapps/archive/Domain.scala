package spaceapps.archive

import zio.json.*
import java.time.Instant
import spaceapps.domain.Hash

final case class ArchiveFailure(code: String, message: String, retryable: Boolean = false, retry_after_seconds: Option[Long] = None) extends Exception(message) derives JsonCodec
object ArchiveFailure:
  def from(t: Throwable): ArchiveFailure = t match
    case e: ArchiveFailure => e
    case e: spaceapps.domain.ApiError => ArchiveFailure(e.code,e.message,e.retryable)
    case _ => ArchiveFailure("transport_error","Archive request could not complete",true)
enum ProductKind derives JsonCodec:
  case image, cube, spectrum, catalog_source, coverage
enum Completeness derives JsonCodec:
  case complete, truncated, unknown, indexed_subset
enum TimeQuality derives JsonCodec:
  case verified, native, provisional, reference_epoch, unknown
enum TimeFilterMode derives JsonCodec:
  case exact_utc, native, client, provisional, unsupported
enum DeliveryMode derives JsonCodec:
  case prefer_cutout, require_cutout, original
final case class Circle(ra_degrees: Double, dec_degrees: Double, radius_degrees: Double, `type`: String = "circle") derives JsonCodec
final case class ArchiveQuery(region: Circle, providers: List[String], product_kinds: List[ProductKind] = List(ProductKind.image), time_start_utc: Option[String] = None, time_end_utc: Option[String] = None, limit_per_provider: Int = 100) derives JsonCodec:
  def hasTime: Boolean = time_start_utc.nonEmpty || time_end_utc.nonEmpty
  def validate: Either[ArchiveFailure, ArchiveQuery] = scala.util.Try {
    val c=region
    require(c.`type`=="circle" && List(c.ra_degrees,c.dec_degrees,c.radius_degrees).forall(_.isFinite),"Expected finite ICRS circle coordinates")
    require(c.ra_degrees>=0 && c.ra_degrees<360 && c.dec_degrees>= -90 && c.dec_degrees<=90 && c.radius_degrees>0 && c.radius_degrees<=180,"Circle outside supported coordinate range")
    require(providers.nonEmpty && providers.distinct.size==providers.size && product_kinds.nonEmpty,"Select unique providers and at least one product kind")
    require(limit_per_provider>=1 && limit_per_provider<=1000,"Result limit must be 1 to 1000 per provider")
    val lo=time_start_utc.map(Instant.parse); val hi=time_end_utc.map(Instant.parse)
    require(!lo.exists(a=>hi.exists(b=> !a.isBefore(b))),"UTC start must precede end")
    this
  }.toEither.left.map(_=>ArchiveFailure("invalid_query","Invalid circle, UTC interval, providers or record budget"))
final case class ObservationTime(start_utc: Option[String] = None, end_utc: Option[String] = None, quality: TimeQuality = TimeQuality.unknown, native: Map[String,String] = Map.empty, reference_epoch: Option[String] = None) derives JsonCodec
final case class ProviderCapabilities(product_kinds: List[ProductKind], time_filter: TimeFilterMode = TimeFilterMode.unsupported, original: Boolean = false, cutout: Boolean = false, availability: String = "available", restrictions: List[String] = Nil, geometry: String = "ICRS circle degrees") derives JsonCodec
final case class ProviderInventory(id: String, capabilities: ProviderCapabilities) derives JsonCodec
final case class ArchiveRecord(id: String, provider: String, collection: String, native_id: String, product_kind: ProductKind, version: Option[String] = None, mission: Option[String] = None, instrument: Option[String] = None, sky_coverage: Option[String] = None, time: ObservationTime = ObservationTime(), wavelength_min_m: Option[Double] = None, wavelength_max_m: Option[Double] = None, brightness_unit: Option[String] = None, native: Map[String,String] = Map.empty, provenance: Map[String,String] = Map.empty, original: Boolean = false, cutout: Boolean = false, analysisEligible: Boolean = false) derives JsonCodec
object ArchiveRecord:
  def create(provider: String, collection: String, native_id: String, product_kind: ProductKind, version: Option[String] = None, native: Map[String,String] = Map.empty): ArchiveRecord =
    ArchiveRecord(Hash.sha256(List(provider,collection,native_id,product_kind.toString,version.getOrElse("")).mkString("|")),provider,collection,native_id,product_kind,version,native=native)
final case class ProviderCursor(value: String) derives JsonCodec
final case class ProviderPage(records: List[ArchiveRecord], completeness: Completeness, continuation: Option[ProviderCursor] = None, warnings: List[String] = Nil) derives JsonCodec
final case class ProviderOutcome(provider: String, status: String, record_count: Int, completeness: Completeness, warnings: List[String] = Nil, error: Option[ArchiveFailure] = None, has_continuation: Boolean = false) derives JsonCodec
final case class DeliveryRequest(mode: DeliveryMode = DeliveryMode.prefer_cutout, region: Option[Circle] = None) derives JsonCodec
/** URLs are ephemeral and intentionally never serialized to public or persistent metadata. */
final case class ArchiveAsset(id: String, provider: String, url: String, semantic: String = "#this", format: String = "application/fits", estimated_bytes: Option[Long] = None, requires_auth: Boolean = false)
final case class StoredAsset(id: String, bytes: Long, sha256: String, compression: String, brightness_unit: Option[String] = None, analysisEligible: Boolean = false, artifact_url: String = "") derives JsonCodec
final case class SearchSnapshot(id: String, query: ArchiveQuery, status: String = "queued", records: List[ArchiveRecord] = Nil, outcomes: List[ProviderOutcome] = Nil, continuations: Map[String,ProviderCursor] = Map.empty, generation: Long = 0, status_url: String = "", pending_provider: Option[String] = None) derives JsonCodec
final case class SearchPage(id: String, status: String, outcomes: List[ProviderOutcome], records: List[ArchiveRecord], returned_count: Int, next_cursor: Option[String]) derives JsonCodec
final case class DownloadSelection(record_ids: List[String], delivery: DeliveryRequest = DeliveryRequest()) derives JsonCodec
final case class AssetOutcome(record_id: String, status: String, asset: Option[StoredAsset] = None, error: Option[ArchiveFailure] = None, provenance: Map[String,String] = Map.empty) derives JsonCodec
final case class DownloadSnapshot(id: String, selection: DownloadSelection, status: String = "queued", assets: List[AssetOutcome] = Nil, status_url: String = "") derives JsonCodec
final case class AcceptedJob(id: String, status_url: String) derives JsonCodec
