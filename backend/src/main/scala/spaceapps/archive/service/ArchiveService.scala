package spaceapps.archive.service

import spaceapps.archive.domain.*
import spaceapps.archive.repository.ArchiveRepository
import zio.*
import java.nio.file.Path

/** Application entry point for archive controllers; storage stays behind services. */
final class ArchiveService(registry: ProviderRegistry,repository: ArchiveRepository,
  discovery: FederatedDiscovery,downloads: ArchiveDownloads):
  def inventory: UIO[List[ProviderInventory]] = registry.inventory
  def search(query: ArchiveQuery): IO[ArchiveFailure,AcceptedJob] = discovery.accept(query)
  def page(id: String,cursor: Option[String],limit: Int): IO[ArchiveFailure,SearchPage] = repository.page(id,cursor,limit)
  def continue(id: String,provider: String): IO[ArchiveFailure,AcceptedJob] = discovery.continue(id,provider)
  def download(selection: DownloadSelection): IO[ArchiveFailure,AcceptedJob] = downloads.accept(selection)
  def downloadStatus(id: String): IO[ArchiveFailure,DownloadSnapshot] = repository.download(id)
  def artifact(id: String): IO[ArchiveFailure,(Path,StoredAsset)] = downloads.artifact(id)
