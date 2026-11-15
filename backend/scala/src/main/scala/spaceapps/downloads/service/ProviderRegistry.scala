package spaceapps.downloads.service
import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.model.*
import zio.*
final class ProviderRegistry(val providers: List[ArchiveProvider]):
  require(providers.map(_.id).distinct.size==providers.size)
  def get(id: String): IO[ArchiveFailure,ArchiveProvider] = ZIO.fromOption(providers.find(_.id==id)).orElseFail(ArchiveFailure("unknown_provider","Unknown archive provider"))
  def inventory: UIO[List[ProviderInventory]] = ZIO.foreach(providers)(p=>p.capabilities.map(ProviderInventory(p.id,_)))
