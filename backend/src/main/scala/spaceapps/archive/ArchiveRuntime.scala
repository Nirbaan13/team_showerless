package spaceapps.archive
import spaceapps.archive.protocol.*
import spaceapps.archive.providers.*
import spaceapps.service.{Archive,FitsCache}
import zio.*
import zio.http.Client
import java.nio.file.Path
final case class ArchiveRuntime(registry: ProviderRegistry,repository: ArchiveRepository,discovery: FederatedDiscovery,downloads: ArchiveDownloads)
object ArchiveRuntime:
  def make(client: Client,irsa: Archive,data: Path,database: Path,limits: ArchiveLimits = ArchiveLimits(),capacity: Option[FitsCache] = None): ZIO[Scope,ArchiveFailure,ArchiveRuntime] =
    for
      repository <- ArchiveRepository.open(database)
      transport=new ArchiveTransport(client,limits.metadata_bytes,Duration.fromMillis(limits.request_timeout_ms))
      registry=new ProviderRegistry(List(
        new IrsaProvider(irsa,repository),
        new ObsTapProvider("eso","https://archive.eso.org/tap_obs/sync",OriginPolicy.eso,transport),
        new ObsTapProvider("cadc","https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/argus/sync",OriginPolicy.cadc,transport),
        new GaiaProvider(transport),new NadcBassProvider(transport),new ArtXcProvider(transport),new LamostProvider(transport),new ArtXcCatalogProvider(transport)
      )++PendingProvider.inventory.map(new PendingProvider(_)))
      discovery <- FederatedDiscovery.make(registry,repository,limits)
      sharedCapacity <- ZIO.fromOption(capacity).orElse(FitsCache.open(data,database,20L*1024*1024*1024,limits.file_bytes,512L*1024*1024).mapError(ArchiveFailure.from))
      downloader=new StreamingDownloader(transport,data.resolve("archive-assets"),limits.file_bytes,Some(sharedCapacity))
      _ <- downloader.recover
      downloads <- ArchiveDownloads.make(registry,repository,downloader,limits)
      _ <- discovery.recover *> downloads.recover
      _ <- discovery.start *> downloads.start
    yield ArchiveRuntime(registry,repository,discovery,downloads)
