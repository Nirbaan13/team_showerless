package spaceapps.service

import spaceapps.domain.ApiError
import spaceapps.repository.FitsCacheRepository
import zio.*
import java.nio.file.{Files,Path,StandardCopyOption}
import java.util.UUID
import scala.jdk.CollectionConverters.*

/** One coordinator owns admission, atomic publication, readers and processing leases. */
final class FitsCache private(root:Path, store:FitsCacheRepository,maxCacheBytes:Long,maxProductBytes:Long,
  minFreeBytes:Long,gate:Semaphore,state:Ref[FitsCache.State]):
  import FitsCache.*
  private def normalized(path:Path)=path.toAbsolutePath.normalize()
  private def identity(path:Path)=root.relativize(path).toString
  private def owned(path:Path):Boolean=
    val relative=root.relativize(path)
    path.startsWith(root) && ((relative.getNameCount==2 && relative.getName(0).toString=="raw" && relative.getFileName.toString.matches("[0-9a-f]{64}[.]fits")) ||
      (relative.getNameCount==3 && relative.getName(0).toString=="jobs" && relative.getFileName.toString.matches("[0-9a-f]{40}[.]fits")))
  private def valid(path:Path)=Files.isRegularFile(path) && Files.size(path)>0
  private def touch(path:Path):Task[Unit]=
    if !owned(path) then ZIO.unit
    else for
      now <- Clock.currentTime(java.util.concurrent.TimeUnit.MILLISECONDS)
      stamp <- state.modify(s=>(math.max(now,s.clock+1),s.copy(clock=math.max(now,s.clock+1))))
      _ <- ZIO.attemptBlocking(store.put(identity(path),path,Files.size(path),stamp))
    yield ()
  /** Protect even a missing output so publication cannot race its first processing/read lease. */
  def protect(path:Path):ZIO[Scope,Throwable,Unit]=
    val key=normalized(path)
    ZIO.acquireRelease(gate.withPermit(state.update(s=>s.copy(pins=s.pins.updated(key,s.pins.getOrElse(key,0)+1)))))(
      _=>gate.withPermit(state.update { s=>
        val count=s.pins.getOrElse(key,1)-1
        s.copy(pins=if count==0 then s.pins-key else s.pins.updated(key,count))
      })).unit
  def cached(path:Path):ZIO[Scope,Throwable,Option[Path]]=
    val key=normalized(path)
    protect(key) *> gate.withPermit(ZIO.attemptBlocking(valid(key)).flatMap {
      case true=>touch(key).as(Some(key))
      case false=>ZIO.none
    })
  private def usage(active:Set[Path]):Task[Usage]=ZIO.attemptBlocking {
    val stream=Files.walk(root)
    var completed=0L
    var partial=0L
    val database=store.databasePath.toAbsolutePath.normalize().toString
    try stream.iterator().asScala.filter(Files.isRegularFile(_)).foreach { p=>
      val path=normalized(p)
      // Administrative SQLite pages are not cached products and grow independently of eviction.
      if !Set(database,database+"-wal",database+"-shm",database+"-journal").contains(path.toString) then
        val bytes=try Files.size(path) catch case _:java.nio.file.NoSuchFileException=>0L
        if active.contains(path) then partial+=bytes else completed+=bytes
    }
    finally stream.close()
    Usage(completed,Files.getFileStore(root).getUsableSpace,partial)
  }
  private def reserve(path:Path):Task[Unit]=gate.withPermit {
    def admit(candidates:List[(String,Path,Long,Long)]):Task[Unit]=
      for
        current <- state.get
        disk <- usage(current.reservations.keySet)
        total=current.reservations.values.sum
        fits=maxProductBytes<=maxCacheBytes-disk.completed-total && disk.free-math.max(0L,total-disk.partial)-maxProductBytes>=minFreeBytes
        _ <- if fits then state.update(s=>s.copy(reservations=s.reservations.updated(path,maxProductBytes)))
          else candidates match
            case (id,candidate,_,_)::rest if owned(candidate) && !current.pins.contains(candidate) && !current.reservations.contains(candidate)=>
              ZIO.attemptBlocking { Files.deleteIfExists(candidate); store.remove(id) } *> admit(rest)
            case _::rest=>admit(rest)
            case Nil=>ZIO.fail(ApiError("cache_capacity","Cache storage budget is exhausted; release active files or retry",true))
      yield ()
    state.get.flatMap { current=>
      if current.reservations.contains(path) then ZIO.fail(ApiError("cache_capacity","A transfer already owns this destination",true))
      else ZIO.attemptBlocking(store.entries()).flatMap(admit)
    }
  }
  def transfer[A](destination:Path)(fetch:Task[A]):Task[A]=
    val path=normalized(destination)
    ZIO.acquireReleaseWith(reserve(path))(_=>gate.withPermit(state.update(s=>s.copy(reservations=s.reservations-path))))(_=>fetch)
  def publish(output:Path)(produce:Path=>Task[Unit]):Task[Unit]=
    val target=normalized(output)
    val part=target.resolveSibling(target.getFileName.toString+"."+UUID.randomUUID().toString+".part")
    ZIO.scoped { protect(target) *> transfer(part) {
      (ZIO.attemptBlocking(Files.createDirectories(target.getParent)) *> produce(part) *>
        gate.withPermit {
          (ZIO.attemptBlocking {
            if !valid(part) then throw ApiError("invalid_product","The generated file was empty or absent")
            if Files.size(part)>maxProductBytes then throw ApiError("archive_overflow","Product exceeds configured maximum size")
            Files.move(part,target,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING)
          } *> touch(target) *> state.update(s=>s.copy(reservations=s.reservations-part))).uninterruptible
        }).ensuring(ZIO.attemptBlocking(Files.deleteIfExists(part)).ignore)
    } }
  private[service] def reconcile:Task[Unit]=gate.withPermit {
    ZIO.attemptBlocking {
      val existing=store.entries()
      existing.foreach { (id,path,_,_)=>if !owned(path) || !valid(path) then store.remove(id) }
      val indexed=existing.map(_._2).toSet
      val stream=Files.walk(root)
      try stream.iterator().asScala.filter(p=>Files.isRegularFile(p) && owned(normalized(p)) && valid(p) && !indexed.contains(normalized(p))).foreach { p=>
        val path=normalized(p)
        store.put(identity(path),path,Files.size(path),Files.getLastModifiedTime(path).toMillis)
      }
      finally stream.close()
      store.entries().map(_._4).maxOption.getOrElse(0L)
    }.flatMap(n=>state.update(_.copy(clock=n)))
  }

object FitsCache:
  private final case class State(pins:Map[Path,Int],reservations:Map[Path,Long],clock:Long)
  private final case class Usage(completed:Long,free:Long,partial:Long)
  def open(root:Path,database:Path,maxCacheBytes:Long,maxProductBytes:Long,minFreeBytes:Long):Task[FitsCache]=
    for
      _ <- ZIO.fail(ApiError("invalid_configuration","Cache limits must be positive and fit one product"))
        .when(maxProductBytes<=0 || maxCacheBytes<maxProductBytes || minFreeBytes<0)
      _ <- ZIO.attemptBlocking { Files.createDirectories(root); Files.createDirectories(database.toAbsolutePath.getParent) }
      store=new FitsCacheRepository(database)
      _ <- ZIO.attemptBlocking(store.initialize())
      gate <- Semaphore.make(1)
      state <- Ref.make(State(Map.empty,Map.empty,0L))
      cache=new FitsCache(root.toAbsolutePath.normalize(),store,maxCacheBytes,maxProductBytes,minFreeBytes,gate,state)
      _ <- cache.reconcile
    yield cache
