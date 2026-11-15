package spaceapps.downloads

import spaceapps.downloads.model.*
import spaceapps.downloads.service.*
import spaceapps.downloads.repository.DownloadsRepository
import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.integrations.protocol.*
import spaceapps.downloads.controller.DownloadsApi
import spaceapps.infra.service.FileCache
import zio.*
import zio.http.*
import zio.json.*
import zio.test.*
import java.nio.file.{Files,Path}
import java.util.concurrent.atomic.AtomicInteger

object DownloadPipelineSpec extends ZIOSpecDefault:
  private case class Fixture(root:Path,repo:DownloadsRepository,record:ArchiveRecord,registry:ProviderRegistry,
    discovery:FederatedDiscovery,downloader:StreamingDownloader,jobs:DownloadJobs,cache:FileCache,hits:AtomicInteger):
    def api=new DownloadsApi(new DownloadsService(registry,repo,discovery,jobs))
    def selection=DownloadSelection(List(record.id))
    def key=ArchiveAssetKey.key(record,selection.delivery)
  private def fixture[A](use:Fixture=>ZIO[Client & Scope,Throwable,A],failures:Int=0):ZIO[Client,Throwable,A]=
    val hits=new AtomicInteger()
    ArchiveTransferSpec.server(ArchiveTransferSpec.fits,hits=hits,transientFailures=failures) { (base,policy)=>ZIO.scoped { for
      dir <- ZIO.attempt(Files.createTempDirectory("download-pipeline-"))
      repo <- DownloadsRepository.open(dir.resolve("jobs.sqlite"))
      client <- ZIO.service[Client]
      record=ArchiveRecord.create("eso","native","one",ProductKind.image)
      _ <- repo.saveSearch(SearchSnapshot("search",ArchiveQuery(Circle(1,2,0.1),List("eso")),records=List(record)))
      provider=new ArchiveProvider:
        val id="eso"
        override def origins=policy
        def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image),original=true))
        def search(q:ArchiveQuery,c:Option[ProviderCursor])=ZIO.succeed(ProviderPage(Nil,Completeness.complete))
        def resolve(r:ArchiveRecord,d:DeliveryRequest)=ZIO.succeed(List(ArchiveAsset(ArchiveAssetKey.key(r,d),id,base)))
      registry=new ProviderRegistry(List(provider))
      discovery <- FederatedDiscovery.make(registry,repo)
      cache <- FileCache.open(dir,dir.resolve("jobs.sqlite"),2880,2880,0)
      downloader=new StreamingDownloader(new ArchiveTransport(client),dir.resolve("archive-assets"),2880,Some(cache))
      jobs <- DownloadJobs.make(registry,repo,downloader)
      result <- use(Fixture(dir,repo,record,registry,discovery,downloader,jobs,cache,hits))
    yield result } }
  private def request(api:DownloadsApi,path:String)=api.routes.runZIO(Request.get("http://localhost"+path))
  private def write(path:Path)=ZIO.attemptBlocking {Files.write(path,ArchiveTransferSpec.fits);()}
  def spec=suite("download pipeline")(
    test("acceptance exposes pending artifact links before downloading") {
      fixture { f=>for
        job <- f.jobs.accept(f.selection)
        status <- request(f.api,job.status_url)
        text <- status.body.asString
        asset <- request(f.api,s"/api/archive-assets/${f.key}")
      yield assertTrue(status.status==Status.Ok,text.contains("pending"),text.contains("events_url"),text.contains("artifact_url"),asset.status==Status.Accepted,f.hits.get==0) }
    },
    test("SSE survives repository reopen, replays after Last-Event-ID and closes on completion") {
      fixture { f=>for
        job <- f.jobs.accept(f.selection)
        _ <- f.jobs.execute(job.id)
        repo <- DownloadsRepository.open(f.root.resolve("jobs.sqlite"))
        jobs <- DownloadJobs.make(f.registry,repo,f.downloader)
        api=new DownloadsApi(new DownloadsService(f.registry,repo,f.discovery,jobs))
        response <- request(api,job.status_url+"/events")
        first <- response.body.asString
        replay <- api.routes.runZIO(Request.get("http://localhost"+job.status_url+"/events").addHeader("Last-Event-ID","1"))
        text <- replay.body.asString
        missing <- request(api,"/api/archive-downloads/missing/events")
        invalid <- ZIO.foreach(List("bad","-1","999999"))(value=>api.routes.runZIO(Request.get("http://localhost"+job.status_url+"/events").addHeader("Last-Event-ID",value)))
      yield assertTrue(response.status==Status.Ok,response.headers.get("Content-Type").contains("text/event-stream"),first.contains("event: job.completed"),text.contains("event: chunk.ready"),text.contains("event: job.completed"),!text.contains("id: 1\n"),missing.status==Status.NotFound,invalid.forall(_.status==Status.UnprocessableEntity)) }
    },
    test("a long replay never replaces unread chunk events with a terminal snapshot") {
      fixture { f=>for
        job <- f.jobs.accept(f.selection)
        _ <- ZIO.foreachDiscard(1 to 300)(_=>f.repo.updateDownload(job.id)(identity))
        _ <- f.jobs.execute(job.id)
        response <- f.api.routes.runZIO(Request.get("http://localhost"+job.status_url+"/events").addHeader("Last-Event-ID","0"))
        text <- response.body.asString
      yield assertTrue(text.contains("event: chunk.ready"),text.contains("event: job.completed"),text.split("id: ").length>300) }
    },
    test("a stream opened before execution receives committed updates and terminates") {
      fixture { f=>for
        job <- f.jobs.accept(f.selection)
        response <- request(f.api,job.status_url+"/events")
        reader <- response.body.asString.forkScoped
        _ <- f.jobs.execute(job.id)
        text <- reader.join
      yield assertTrue(text.contains("event: chunk.started"),text.contains("event: chunk.ready"),text.endsWith("\n\n"),text.contains("event: job.completed")) }
    },
    test("global eviction changes the manifest and a new download restores the product") {
      fixture { f=>for
        first <- f.jobs.accept(f.selection)
        _ <- f.jobs.execute(first.id)
        _ <- f.cache.publish(f.root.resolve("calibration-cache").resolve("a"*64))(write)
        missing <- request(f.api,first.status_url)
        text <- missing.body.asString
        next <- f.jobs.accept(f.selection)
        _ <- f.jobs.execute(next.id)
        restored <- f.jobs.status(next.id)
        disk <- ZIO.attempt(Files.exists(f.root.resolve("archive-assets").resolve(f.key)))
      yield assertTrue(text.contains("cache_missing"),restored.status=="completed",disk,f.hits.get==2) }
    },
    test("concurrent jobs selecting the same product perform one upstream transfer") {
      fixture { f=>for
        accepted <- ZIO.foreach(1 to 8)(_=>f.jobs.accept(f.selection))
        _ <- ZIO.foreachParDiscard(accepted)(j=>f.jobs.execute(j.id))
        completed <- ZIO.foreach(accepted)(j=>f.jobs.status(j.id))
      yield assertTrue(completed.forall(j=>j.status=="completed" && j.assets.size==1),f.hits.get==1) }
    },
    test("interrupted work resumes from persistent state with unique outcomes") {
      fixture { f=>for
        entered <- Promise.make[Nothing,Unit]
        original=f.registry.providers.head
        slow=new ArchiveProvider:
          val id="eso"
          override def origins=original.origins
          def capabilities=original.capabilities
          def search(q:ArchiveQuery,c:Option[ProviderCursor])=original.search(q,c)
          def resolve(r:ArchiveRecord,d:DeliveryRequest)=entered.succeed(()) *> ZIO.never
        stalled <- DownloadJobs.make(new ProviderRegistry(List(slow)),f.repo,f.downloader)
        job <- stalled.accept(f.selection)
        running <- stalled.execute(job.id).forkScoped
        _ <- entered.await
        _ <- running.interrupt
        reopened <- DownloadsRepository.open(f.root.resolve("jobs.sqlite"))
        restarted <- DownloadJobs.make(f.registry,reopened,f.downloader)
        _ <- restarted.recover
        _ <- restarted.execute(job.id)
        done <- restarted.status(job.id)
        events <- reopened.eventsAfter(job.id,0)
      yield assertTrue(done.status=="completed",done.assets.size==1,done.progress.ready_chunks==1,events.map(_.sequence)==events.map(_.sequence).distinct.sorted,f.hits.get==1) }
    },
    test("a retryable archive failure releases scratch capacity before a bounded retry") {
      fixture(f=>for
        job <- f.jobs.accept(f.selection)
        _ <- f.jobs.execute(job.id)
        done <- f.jobs.status(job.id)
        entries <- ZIO.attempt {val stream=Files.list(f.root.resolve("archive-assets"));try stream.count() finally stream.close()}
      yield assertTrue(done.status=="completed",done.progress.ready_chunks==1,f.hits.get==2,entries==1),failures=1)
    },
    test("an HTTP artifact response retains its lease through headers and body consumption") {
      fixture { f=>for
        job <- f.jobs.accept(f.selection)
        _ <- f.jobs.execute(job.id)
        scope <- Scope.make
        response <- scope.extend(request(f.api,"/api/archive-assets/"+f.key))
        blocked <- f.cache.publish(f.root.resolve("calibration-cache").resolve("b"*64))(write).exit
        bytes <- response.body.asChunk
        _ <- scope.close(Exit.unit)
        released <- f.cache.publish(f.root.resolve("calibration-cache").resolve("b"*64))(write).exit
      yield assertTrue(response.status==Status.Ok,bytes.toArray.toList==ArchiveTransferSpec.fits.toList,blocked.isFailure,released.isSuccess) }
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock @@ TestAspect.timeout(30.seconds)
