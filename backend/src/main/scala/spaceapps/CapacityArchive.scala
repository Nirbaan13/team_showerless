package spaceapps

import zio.*
import java.nio.file.{Files,Path}
import scala.jdk.CollectionConverters.*

/** Reserve the maximum transfer size before consuming disk space. */
object CapacityArchive:
  def make(delegate:Archive,root:Path,maxCacheBytes:Long,maxProductBytes:Long,minFreeBytes:Long):Task[Archive]=
    for
      _ <- ZIO.fail(ApiError("invalid_configuration","Cache limits must be positive and fit one product")).when(maxProductBytes<=0 || maxCacheBytes<maxProductBytes || minFreeBytes<0)
      reserved <- Ref.Synchronized.make(0L)
    yield new Archive:
      def search(query:Query):Task[List[ArchiveImage]]=delegate.search(query)
      private def usage:Task[(Long,Long)]=ZIO.attemptBlocking {
        val stream=Files.walk(root)
        val used=try stream.iterator().asScala.filter(p=>Files.isRegularFile(p)).map(p=>try Files.size(p) catch case _:java.nio.file.NoSuchFileException=>0L).sum finally stream.close()
        (used,Files.getFileStore(root).getUsableSpace)
      }
      def fetch(image:ArchiveImage,destination:Path):Task[Unit]=
        val reserve=reserved.modifyZIO { current=>
          usage.flatMap { (used,free)=>
            if used+current+maxProductBytes>maxCacheBytes || free-current-maxProductBytes<minFreeBytes then
              ZIO.fail(ApiError("cache_capacity","Cache storage budget is exhausted; free space and retry",true))
            else ZIO.succeed(((),current+maxProductBytes))
          }
        }
        ZIO.acquireReleaseWith(reserve)(_=>reserved.update(_-maxProductBytes))(_=>delegate.fetch(image,destination))
