package spaceapps.archive.service
import spaceapps.archive.repository.ArchiveRepository
import spaceapps.archive.domain.*
import spaceapps.archive.integrations.protocol.*
import zio.*
import java.nio.file.{Files,Path}
import java.util.UUID
final class ArchiveDownloads private(registry: ProviderRegistry,repository: ArchiveRepository,downloader: StreamingDownloader,limits: ArchiveLimits,admission: Semaphore,execution: Semaphore):
  def accept(selection: DownloadSelection): IO[ArchiveFailure,AcceptedJob] = admission.withPermit {
    for
      _ <- ZIO.fail(ArchiveFailure("invalid_selection","Select 1 to 100 distinct server-known record IDs")).when(selection.record_ids.isEmpty || selection.record_ids.size>100 || selection.record_ids.distinct.size!=selection.record_ids.size)
      _ <- ZIO.foreachDiscard(selection.delivery.region)(c=>ZIO.fromEither(ArchiveQuery(c,List("validation")).validate))
      _ <- ZIO.fail(ArchiveFailure("invalid_selection","require_cutout needs a spatial region")).when(selection.delivery.mode==DeliveryMode.require_cutout && selection.delivery.region.isEmpty)
      _ <- ZIO.foreachDiscard(selection.record_ids)(repository.record)
      active <- repository.allDownloads.map(_.count(j=>Set("queued","running")(j.status)))
      _ <- ZIO.fail(ArchiveFailure("capacity_exceeded","Archive download queue is full",true)).when(active>=limits.max_active_jobs)
      id=UUID.randomUUID().toString;url=s"/api/archive-downloads/$id"
      _ <- repository.saveDownload(DownloadSnapshot(id,selection,status_url=url))
    yield AcceptedJob(id,url)
  }
  private def cached(id: String): IO[ArchiveFailure,Option[StoredAsset]] = repository.allDownloads.flatMap { jobs=>
    val asset=jobs.flatMap(_.assets.flatMap(_.asset)).find(_.id==id)
    ZIO.attemptBlocking(asset.filter(a=>Files.isRegularFile(downloader.directory.resolve(id)) && Files.size(downloader.directory.resolve(id))==a.bytes)).mapError(ArchiveFailure.from)
  }
  def execute(id: String): IO[ArchiveFailure,Unit] = execution.withPermit {
    repository.updateDownload(id) { job=>
      if job.status!="queued" then throw ArchiveFailure("job_active","Download is not queued")
      job.copy(status="running")
    }.flatMap { job=>
      ZIO.foreachDiscard(job.selection.record_ids.filterNot(r=>job.assets.exists(_.record_id==r))) { id=>
        (for
          record <- repository.record(id)
          provider <- registry.get(record.provider)
          existing <- cached(ArchiveAssetKey.key(record,job.selection.delivery))
          assets <- existing match
            case Some(stored)=>ZIO.succeed(List(AssetOutcome(id,"ready",Some(stored),provenance=record.provenance)))
            case None=>provider.resolve(record,job.selection.delivery).flatMap { resolved=>
              if resolved.isEmpty then ZIO.fail(ArchiveFailure("missing_product","Provider returned no selected science product"))
              else ZIO.foreach(resolved) { asset=>
                downloader.fetch(asset,provider.origins).either.map {
                  case Right(stored)=>AssetOutcome(id,"ready",Some(stored),provenance=record.provenance)
                  case Left(error)=>AssetOutcome(id,if error.code=="no_content" then "skipped" else "failed",error=Some(error),provenance=record.provenance)
                }
              }
            }
        yield assets).catchAllDefect(_=>ZIO.fail(ArchiveFailure("provider_error","Archive provider could not resolve or transfer the selected product"))).catchAll { error=>repository.record(id).map(r=>List(AssetOutcome(id,if error.code=="no_content" then "skipped" else "failed",error=Some(error),provenance=r.provenance))) }.flatMap { assets=>
          repository.updateDownload(job.id)(current=>current.copy(assets=current.assets++assets)).unit
        }
      } *> repository.updateDownload(job.id) { current=>
        val ready=current.assets.count(_.status=="ready")
        current.copy(status=if ready==current.assets.size then "completed" else if ready==0 then "failed" else "partial")
      }.unit
    }
  }
  def artifact(id: String): IO[ArchiveFailure,(Path,StoredAsset)] =
    if !id.matches("[a-f0-9]{64}") then ZIO.fail(ArchiveFailure("not_found","Archive asset not found"))
    else cached(id).flatMap {
      case Some(asset)=>ZIO.succeed(downloader.directory.resolve(id)->asset)
      case None=>ZIO.fail(ArchiveFailure("not_found","Archive asset not found"))
    }
  def recover: IO[ArchiveFailure,Unit] = repository.allDownloads.flatMap(jobs=>ZIO.foreachDiscard(jobs.filter(_.status=="running"))(j=>repository.updateDownload(j.id)(_.copy(status="queued"))))
  def start: ZIO[Scope,Nothing,Unit] =
    val poll=repository.allDownloads.flatMap(jobs=>ZIO.foreachDiscard(jobs.filter(_.status=="queued"))(j=>execute(j.id).catchAll(_=>ZIO.unit))).catchAll(_=>ZIO.unit) *> ZIO.sleep(200.millis)
    poll.forever.forkScoped.unit
object ArchiveDownloads:
  def make(registry: ProviderRegistry,repository: ArchiveRepository,downloader: StreamingDownloader,limits: ArchiveLimits = ArchiveLimits()): UIO[ArchiveDownloads] =
    for
      admission <- Semaphore.make(1)
      execution <- Semaphore.make(1)
    yield new ArchiveDownloads(registry,repository,downloader,limits,admission,execution)
