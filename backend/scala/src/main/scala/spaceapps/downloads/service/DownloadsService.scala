package spaceapps.downloads.service

import spaceapps.downloads.model.*
import spaceapps.downloads.repository.DownloadsRepository
import zio.*
import java.nio.file.Path

/** Application entry point for archive controllers; storage stays behind services. */
final class DownloadsService(registry: ProviderRegistry,repository: DownloadsRepository,
  discovery: FederatedDiscovery,downloads: DownloadJobs):
  def inventory: UIO[List[ProviderInventory]] = registry.inventory
  def search(query: ArchiveQuery): IO[ArchiveFailure,AcceptedJob] = discovery.accept(query)
  def page(id: String,cursor: Option[String],limit: Int): IO[ArchiveFailure,SearchPage] = repository.page(id,cursor,limit)
  def continue(id: String,provider: String): IO[ArchiveFailure,AcceptedJob] = discovery.continue(id,provider)
  def download(selection: DownloadSelection): IO[ArchiveFailure,AcceptedJob] = downloads.accept(selection)
  def downloadStatus(id: String): IO[ArchiveFailure,DownloadSnapshot] = downloads.status(id)
  def events(id:String,after:Option[Long])=downloads.status(id) *> new DownloadEvents(repository).watch(id,after)
  def resource(id:String)=downloads.resource(id)
  def artifact(id: String): IO[ArchiveFailure,(Path,StoredAsset)] = downloads.artifact(id)
