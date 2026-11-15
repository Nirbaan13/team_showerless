package spaceapps.downloads.service

import spaceapps.downloads.repository.DownloadsRepository
import spaceapps.downloads.model.*
import spaceapps.downloads.integrations.protocol.*
import zio.*
import java.nio.file.Path
import java.util.UUID

final class DownloadJobs private(registry:ProviderRegistry,repository:DownloadsRepository,
  downloader:StreamingDownloader,limits:ArchiveLimits,admission:Semaphore,transfers:Semaphore,
  perProvider:Map[String,Semaphore]):
  private def retry[A](effect: => IO[ArchiveFailure,A],attempt:Int=0):IO[ArchiveFailure,A]=
    effect.catchAll { error=>
      if error.retryable && attempt<limits.max_retries then
        val delay=error.retry_after_seconds.fold(200L << attempt)(seconds=>math.min(30L,math.max(0L,seconds))*1000L)
        ZIO.sleep(Duration.fromMillis(delay)) *> retry(effect,attempt+1)
      else ZIO.fail(error)
    }
  private def initial(record:ArchiveRecord,delivery:DeliveryRequest):DownloadChunk=
    val key=ArchiveAssetKey.key(record,delivery)
    DownloadChunk(key,record.id,s"/api/archive-assets/$key")
  private def hydrate(job:DownloadSnapshot):IO[ArchiveFailure,DownloadSnapshot]=
    if job.chunks.nonEmpty then ZIO.succeed(job.manifest)
    else ZIO.foreach(job.selection.record_ids)(repository.record).map { records=>
      val chunks=records.flatMap { record=>
        val saved=job.assets.filter(_.record_id==record.id)
        if saved.isEmpty then List(initial(record,job.selection.delivery))
        else saved.map { outcome=>
          val base=initial(record,job.selection.delivery)
          outcome.asset.fold(base.copy(status=outcome.status,error=outcome.error))(a=>DownloadChunk(a.id,record.id,a.artifact_url,outcome.status,outcome.error))
        }
      }
      job.copy(chunks=chunks).manifest
    }
  def accept(selection:DownloadSelection):IO[ArchiveFailure,AcceptedJob]=admission.withPermit {
    for
      _ <- ZIO.fail(ArchiveFailure("invalid_selection","Select 1 to 100 distinct server-known record IDs")).when(selection.record_ids.isEmpty || selection.record_ids.size>100 || selection.record_ids.distinct.size!=selection.record_ids.size)
      _ <- ZIO.foreachDiscard(selection.delivery.region)(c=>ZIO.fromEither(ArchiveQuery(c,List("validation")).validate))
      _ <- ZIO.fail(ArchiveFailure("invalid_selection","require_cutout needs a spatial region")).when(selection.delivery.mode==DeliveryMode.require_cutout && selection.delivery.region.isEmpty)
      records <- ZIO.foreach(selection.record_ids)(repository.record)
      active <- repository.allDownloads.map(_.count(j=> !j.terminal))
      _ <- ZIO.fail(ArchiveFailure("capacity_exceeded","Archive download queue is full",true)).when(active>=limits.max_active_jobs)
      id=UUID.randomUUID().toString
      url=s"/api/archive-downloads/$id"
      _ <- repository.saveDownload(DownloadSnapshot(id,selection,status_url=url,chunks=records.map(initial(_,selection.delivery))))
    yield AcceptedJob(id,url,Some(url+"/events"))
  }
  private def cached(id:String):ZIO[Scope,ArchiveFailure,Option[StoredAsset]]=
    repository.allDownloads.flatMap { jobs=>
      jobs.iterator.flatMap(_.assets).flatMap(_.asset).find(_.id==id) match
        case None=>ZIO.none
        case Some(asset)=>downloader.cached(id,asset.bytes).map(valid=>Option.when(valid)(asset))
    }
  /** Validate ready manifests without keeping files pinned between independent requests. */
  def status(id:String):IO[ArchiveFailure,DownloadSnapshot]=
    for
      stored <- repository.download(id)
      job <- hydrate(stored)
      invalid <- ZIO.scoped(ZIO.filter(job.assets.filter(_.status=="ready"))(outcome=>outcome.asset.fold[ZIO[Scope,ArchiveFailure,Boolean]](ZIO.succeed(true))(a=>downloader.cached(a.id,a.bytes).map(!_))))
      result <- if invalid.isEmpty then ZIO.succeed(job)
        else repository.updateDownload(id,if job.terminal then "job.completed" else "job.updated") { current=>
          val missing=invalid.flatMap(_.asset.map(_.id)).toSet
          val error=ArchiveFailure("cache_missing","The cached resource was evicted or removed; submit a new download",true)
          val assets=current.assets.map(a=>if a.asset.exists(x=>missing(x.id)) then a.copy(status="failed",error=Some(error)) else a)
          val chunks=job.chunks.map(c=>if missing(c.id) then c.copy(status="failed",error=Some(error)) else c)
          current.copy(assets=assets,chunks=chunks,status=if !current.terminal then current.status else if assets.exists(_.status=="ready") then "partial" else "failed")
        }
    yield result
  private def record(job:DownloadSnapshot,id:String):IO[ArchiveFailure,Unit]=ZIO.scoped {
    for
      product <- repository.record(id)
      provider <- registry.get(product.provider)
      key=ArchiveAssetKey.key(product,job.selection.delivery)
      _ <- downloader.protect(downloader.directory.resolve(key))
      _ <- downloader.serialized(downloader.directory.resolve(key)) {
        val work=for
          existing <- cached(key)
          assets <- existing match
            case Some(stored)=>ZIO.succeed(List(AssetOutcome(id,"ready",Some(stored),provenance=product.provenance)))
            case None=>perProvider(product.provider).withPermit(transfers.withPermit {
              retry(provider.resolve(product,job.selection.delivery).timeoutFail(ArchiveFailure("timeout","Archive product resolution timed out",true))(Duration.fromMillis(limits.request_timeout_ms))).flatMap { resolved=>
                if resolved.isEmpty then ZIO.fail(ArchiveFailure("missing_product","Provider returned no selected science product"))
                else ZIO.foreach(resolved) { asset=>
                  downloader.protect(downloader.directory.resolve(asset.id)) *>
                    retry(downloader.fetch(asset,provider.origins)).either.map {
                      case Right(stored)=>AssetOutcome(id,"ready",Some(stored),provenance=product.provenance)
                      case Left(error)=>AssetOutcome(id,if error.code=="no_content" then "skipped" else "failed",error=Some(error),provenance=product.provenance)
                    }
                }
              }
            })
        yield assets
        for
          _ <- repository.updateDownload(job.id,"chunk.started")(current=>current.copy(chunks=current.chunks.map(c=>if c.record_id==id then c.copy(status="downloading") else c)))
          assets <- work.catchAllDefect(_=>ZIO.fail(ArchiveFailure("provider_error","Archive provider could not resolve or transfer the selected product")))
            .catchAll(error=>ZIO.succeed(List(AssetOutcome(id,if error.code=="no_content" then "skipped" else "failed",error=Some(error),provenance=product.provenance))))
          _ <- repository.updateDownload(job.id,if assets.forall(_.status=="ready") then "chunk.ready" else "chunk.failed") { current=>
            val chunks=assets.map { outcome=>
              val pending=initial(product,job.selection.delivery)
              outcome.asset.fold(pending.copy(status=outcome.status,error=outcome.error))(a=>DownloadChunk(a.id,id,a.artifact_url,outcome.status,outcome.error))
            }
            current.copy(assets=current.assets.filterNot(_.record_id==id)++assets,chunks=current.chunks.filterNot(_.record_id==id)++chunks)
          }
        yield ()
      }
    yield ()
  }
  def execute(id:String):IO[ArchiveFailure,Unit]=
    repository.download(id).flatMap(hydrate).flatMap { hydrated=>
      repository.updateDownload(id) { job=>
        if job.status!="queued" then throw ArchiveFailure("job_active","Download is not queued")
        job.copy(status="running",chunks=hydrated.chunks)
      }
    }.flatMap { job=>
      val work=ZIO.foreachParDiscard(job.selection.record_ids.filterNot(r=>job.assets.exists(_.record_id==r)))(record(job,_)).withParallelism(limits.global_parallelism) *>
        repository.updateDownload(job.id,"job.completed") { current=>
          val ready=current.assets.count(_.status=="ready")
          current.copy(status=if ready==current.assets.size then "completed" else if ready==0 then "failed" else "partial")
        }.unit
      work.catchAll { error=>repository.updateDownload(job.id,"job.completed") { current=>
        val failed=current.chunks.map(c=>if Set("pending","downloading")(c.status) then c.copy(status="failed",error=Some(error)) else c)
        current.copy(status="failed",chunks=failed)
      }.unit }
    }
  def artifact(id:String):IO[ArchiveFailure,(Path,StoredAsset)]=ZIO.scoped {
    if !id.matches("[a-f0-9]{64}") then ZIO.fail(ArchiveFailure("not_found","Archive asset not found"))
    else cached(id).flatMap {
      case Some(asset)=>ZIO.succeed(downloader.directory.resolve(id)->asset)
      case None=>ZIO.fail(ArchiveFailure("not_found","Archive asset not found"))
    }
  }
  def resource(id:String):ZIO[Scope,ArchiveFailure,AssetResource]=
    if !id.matches("[a-f0-9]{64}") then ZIO.fail(ArchiveFailure("not_found","Archive asset not found"))
    else cached(id).flatMap {
      case Some(asset)=>ZIO.succeed(AssetResource.Ready(downloader.directory.resolve(id),asset))
      case None=>repository.allDownloads.flatMap { jobs=>
        ZIO.foreach(jobs)(hydrate).flatMap { snapshots=>
          val chunks=snapshots.flatMap(_.chunks).filter(_.id==id)
          if chunks.exists(c=>Set("pending","downloading")(c.status)) then ZIO.succeed(AssetResource.Pending)
          else if chunks.nonEmpty then ZIO.succeed(AssetResource.Failed(chunks.flatMap(_.error).headOption.getOrElse(ArchiveFailure("cache_missing","Cached resource is unavailable; submit a new download",true))))
          else ZIO.fail(ArchiveFailure("not_found","Archive asset not found"))
        }
      }
    }
  def recover:IO[ArchiveFailure,Unit]=repository.allDownloads.flatMap { jobs=>
    ZIO.foreachDiscard(jobs.filter(j=> !j.terminal)) { job=>
      hydrate(job).flatMap { hydrated=>
        ZIO.scoped(ZIO.filter(hydrated.assets)(a=>a.asset.fold[ZIO[Scope,ArchiveFailure,Boolean]](ZIO.succeed(a.status!="ready"))(s=>downloader.cached(s.id,s.bytes)))).flatMap { assets=>
          val finished=assets.map(_.record_id).toSet
          repository.updateDownload(job.id)(_.copy(status="queued",assets=assets,chunks=hydrated.chunks.map(c=>if finished(c.record_id) then c else c.copy(status="pending",error=None)))).unit
        }
      }
    }
  }
  def start:ZIO[Scope,Nothing,Unit]=
    val poll=repository.allDownloads.flatMap(jobs=>ZIO.foreachDiscard(jobs.filter(_.status=="queued"))(j=>execute(j.id).catchAll(_=>ZIO.unit))).catchAll(_=>ZIO.unit) *> ZIO.sleep(200.millis)
    ZIO.foreachDiscard(1 to limits.global_parallelism)(_=>poll.forever.forkScoped)

object DownloadJobs:
  def make(registry:ProviderRegistry,repository:DownloadsRepository,downloader:StreamingDownloader,limits:ArchiveLimits=ArchiveLimits()):UIO[DownloadJobs]=
    for
      admission <- Semaphore.make(1)
      transfers <- Semaphore.make(limits.global_parallelism.toLong)
      providers <- ZIO.foreach(registry.providers)(p=>Semaphore.make(limits.per_provider_parallelism.toLong).map(p.id->_))
    yield new DownloadJobs(registry,repository,downloader,limits,admission,transfers,providers.toMap)
