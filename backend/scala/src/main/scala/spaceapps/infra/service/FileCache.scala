package spaceapps.infra.service

import spaceapps.infra.model.ApiError
import spaceapps.infra.repository.FileCacheRepository
import zio.*
import java.nio.file.{Files,Path,StandardCopyOption,SimpleFileVisitor,FileVisitResult,NoSuchFileException}
import java.nio.file.attribute.BasicFileAttributes
import java.io.IOException
import java.util.UUID
import scala.jdk.CollectionConverters.*

/** One coordinator owns admission, atomic publication, readers and processing leases. */
final class FileCache private(root:Path, store:FileCacheRepository,maxCacheBytes:Long,maxProductBytes:Long,
  minFreeBytes:Long,gate:Semaphore,state:Ref[FileCache.State],locks:Vector[Semaphore]):
  import FileCache.*
  private def normalized(path:Path)=path.toAbsolutePath.normalize()
  private def identity(path:Path)=root.relativize(path).toString
  private def safe(path:Path):Boolean=
    path.startsWith(root) && Iterator.iterate(path)(_.getParent).takeWhile(p=>p!=null && p.startsWith(root)).forall(p=> !Files.isSymbolicLink(p))
  private def owned(path:Path):Boolean=
    val relative=root.relativize(path)
    safe(path) && (
      (relative.getNameCount==2 && relative.getName(0).toString=="raw" && relative.getFileName.toString.matches("[0-9a-f]{64}[.]fits")) ||
      (relative.getNameCount==3 && relative.getName(0).toString=="jobs" && relative.getFileName.toString.matches("[0-9a-f]{40}[.](?:fits|png)")) ||
      (relative.getNameCount==2 && relative.getName(0).toString=="archive-assets" && relative.getFileName.toString.matches("[a-zA-Z0-9_-]{1,128}")) ||
      (relative.getNameCount==2 && relative.getName(0).toString=="calibration-cache" && relative.getFileName.toString.matches("[0-9a-f]{64}")) ||
      (relative.getNameCount==3 && relative.getName(0).toString=="unifications" && relative.getName(1).toString.matches("[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}") && relative.getFileName.toString=="dataset.npz"))
  private def valid(path:Path)=safe(path) && Files.isRegularFile(path) && Files.size(path)>0
  /** Serialize lookup plus transfer for the same destination, across every producer. */
  def serialized[R,E,A](path:Path)(effect:ZIO[R,E,A]):ZIO[R,E,A]=
    locks((normalized(path).hashCode & Int.MaxValue)%locks.size).withPermit(effect)
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
    var completed=0L
    var partial=0L
    val database=store.databasePath.toAbsolutePath.normalize().toString
    val databases=Set(database,database+"-wal",database+"-shm",database+"-journal")
    // SQLite sidecars and atomic-publication scratch files may disappear while
    // directory entries are being visited. A missing entry is no longer usage;
    // other I/O failures must still reject admission.
    Files.walkFileTree(root,new SimpleFileVisitor[Path]:
      override def visitFile(file:Path,attributes:BasicFileAttributes):FileVisitResult=
        val path=normalized(file)
        val administrative=databases(path.toString) || (path.getParent==root && path.getFileName.toString.matches(".*[.](?:sqlite|sqlite3|db)(?:-wal|-shm|-journal)?"))
        if attributes.isRegularFile && !administrative then
          if active.exists(path.startsWith(_)) then partial+=attributes.size() else completed+=attributes.size()
        FileVisitResult.CONTINUE
      override def visitFileFailed(file:Path,error:IOException):FileVisitResult=
        if error.isInstanceOf[NoSuchFileException] then FileVisitResult.CONTINUE else throw error
      override def postVisitDirectory(directory:Path,error:IOException):FileVisitResult=
        if error==null || error.isInstanceOf[NoSuchFileException] then FileVisitResult.CONTINUE else throw error
    )
    Usage(completed,Files.getFileStore(root).getUsableSpace,partial)
  }
  private def reserve(path:Path,bytes:Long,product:Boolean=true):Task[Unit]=
    if !safe(path) || bytes<=0 || (product && bytes>maxProductBytes) then ZIO.fail(ApiError("archive_overflow","Invalid destination or product reservation exceeds configured maximum size"))
    else gate.withPermit {
    def admit(candidates:List[(String,Path,Long,Long)]):Task[Unit]=
      for
        current <- state.get
        disk <- usage(current.reservations.keySet)
        total=current.reservations.values.sum
        fits=bytes<=maxCacheBytes-disk.completed-total && disk.free-math.max(0L,total-disk.partial)-bytes>=minFreeBytes
        _ <- if fits then state.update(s=>s.copy(reservations=s.reservations.updated(path,bytes)))
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
  /** Reserve staging and output capacity before making immutable unification snapshots. */
  def withReservation[A](bytes:Long)(work:Task[A]):Task[A]=
    val token=root.resolve("unifications").resolve(UUID.randomUUID().toString+".reservation")
    withReservation(token,bytes)(work)
  /** Files under this staging directory consume its existing reservation. */
  def withReservation[A](destination:Path,bytes:Long)(work:Task[A]):Task[A]=
    val path=normalized(destination)
    ZIO.fail(ApiError("invalid_product","Reservation must remain inside managed storage")).unless(path.startsWith(root) && path!=root) *>
      ZIO.acquireReleaseWith(reserve(path,bytes,product=false))(_=>gate.withPermit(state.update(s=>s.copy(reservations=s.reservations-path))))(_=>work)
  /** Atomically adopt validated staging bytes without allocating another product budget. */
  def adopt(output:Path,staged:Path):Task[Unit]=
    val target=normalized(output)
    val source=normalized(staged)
    ZIO.scoped { protect(target) *> gate.withPermit {
      (for
        current <- state.get
        _ <- ZIO.fail(ApiError("invalid_product","Publication requires an active staging reservation")).unless(
          owned(target) && current.reservations.keys.exists(p=>source.startsWith(p) && target.startsWith(p)))
        _ <- ZIO.attemptBlocking {
          if !valid(source) || Files.isSymbolicLink(source) || Files.size(source)>maxProductBytes then
            throw ApiError("invalid_product","Generated product is absent or exceeds its configured byte budget")
          Files.move(source,target,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING)
        }
        _ <- touch(target)
      yield ()).uninterruptible
    } }
  def transfer[A](destination:Path,bytes:Long=maxProductBytes)(fetch:Task[A]):Task[A]=
    val path=normalized(destination)
    ZIO.acquireReleaseWith(reserve(path,bytes))(_=>gate.withPermit(state.update(s=>s.copy(reservations=s.reservations-path))))(_=>fetch)
  /** Register every published product under the same gate used by eviction. */
  def commit(part:Path,output:Path):Task[Unit]=gate.withPermit {
    val target=normalized(output)
    (ZIO.attemptBlocking {
      if !owned(target) || !safe(normalized(part)) then throw ApiError("invalid_product","Unsafe managed cache product path")
      if !valid(part) then throw ApiError("invalid_product","The generated file was empty or absent")
      if Files.size(part)>maxProductBytes then throw ApiError("archive_overflow","Product exceeds configured maximum size")
      Files.move(part,target,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING)
    } *> touch(target) *> state.update(s=>s.copy(reservations=s.reservations-normalized(part)))).uninterruptible
  }
  def publish(output:Path,bytes:Long=maxProductBytes)(produce:Path=>Task[Unit]):Task[Unit]=
    val target=normalized(output)
    val part=target.resolveSibling(target.getFileName.toString+"."+UUID.randomUUID().toString+".part")
    ZIO.scoped { protect(target) *> transfer(part,bytes) {
      (ZIO.attemptBlocking(Files.createDirectories(target.getParent)) *> produce(part) *> commit(part,target))
        .ensuring(ZIO.attemptBlocking(Files.deleteIfExists(part)).ignore)
    } }
  private[infra] def reconcile:Task[Unit]=gate.withPermit {
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

object FileCache:
  private final case class State(pins:Map[Path,Int],reservations:Map[Path,Long],clock:Long)
  private final case class Usage(completed:Long,free:Long,partial:Long)
  /** Startup only: reclaim every producer's known scratch names before workers start. */
  def recover(root:Path):Task[Unit]=ZIO.attemptBlocking {
    val base=root.toAbsolutePath.normalize()
    val uuid="[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
    val paths=Files.walk(base)
    try paths.iterator().asScala.foreach { path=>
      val relative=base.relativize(path)
      val name=path.getFileName.toString
      val partial=
        (relative.getNameCount==2 && relative.getName(0).toString=="raw" && name.matches(s"[0-9a-f]{64}[.]fits[.]$uuid[.]part")) ||
        (relative.getNameCount==3 && relative.getName(0).toString=="jobs" && name.matches(s"[0-9a-f]{40}[.](?:fits|png)[.]$uuid[.]part")) ||
        (relative.getNameCount==2 && relative.getName(0).toString=="calibration-cache" && name.matches(s"[0-9a-f]{64}(?:[.]$uuid)?[.]part")) ||
        (relative.getNameCount==2 && relative.getName(0).toString=="archive-assets" && name.matches("(?:transfer|decoded)-[a-zA-Z0-9_-]+[.]part")) ||
        (relative.getNameCount>=3 && relative.getName(0).toString=="unifications" && relative.getName(1).toString.matches(uuid) && (
          (relative.getNameCount==3 && (name=="request.json" || name.matches(s"dataset[.]npz[.]$uuid[.]part"))) ||
          (relative.getNameCount==4 && relative.getName(2).toString=="inputs" && name.matches("[0-9]{3}[.]fits")) ||
          (relative.getNameCount==4 && relative.getName(2).toString=="output" && name.matches("(?:dataset[.]npz|manifest[.]json)(?:[.]partial)?"))))
      if partial then
        if Files.isSymbolicLink(path) || !Files.isRegularFile(path,java.nio.file.LinkOption.NOFOLLOW_LINKS) then
          throw ApiError("invalid_product","Unsafe abandoned cache partial file")
        Files.deleteIfExists(path)
    }
    finally paths.close()
  }
  def open(root:Path,database:Path,maxCacheBytes:Long,maxProductBytes:Long,minFreeBytes:Long):Task[FileCache]=
    for
      _ <- ZIO.fail(ApiError("invalid_configuration","Cache limits must be positive and fit one product"))
        .when(maxProductBytes<=0 || maxCacheBytes<maxProductBytes || minFreeBytes<0)
      _ <- ZIO.attemptBlocking { Files.createDirectories(root); Files.createDirectories(database.toAbsolutePath.getParent) }
      store=new FileCacheRepository(database)
      _ <- ZIO.attemptBlocking(store.initialize())
      gate <- Semaphore.make(1)
      state <- Ref.make(State(Map.empty,Map.empty,0L))
      locks <- ZIO.foreach(1 to 64)(_=>Semaphore.make(1))
      cache=new FileCache(root.toAbsolutePath.normalize(),store,maxCacheBytes,maxProductBytes,minFreeBytes,gate,state,locks.toVector)
      _ <- cache.reconcile
    yield cache
