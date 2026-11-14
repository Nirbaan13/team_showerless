package spaceapps.service

import spaceapps.domain.{ArchiveImage,Query}
import zio.*
import java.nio.file.Path

/** The same coordinator is carried into Jobs so reservation spans atomic publication. */
object CapacityArchive:
  private[service] final class Bounded(val delegate:Archive,val cache:FitsCache) extends Archive:
    def search(query:Query):Task[List[ArchiveImage]]=delegate.search(query)
    def fetch(image:ArchiveImage,destination:Path):Task[Unit]=cache.transfer(destination)(delegate.fetch(image,destination))
  def make(delegate:Archive,root:Path,maxCacheBytes:Long,maxProductBytes:Long,minFreeBytes:Long,
    cache:Option[FitsCache]=None):Task[Archive]=
    ZIO.fromOption(cache).orElse(FitsCache.open(root,root.resolve("jobs.sqlite"),maxCacheBytes,maxProductBytes,minFreeBytes))
      .map(new Bounded(delegate,_))
