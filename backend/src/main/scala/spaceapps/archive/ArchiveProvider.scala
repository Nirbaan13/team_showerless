package spaceapps.archive
import zio.*
trait ArchiveProvider:
  def id: String
  def capabilities: UIO[ProviderCapabilities]
  def search(query: ArchiveQuery, cursor: Option[ProviderCursor]): IO[ArchiveFailure,ProviderPage]
  def resolve(record: ArchiveRecord, delivery: DeliveryRequest): IO[ArchiveFailure,List[ArchiveAsset]]
