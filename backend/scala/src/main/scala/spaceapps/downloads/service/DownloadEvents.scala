package spaceapps.downloads.service

import spaceapps.downloads.model.*
import spaceapps.downloads.repository.DownloadsRepository
import spaceapps.infra.model.Event
import zio.*
import zio.json.*
import zio.stream.ZStream

/** Persistent sequence IDs support reconnects without a JVM-local subscription race. */
final class DownloadEvents(repository:DownloadsRepository):
  def watch(id:String,after:Option[Long]):IO[ArchiveFailure,ZStream[Any,ArchiveFailure,Event]]=
    repository.snapshot(id).flatMap { (job,cursor)=>
      ZIO.fail(ArchiveFailure("invalid_cursor","Last-Event-ID must be between zero and the latest committed event"))
        .when(after.exists(n=>n<0 || n>cursor)).as {
          val snapshot=ZStream.succeed(Event(cursor,"job.updated",job.manifest.toJson))
          val terminal=ZStream.succeed(Event(cursor,"job.completed",job.manifest.toJson))
          after match
            case None if job.terminal=>snapshot ++ terminal
            case None=>snapshot ++ updates(id,cursor)
            case Some(n) if job.terminal=>
              if n==cursor then ZStream.empty
              else replay(id,n,cursor)
            case Some(n)=>updates(id,n)
        }
    }
  private def replay(id:String,from:Long,through:Long):ZStream[Any,ArchiveFailure,Event]=
    ZStream.unfoldChunkZIO(from) { next=>
      if next>=through then ZIO.none
      else repository.eventsAfter(id,next).flatMap { events=>
        val batch=events.takeWhile(_.sequence<=through)
        if batch.isEmpty then ZIO.fail(ArchiveFailure("storage_error","The committed download event log is incomplete"))
        else ZIO.some((Chunk.fromIterable(batch),batch.last.sequence))
      }
    }
  private def updates(id:String,cursor:Long):ZStream[Any,ArchiveFailure,Event]=
    ZStream.unfoldChunkZIO(cursor) { next=>
      repository.eventsAfter(id,next).flatMap {
        case Nil=>ZIO.sleep(100.millis).as(Some((Chunk.empty[Event],next)))
        case events=>ZIO.succeed(Some((Chunk.fromIterable(events),events.last.sequence)))
      }
    }.takeUntil(_.name=="job.completed")
