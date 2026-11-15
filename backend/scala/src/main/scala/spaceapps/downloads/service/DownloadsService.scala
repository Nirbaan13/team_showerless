package spaceapps.downloads.service

import spaceapps.downloads.model.*
import spaceapps.downloads.repository.DownloadsRepository
import zio.*
import zio.json.*
import zio.json.ast.Json
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

  def findObservations(query:ArchiveQuery):IO[ArchiveFailure,ObservationsFound]=
    discovery.find(query).map(result=>ObservationsFound(result.records.map(ObservationsContract.observation),result.outcomes,result.records.size))
  private def selected(job:DownloadSnapshot):IO[ArchiveFailure,List[ArchiveRecord]]=
    ZIO.foreach(job.selection.record_ids)(repository.record)
  def observationsDownload(selection:ObservationSelection):IO[ArchiveFailure,ObservationDownload]=
    downloads.accept(DownloadSelection(selection.observation_ids,selection.delivery),ObservationsContract.base).flatMap(j=>observationsStatus(j.id))
  def observationsStatus(id:String):IO[ArchiveFailure,ObservationDownload]=
    downloads.status(id).flatMap(job=>selected(job).map(records=>ObservationsContract.download(job,records)))
  def observationsEvents(id:String,after:Option[Long])=
    for
      job <- downloads.status(id)
      records <- selected(job)
      stream <- new DownloadEvents(repository).watch(id,after)
    yield stream.mapZIO { event=>
      ZIO.fromEither(event.data.fromJson[DownloadSnapshot].left.map(_=>ArchiveFailure("storage_error","Invalid stored download event"))).map { snapshot=>
        val target=event.data.fromJson[Json].toOption.flatMap(_.asObject.flatMap(_.get("chunk_id")).flatMap(_.asString))
        ObservationsContract.event(event,ObservationsContract.download(snapshot,records),target)
      }
    }
