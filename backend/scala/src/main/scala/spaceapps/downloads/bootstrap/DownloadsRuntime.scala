package spaceapps.downloads.bootstrap
import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.repository.DownloadsRepository
import spaceapps.downloads.model.*
import spaceapps.downloads.integrations.protocol.*
import spaceapps.downloads.integrations.providers.*
import spaceapps.infra.service.FileCache

import spaceapps.irsa.service.{Archive}
import spaceapps.downloads.service.{ArchiveLimits,DownloadJobs,FederatedDiscovery,ProviderRegistry,DownloadsService}
import zio.*
import zio.http.Client
import java.nio.file.Path
final case class DownloadsRuntime(registry: ProviderRegistry,repository: DownloadsRepository,discovery: FederatedDiscovery,downloads: DownloadJobs):
  def service: DownloadsService = new DownloadsService(registry,repository,discovery,downloads)
object DownloadsRuntime:
  def make(client: Client,irsa: Archive,data: Path,database: Path,limits: ArchiveLimits = ArchiveLimits(),capacity: Option[FileCache] = None): ZIO[Scope,ArchiveFailure,DownloadsRuntime] =
    for
      repository <- DownloadsRepository.open(database)
      transport=new ArchiveTransport(client,limits.metadata_bytes,Duration.fromMillis(limits.request_timeout_ms))
      registry=new ProviderRegistry(List(
        new IrsaProvider(irsa,repository),
        new ObsTapProvider("eso","https://archive.eso.org/tap_obs/sync",OriginPolicy.eso,transport),
        new ObsTapProvider("cadc","https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/argus/sync",OriginPolicy.cadc,transport),
        new GaiaProvider(transport),new NadcBassProvider(transport),new ArtXcProvider(transport),new LamostProvider(transport),new ArtXcCatalogProvider(transport),new UnwiseProvider(transport)
      )++PendingProvider.inventory.map(new PendingProvider(_)))
      discovery <- FederatedDiscovery.make(registry,repository,limits)
      sharedCapacity <- ZIO.fromOption(capacity).orElse(FileCache.open(data,database,20L*1024*1024*1024,limits.file_bytes,512L*1024*1024).mapError(ArchiveFailure.from))
      downloader=new StreamingDownloader(transport,data.resolve("archive-assets"),limits.file_bytes,Some(sharedCapacity))
      _ <- downloader.recover
      downloads <- DownloadJobs.make(registry,repository,downloader,limits)
      _ <- discovery.recover *> downloads.recover
      _ <- discovery.start *> downloads.start
    yield DownloadsRuntime(registry,repository,discovery,downloads)
