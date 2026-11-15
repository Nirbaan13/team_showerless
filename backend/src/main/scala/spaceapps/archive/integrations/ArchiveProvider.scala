package spaceapps.archive.integrations
import spaceapps.archive.domain.*
import zio.*
trait ArchiveProvider:
  def origins: spaceapps.archive.integrations.protocol.OriginPolicy = spaceapps.archive.integrations.protocol.OriginPolicy.forProvider(id)
  def id: String
  def capabilities: UIO[ProviderCapabilities]
  def search(query: ArchiveQuery, cursor: Option[ProviderCursor]): IO[ArchiveFailure,ProviderPage]
  def resolve(record: ArchiveRecord, delivery: DeliveryRequest): IO[ArchiveFailure,List[ArchiveAsset]]
