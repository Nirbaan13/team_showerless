package spaceapps.downloads.service
import spaceapps.downloads.model.*
import spaceapps.downloads.repository.DownloadsRepository
import zio.*

/** Cache availability is a port; state invalidation always runs in a SQLite transaction. */
final class DownloadManifests(repository:DownloadsRepository,available:(String,Long)=>ZIO[Scope,ArchiveFailure,Boolean]):
  def initial(record:ArchiveRecord,delivery:DeliveryRequest):DownloadChunk=
    val key=ArchiveAssetKey.key(record,delivery)
    DownloadChunk(key,record.id,s"/api/archive-assets/$key")
  def hydrate(job:DownloadSnapshot):IO[ArchiveFailure,DownloadSnapshot]=
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
  /** Validate ready manifests without keeping files pinned between independent requests. */
  def status(id:String):IO[ArchiveFailure,DownloadSnapshot]=
    for
      stored <- repository.download(id)
      job <- hydrate(stored)
      invalid <- ZIO.scoped(ZIO.filter(job.assets.filter(_.status=="ready"))(outcome=>outcome.asset.fold[ZIO[Scope,ArchiveFailure,Boolean]](ZIO.succeed(true))(a=>available(a.id,a.bytes).map(!_))))
      result <- if invalid.isEmpty then ZIO.succeed(job)
        else repository.modifyDownload(id) { current=>
          val missing=invalid.flatMap(_.asset.map(_.id)).toSet
          val error=ArchiveFailure("cache_missing","The cached resource was evicted or removed; submit a new download",true)
          val assets=current.assets.map(a=>if a.asset.exists(x=>missing(x.id)) then a.copy(status="failed",error=Some(error)) else a)
          val chunks=(if current.chunks.nonEmpty then current.chunks else job.chunks).map(c=>if missing(c.id) then c.copy(status="failed",error=Some(error)) else c)
          val next=current.copy(assets=assets,chunks=chunks,status=if !current.terminal then current.status else if assets.exists(_.status=="ready") then "partial" else "failed")
          next -> (if next.terminal then "job.completed" else "job.updated")
        }
    yield result
