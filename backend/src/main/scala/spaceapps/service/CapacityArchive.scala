package spaceapps.service

import spaceapps.domain.{ApiError,ArchiveImage,Query}
import zio.*
import java.nio.file.{Files,Path}
import scala.jdk.CollectionConverters.*

/** Reserve each transfer's maximum size, excluding its already-written partial bytes. */
object CapacityArchive:
  private final case class Usage(completed:Long, free:Long, activeBytes:Long)

  def make(delegate:Archive,root:Path,maxCacheBytes:Long,maxProductBytes:Long,minFreeBytes:Long):Task[Archive]=
    for
      _ <- ZIO.fail(ApiError("invalid_configuration","Cache limits must be positive and fit one product"))
        .when(maxProductBytes<=0 || maxCacheBytes<maxProductBytes || minFreeBytes<0)
      reserved <- Ref.Synchronized.make(Map.empty[Path,Long])
    yield new Archive:
      def search(query:Query):Task[List[ArchiveImage]]=delegate.search(query)
      private def usage(active:Set[Path]):Task[Usage]=ZIO.attemptBlocking {
        val stream=Files.walk(root)
        var completed=0L
        var activeBytes=0L
        try
          stream.iterator().asScala.filter(Files.isRegularFile(_)).foreach { path=>
            val bytes=try Files.size(path) catch case _:java.nio.file.NoSuchFileException=>0L
            if active.contains(path.toAbsolutePath.normalize()) then activeBytes+=bytes else completed+=bytes
          }
        finally stream.close()
        Usage(completed,Files.getFileStore(root).getUsableSpace,activeBytes)
      }
      def fetch(image:ArchiveImage,destination:Path):Task[Unit]=
        val key=destination.toAbsolutePath.normalize()
        val reserve=reserved.modifyZIO { current=>
          usage(current.keySet).flatMap { disk=>
            val total=current.values.sum
            val remaining=math.max(0L,total-disk.activeBytes)
            if current.contains(key) || maxProductBytes>maxCacheBytes-disk.completed-total ||
              disk.free-remaining-maxProductBytes<minFreeBytes then
              ZIO.fail(ApiError("cache_capacity","Cache storage budget is exhausted; free space and retry",true))
            else ZIO.succeed(((),current.updated(key,maxProductBytes)))
          }
        }
        ZIO.acquireReleaseWith(reserve)(_=>reserved.update(_-key))(_=>delegate.fetch(image,destination))
