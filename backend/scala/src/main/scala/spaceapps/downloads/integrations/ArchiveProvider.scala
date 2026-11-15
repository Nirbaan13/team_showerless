package spaceapps.downloads.integrations
import spaceapps.downloads.model.*
import zio.*
trait ArchiveProvider:
  def origins: spaceapps.downloads.integrations.protocol.OriginPolicy = spaceapps.downloads.integrations.protocol.OriginPolicy.forProvider(id)
  def id: String
  def capabilities: UIO[ProviderCapabilities]
  def search(query: ArchiveQuery, cursor: Option[ProviderCursor]): IO[ArchiveFailure,ProviderPage]
  def resolve(record: ArchiveRecord, delivery: DeliveryRequest): IO[ArchiveFailure,List[ArchiveAsset]]
