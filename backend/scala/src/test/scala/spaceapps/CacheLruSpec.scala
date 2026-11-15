package spaceapps

import spaceapps.irsa.model.*
import spaceapps.infra.service.FileCache

import spaceapps.irsa.service.*
import spaceapps.irsa.repository.Repository
import spaceapps.infra.repository.FileCacheRepository
import spaceapps.infra.controller.Api
import zio.*
import zio.http.{Request,Status}
import zio.test.*
import java.nio.file.{Files,Path}
import java.nio.file.attribute.FileTime

object CacheLruSpec extends ZIOSpecDefault:
  private val image = ArchiveImage(Observation("one","2026-01-01T00:00:00Z",1,"DR1"),"https://example.test/one")
  private val query=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get
  private def write(path:Path,n:Int)=ZIO.attemptBlocking { Files.createDirectories(path.getParent); Files.write(path,Array.fill[Byte](n)(1)); () }
  private def native(dir:Path,key:Char)=dir.resolve("raw").resolve(key.toString*64+".fits")
  private def temp=ZIO.acquireRelease(ZIO.attempt(Files.createTempDirectory("fits-lru-")))(dir=>ZIO.attemptBlocking {
    val paths=Files.walk(dir)
    try paths.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally paths.close()
  }.orDie)
  private def cache(dir:Path,budget:Long=80,max:Long=40)=FileCache.open(dir,dir.resolve("jobs.sqlite"),budget,max,0)
  private val source=new Archive:
    def search(q:Query)=ZIO.succeed(List(image))
    def fetch(i:ArchiveImage,p:Path)=write(p,40)
  private def done(jobs:Jobs,id:String):Task[Download]=jobs.get(id).flatMap(d=>if d.terminal then ZIO.succeed(d) else ZIO.sleep(10.millis) *> done(jobs,id))
  private def fixture(dir:Path,budget:Long=80)=for
    repo <- Repository.open(dir.resolve("jobs.sqlite"))
    coordinator <- cache(dir,budget)
    archive <- CapacityArchive.make(source,dir,budget,40,0,Some(coordinator))
    jobs <- Jobs.make(repo,archive,NoProcessing,dir)
    accepted <- jobs.submit(query,"default",None)
    completed <- done(jobs,accepted.id)
  yield (coordinator,jobs,completed)
  def spec=suite("Native FITS LRU")(
    test("admission evicts owned FITS before transfer and preserves unrelated files") {
      ZIO.scoped { for
        dir <- temp
        first=native(dir,'a')
        second=native(dir,'b')
        other=dir.resolve("user.fits")
        _ <- write(first,40) *> write(second,40) *> write(other,10)
        _ <- ZIO.attempt(Files.setLastModifiedTime(first,FileTime.fromMillis(1)))
        archive <- CapacityArchive.make(source,dir,110,40,0)
        result <- archive.fetch(image,dir.resolve("new.part")).exit
        disk <- ZIO.attempt(List(first,second,other).map(Files.exists(_)))
      yield assertTrue(result.isSuccess,disk==List(false,true,true)) }
    },
    test("one LRU evicts archive, calibration and preview files in persisted access order") {
      ZIO.scoped { for
        dir <- temp
        c <- cache(dir,120)
        a=dir.resolve("archive-assets").resolve("a"*64)
        b=dir.resolve("calibration-cache").resolve("b"*64)
        preview=dir.resolve("jobs/job").resolve("c"*40+".png")
        d=native(dir,'d')
        _ <- c.publish(a)(write(_,40)) *> c.publish(b)(write(_,40)) *> c.publish(preview)(write(_,40))
        _ <- ZIO.scoped(c.cached(a))
        reopened <- cache(dir,120)
        _ <- reopened.publish(d)(write(_,40))
        first <- ZIO.attempt(List(a,b,preview,d).map(Files.exists(_)))
        _ <- reopened.publish(b)(write(_,40))
        second <- ZIO.attempt(List(a,b,preview,d).map(Files.exists(_)))
      yield assertTrue(first==List(true,false,true,true),second==List(true,true,false,true)) }
    },
    test("an active equipment reader survives global eviction and releases its lease") {
      ZIO.scoped { for
        dir <- temp
        c <- cache(dir,40)
        equipment=dir.resolve("calibration-cache").resolve("e"*64)
        next=native(dir,'f')
        _ <- c.publish(equipment)(write(_,40))
        entered <- Promise.make[Nothing,Unit]
        reader <- ZIO.scoped(c.cached(equipment) *> entered.succeed(()) *> ZIO.never).forkScoped
        _ <- entered.await
        blocked <- c.publish(next)(write(_,40)).exit
        _ <- reader.interrupt
        released <- c.publish(next)(write(_,40)).exit
        disk <- ZIO.attempt(!Files.exists(equipment) && Files.exists(next))
      yield assertTrue(blocked.isFailure,released.isSuccess,disk) }
    },
    test("reuse touches LRU order durably rather than evicting the first downloaded file") {
      ZIO.scoped { for
        dir <- temp
        c <- cache(dir)
        a=native(dir,'a'); b=native(dir,'b'); d=native(dir,'c')
        _ <- c.publish(a)(write(_,40)) *> c.publish(b)(write(_,40))
        hit <- ZIO.scoped(c.cached(a))
        reopened <- cache(dir)
        _ <- reopened.publish(d)(write(_,40))
        rows <- ZIO.attempt(new FileCacheRepository(dir.resolve("jobs.sqlite")).entries())
        disk <- ZIO.attempt(List(a,b,d).map(Files.exists(_)))
      yield assertTrue(hit.contains(a),disk==List(true,false,true),
        rows.map(_._2).toSet==Set(a,d),rows.forall(_._3==40),rows.last._2==d) }
    },
    test("an active reader cannot be evicted and interruption releases its lease") {
      ZIO.scoped { for
        dir <- temp
        c <- cache(dir)
        a=native(dir,'a'); b=native(dir,'b'); d=native(dir,'c'); e=native(dir,'d')
        _ <- c.publish(a)(write(_,40)) *> c.publish(b)(write(_,40))
        entered <- Promise.make[Nothing,Unit]
        reader <- ZIO.scoped(c.cached(a) *> entered.succeed(()) *> ZIO.never).forkScoped
        _ <- entered.await
        _ <- c.publish(d)(write(_,40))
        protectedNow <- ZIO.attempt(Files.exists(a) && !Files.exists(b))
        _ <- reader.interrupt
        _ <- c.publish(e)(write(_,40))
        disk <- ZIO.attempt(List(a,d,e).map(Files.exists(_)))
      yield assertTrue(protectedNow,disk==List(false,true,true)) }
    },
    test("concurrent partial downloads reserve once, stay unpublished and cannot over-admit") {
      ZIO.scoped { for
        dir <- temp
        c <- cache(dir)
        written <- Ref.make(0)
        both <- Promise.make[Nothing,Unit]
        finish <- Promise.make[Nothing,Unit]
        produce=(p:Path)=>write(p,20) *> written.updateAndGet(_+1).flatMap(n=>both.succeed(()).when(n==2)) *> finish.await *> write(p,40)
        a=native(dir,'a'); b=native(dir,'b'); d=native(dir,'c')
        first <- c.publish(a)(produce).forkScoped
        second <- c.publish(b)(produce).forkScoped
        _ <- both.await
        third <- c.publish(d)(write(_,40)).exit
        hidden <- ZIO.attempt(!Files.exists(a) && !Files.exists(b))
        _ <- finish.succeed(())
        _ <- first.join *> second.join
        disk <- ZIO.attempt((Files.size(a)+Files.size(b),Files.exists(d)))
      yield assertTrue(third.isFailure,hidden,disk==(80L,false)) }
    },
    test("failed publication releases its reservation and removes only its own partial") {
      ZIO.scoped { for
        dir <- temp
        c <- cache(dir,40)
        a=native(dir,'a'); b=native(dir,'b')
        failed <- c.publish(a)(p=>write(p,20) *> ZIO.fail(new RuntimeException("failed"))).exit
        _ <- c.publish(b)(write(_,40))
        raw <- ZIO.attempt { val s=Files.list(dir.resolve("raw")); try s.count() finally s.close() }
        disk <- ZIO.attempt(List(a,b).map(Files.exists(_)))
      yield assertTrue(failed.isFailure,disk==List(false,true),raw==1) }
    },
    test("startup reclaims every producer's crash partial before the shared cache admits work") {
      ZIO.scoped { for
        dir <- temp
        uuid="12345678-1234-1234-1234-123456789abc"
        partials=List(dir.resolve("raw").resolve("a"*64+s".fits.$uuid.part"),
          dir.resolve("jobs/job").resolve("b"*40+s".png.$uuid.part"),
          dir.resolve("calibration-cache").resolve("c"*64+s".$uuid.part"),
          dir.resolve("archive-assets/transfer-12345.part"),dir.resolve("archive-assets/decoded-67890.part"),
          dir.resolve(s"unifications/$uuid/inputs/000.fits"),dir.resolve(s"unifications/$uuid/output/dataset.npz"),
          dir.resolve(s"unifications/$uuid/output/manifest.json"),dir.resolve(s"unifications/$uuid/output/dataset.npz.partial"),
          dir.resolve(s"unifications/$uuid/output/manifest.json.partial"),dir.resolve(s"unifications/$uuid/request.json"),
          dir.resolve(s"unifications/$uuid/dataset.npz.$uuid.part"))
        _ <- ZIO.foreachDiscard(partials)(write(_,40))
        unrelated=dir.resolve("user.part")
        _ <- write(unrelated,1)
        _ <- FileCache.recover(dir)
        c <- cache(dir,41)
        _ <- c.publish(native(dir,'f'))(write(_,40))
        disk <- ZIO.attempt(partials.forall(p=> !Files.exists(p)) && Files.size(unrelated)==1 && Files.size(native(dir,'f'))==40)
      yield assertTrue(disk) }
    },
    test("restart reconciles missing indexed products and atomically published unindexed FITS") {
      ZIO.scoped { for
        dir <- temp
        c <- cache(dir)
        a=native(dir,'a'); b=native(dir,'b'); d=native(dir,'c')
        _ <- c.publish(a)(write(_,40))
        _ <- ZIO.attempt(Files.delete(a)) *> write(b,40)
        _ <- ZIO.attempt(Files.setLastModifiedTime(b,FileTime.fromMillis(1)))
        reopened <- cache(dir)
        rows <- ZIO.attempt(new FileCacheRepository(dir.resolve("jobs.sqlite")).entries())
        _ <- reopened.publish(d)(write(_,40))
        _ <- reopened.publish(a)(write(_,40))
        disk <- ZIO.attempt(List(b,a,d).map(Files.exists(_)))
      yield assertTrue(rows.map(_._2)==List(b),disk==List(false,true,true)) }
    },
    test("science processing protects its native input and unpublished output until it completes") {
      ZIO.scoped { for
        dir <- temp
        repo <- Repository.open(dir.resolve("jobs.sqlite"))
        c <- cache(dir)
        archive <- CapacityArchive.make(source,dir,80,40,0,Some(c))
        entered <- Promise.make[Nothing,Path]
        finish <- Promise.make[Nothing,Unit]
        processor=new Processor:
          override def supportsPreview=false
          def prepare(in:Path,out:Path,mode:String,ref:Option[Path],q:Query)=entered.succeed(in) *> finish.await *> write(out,40)
          def preview(in:Path,out:Path)=ZIO.unit
        jobs <- Jobs.make(repo,archive,processor,dir)
        accepted <- jobs.submit(query,"epoch",None)
        input <- entered.await
        blocked <- c.publish(native(dir,'f'))(write(_,40)).exit
        inputExists <- ZIO.attempt(Files.exists(input))
        _ <- finish.succeed(())
        completed <- done(jobs,accepted.id)
        released <- c.publish(native(dir,'f'))(write(_,40)).exit
      yield assertTrue(blocked.isFailure,inputExists,completed.status=="completed",released.isSuccess) }
    },
    test("evicted jobs become cache_missing and concurrent resubmission refetches one native product") {
      ZIO.scoped { for
        dir <- temp
        f <- fixture(dir,40)
        (c,jobs,first)=f
        _ <- c.publish(native(dir,'f'))(write(_,40))
        missing <- jobs.resource(first.chunks.head.id,false)
        retried <- ZIO.foreachPar(1 to 8)(_=>jobs.submit(query,"default",None))
        ready <- done(jobs,retried.head.id)
      yield assertTrue(missing match {case Resource.Failed(e)=>e.code=="cache_missing"; case _=>false},
        retried.map(_.id).distinct.size==1,retried.head.id!=first.id,ready.status=="completed",ready.progress.ready_chunks==1) }
    },
    test("HTTP response pins before headers and retains its file until the request scope closes") {
      ZIO.scoped { for
        dir <- temp
        f <- fixture(dir,40)
        (c,jobs,first)=f
        api <- Api.make(jobs,"test",Path.of("docs/openapi.yaml"))
        scope <- Scope.make
        response <- scope.extend(api.routes.runZIO(Request.get(s"http://localhost/api/chunks/${first.chunks.head.id}")))
        whileOpen <- c.publish(native(dir,'f'))(write(_,40)).exit
        bytes <- response.body.asChunk
        _ <- scope.close(Exit.unit)
        afterClose <- c.publish(native(dir,'f'))(write(_,40)).exit
      yield assertTrue(response.status==Status.Ok,whileOpen.isFailure,bytes.size==40,afterClose.isSuccess) }
    },
    test("a slow gRPC byte reader holds its FITS lease and disconnect releases admission") {
      ZIO.scoped { for
        dir <- temp
        size=16*1024*1024
        repo <- Repository.open(dir.resolve("jobs.sqlite"))
        c <- cache(dir,size,size)
        large=new Archive:
          def search(q:Query)=ZIO.succeed(List(image))
          def fetch(i:ArchiveImage,p:Path)=write(p,size)
        archive <- CapacityArchive.make(large,dir,size,size,0,Some(c))
        jobs <- Jobs.make(repo,archive,NoProcessing,dir)
        accepted <- jobs.submit(query,"default",None)
        first <- done(jobs,accepted.id)
        port <- spaceapps.irsa.integrations.grpc.GrpcServer.start(jobs,"test","127.0.0.1",0)
        client <- spaceapps.integrations.grpc.v1.ZioRetrieval.RetrievalServiceClient.scoped(
          scalapb.zio_grpc.ZManagedChannel(io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder.forAddress("127.0.0.1",port).usePlaintext()))
        started <- Promise.make[Nothing,Unit]
        reader <- client.getChunk(spaceapps.integrations.grpc.v1.ChunkRequest(first.chunks.head.id))
          .tap(_=>started.succeed(()) *> ZIO.never).runDrain.forkScoped
        _ <- started.await
        blocked <- c.publish(native(dir,'f'))(write(_,size)).exit
        _ <- reader.interrupt
        released <- c.publish(native(dir,'f'))(write(_,size)).retry(Schedule.spaced(20.millis) && Schedule.recurs(100)).exit
      yield assertTrue(blocked.isFailure,released.isSuccess) }
    },
    test("discarding an unconsumed HTTP response releases its cache lease on request cancellation") {
      ZIO.scoped { for
        dir <- temp
        f <- fixture(dir,40)
        (c,jobs,first)=f
        api <- Api.make(jobs,"test",Path.of("docs/openapi.yaml"))
        ready <- Promise.make[Nothing,Unit]
        request <- ZIO.scoped(api.routes.runZIO(Request.get(s"http://localhost/api/chunks/${first.chunks.head.id}")) *> ready.succeed(()) *> ZIO.never).forkScoped
        _ <- ready.await
        blocked <- c.publish(native(dir,'f'))(write(_,40)).exit
        _ <- request.interrupt
        released <- c.publish(native(dir,'f'))(write(_,40)).exit
      yield assertTrue(blocked.isFailure,released.isSuccess) }
    }
  ) @@ TestAspect.withLiveClock @@ TestAspect.timeout(30.seconds)
