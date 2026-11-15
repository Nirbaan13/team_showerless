package spaceapps.downloads
import spaceapps.irsa.model.*
import spaceapps.downloads.model.*

import spaceapps.irsa.service.*
import spaceapps.downloads.service.*
import spaceapps.downloads.repository.DownloadsRepository
import spaceapps.downloads.bootstrap.DownloadsRuntime
import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.integrations.providers.PendingProvider
import spaceapps.downloads.integrations.providers.GaiaProvider
import spaceapps.downloads.integrations.protocol.ArchiveTransport
import zio.*
import zio.http.Client
import zio.test.*
import java.nio.file.Files
object FederatedArchiveSpec extends ZIOSpecDefault:
  def provider(name: String,page: IO[ArchiveFailure,ProviderPage],mode: TimeFilterMode = TimeFilterMode.exact_utc)=new ArchiveProvider:
    val id=name
    def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image,ProductKind.coverage),mode))
    def search(q: ArchiveQuery,c: Option[ProviderCursor])=page
    def resolve(r: ArchiveRecord,d: DeliveryRequest)=ZIO.fail(ArchiveFailure("unsupported_delivery","No file"))
  def setup(providers: List[ArchiveProvider],limits: ArchiveLimits = ArchiveLimits())=for
    dir <- ZIO.attempt(Files.createTempDirectory("federated-"))
    repo <- DownloadsRepository.open(dir.resolve("state.sqlite"))
    service <- FederatedDiscovery.make(new ProviderRegistry(providers),repo,limits)
  yield (repo,service)
  def spec=suite("federated archive jobs")(
    test("independent failure retains ESO image and ART-XC coverage with honest completeness") {
      val image=ArchiveRecord.create("eso","VISTA","frame",ProductKind.image)
      val coverage=ArchiveRecord.create("iki-artxc","indexed","interval",ProductKind.coverage)
      for
        pair <- setup(List(provider("eso",ZIO.succeed(ProviderPage(List(image),Completeness.truncated))),new PendingProvider(PendingProvider.inventory.find(_.id=="esasky").get),provider("iki-artxc",ZIO.succeed(ProviderPage(List(coverage),Completeness.indexed_subset)))))
        (repo,service)=pair
        accepted <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("eso","esasky","iki-artxc"),List(ProductKind.image,ProductKind.coverage)))
        _ <- service.execute(accepted.id)
        job <- repo.search(accepted.id)
        result <- repo.page(accepted.id,None,1)
      yield assertTrue(job.status=="partial",job.records.size==2,job.outcomes.find(_.provider=="esasky").exists(_.status=="unavailable"),result.next_cursor.nonEmpty,result.outcomes.find(_.provider=="eso").exists(_.completeness==Completeness.truncated))
    },
    test("all failed differs from a valid empty search; unsupported UTC is scoped per provider") {
      for
        pair <- setup(List(provider("bad",ZIO.fail(ArchiveFailure("unavailable","maintenance"))),provider("empty",ZIO.succeed(ProviderPage(Nil,Completeness.complete))),provider("native",ZIO.succeed(ProviderPage(Nil,Completeness.indexed_subset)),TimeFilterMode.provisional)))
        (repo,service)=pair
        failed <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("bad")))
        _ <- service.execute(failed.id)
        a <- repo.search(failed.id)
        empty <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("empty")))
        _ <- service.execute(empty.id)
        b <- repo.search(empty.id)
        mixed <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("empty","native"),time_start_utc=Some("2020-01-01T00:00:00Z")))
        _ <- service.execute(mixed.id)
        c <- repo.search(mixed.id)
      yield assertTrue(a.status=="failed",b.status=="completed",b.outcomes.head.status=="empty",c.status=="partial",c.outcomes.find(_.provider=="native").flatMap(_.error).exists(_.code=="unsupported_filter"))
    },
    test("an unexpected provider defect becomes an independent failure and terminates its job") {
      for
        pair <- setup(List(provider("broken",ZIO.die(new IllegalArgumentException("private upstream URL"))),provider("empty",ZIO.succeed(ProviderPage(Nil,Completeness.complete)))))
        (repo,service)=pair
        accepted <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("broken","empty")))
        _ <- service.execute(accepted.id).exit
        job <- repo.search(accepted.id)
      yield assertTrue(job.status=="partial",job.outcomes.find(_.provider=="broken").flatMap(_.error).exists(e=>e.code=="provider_error" && !e.message.contains("private")))
    },
    test("malformed HTTP 200 Gaia rows fail only Gaia while another archive completes") {
      val xml="<VOTABLE><RESOURCE><INFO name='QUERY_STATUS' value='OK'/><TABLE><FIELD name='ra'/><DATA><TABLEDATA><TR><TD>1.0</TD></TR></TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>".getBytes(java.nio.charset.StandardCharsets.UTF_8)
      ArchiveTransferSpec.server(xml) { (base,policy)=>for
        client <- ZIO.service[Client]
        pair <- setup(List(new GaiaProvider(new ArchiveTransport(client),base,policy),provider("empty",ZIO.succeed(ProviderPage(Nil,Completeness.complete)))))
        (repo,service)=pair
        accepted <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("esa-gaia","empty"),List(ProductKind.image,ProductKind.catalog_source)))
        _ <- service.execute(accepted.id)
        job <- repo.search(accepted.id)
      yield assertTrue(job.status=="partial",job.outcomes.find(_.provider=="esa-gaia").flatMap(_.error).exists(_.code=="invalid_response"),job.outcomes.find(_.provider=="empty").exists(_.status=="empty")) }.provide(Client.default)
    },
    test("upstream truncation has no invented continuation; genuine continuation deduplicates records and invalidates old local cursor") {
      val r=ArchiveRecord.create("paged","c","one",ProductKind.image)
      val r2=ArchiveRecord.create("paged","c","two",ProductKind.image)
      val p=new ArchiveProvider:
        val id="paged"
        def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image),TimeFilterMode.exact_utc))
        def search(q: ArchiveQuery,c: Option[ProviderCursor])=ZIO.succeed(if c.isEmpty then ProviderPage(List(r,r2),Completeness.truncated,Some(ProviderCursor("next"))) else ProviderPage(List(r2),Completeness.complete))
        def resolve(r: ArchiveRecord,d: DeliveryRequest)=ZIO.succeed(Nil)
      for
        pair <- setup(List(p))
        (repo,service)=pair
        job <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("paged")))
        _ <- service.execute(job.id)
        page <- repo.page(job.id,None,1)
        _ <- service.continue(job.id,"paged")
        _ <- service.execute(job.id)
        complete <- repo.search(job.id)
        stale <- repo.page(job.id,page.next_cursor,1).either
        exhausted <- service.continue(job.id,"paged").either
      yield assertTrue(complete.records.size==2,complete.outcomes.head.record_count==2,complete.outcomes.head.completeness==Completeness.complete,stale.isLeft,exhausted.left.toOption.exists(_.code=="unsupported_continuation"))
    },
    test("transient retries stop after two and permanent failures are not retried") {
      for
        transient <- Ref.make(0)
        permanent <- Ref.make(0)
        pair <- setup(List(provider("transient",transient.update(_+1) *> ZIO.fail(ArchiveFailure("http_error","503",true))),provider("permanent",permanent.update(_+1) *> ZIO.fail(ArchiveFailure("no_content","No subset")))))
        (repo,service)=pair
        job <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("transient","permanent")))
        _ <- service.execute(job.id)
        retries <- transient.get
        once <- permanent.get
      yield assertTrue(retries==3,once==1)
    },
    test("genuine continuations honor the same bounded admission queue") {
      val source=provider("paged",ZIO.succeed(ProviderPage(Nil,Completeness.truncated,Some(ProviderCursor("real-next")))))
      for
        pair <- setup(List(source),ArchiveLimits(max_active_jobs=1))
        (repo,service)=pair
        first <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("paged")))
        _ <- service.execute(first.id)
        queued <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("paged")))
        continuation <- service.continue(first.id,"paged").either
        previous <- repo.search(first.id)
      yield assertTrue(continuation.left.toOption.exists(_.code=="capacity_exceeded"),previous.status=="completed")
    },
    test("global and per-provider concurrency budgets apply across concurrent jobs") {
      for
        active <- Ref.make(0)
        maximum <- Ref.make(0)
        counts <- Ref.make(Map.empty[String,Int])
        violation <- Ref.make(false)
        providers=List("a","b","c","d").map { name=>
          provider(name,ZIO.acquireReleaseWith(active.updateAndGet(_+1).flatMap(n=>maximum.update(_.max(n))) *> counts.modify { m=> val next=m.getOrElse(name,0)+1;(next,m.updated(name,next)) }.flatMap(n=>violation.update(_ || n>1)))(_=>active.update(_-1) *> counts.update(m=>m.updated(name,m(name)-1)))(_=>ZIO.sleep(5.millis).as(ProviderPage(Nil,Completeness.complete))))
        }
        pair <- setup(providers)
        (_,service)=pair
        jobs <- ZIO.foreach(1 to 3)(_=>service.accept(ArchiveQuery(Circle(0,0,0.1),List("a","b","c","d"))))
        _ <- ZIO.foreachParDiscard(jobs)(j=>service.execute(j.id))
        max <- maximum.get
        invalid <- violation.get
      yield assertTrue(max<=3,max>=2,!invalid)
    },
    test("running searches recover from SQLite without losing completed provider outcomes") {
      for
        pair <- setup(List(provider("empty",ZIO.succeed(ProviderPage(Nil,Completeness.complete)))))
        (repo,service)=pair
        accepted <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("empty")))
        _ <- repo.updateSearch(accepted.id)(_.copy(status="running"))
        _ <- service.recover
        recovered <- repo.search(accepted.id)
        _ <- service.execute(accepted.id)
        complete <- repo.search(accepted.id)
      yield assertTrue(recovered.status=="queued",complete.status=="completed")
    },
    test("timeout stops a stalled provider while preserving an independently completed provider") {
      for
        pair <- setup(List(provider("slow",ZIO.never),provider("empty",ZIO.succeed(ProviderPage(Nil,Completeness.complete)))),ArchiveLimits(request_timeout_ms=20,search_deadline_ms=80,max_retries=0))
        (repo,service)=pair
        job <- service.accept(ArchiveQuery(Circle(0,0,0.1),List("slow","empty")))
        _ <- service.execute(job.id)
        result <- repo.search(job.id)
      yield assertTrue(result.status=="partial",result.outcomes.find(_.provider=="slow").flatMap(_.error).exists(_.code=="timeout"))
    }
  ) @@ TestAspect.withLiveClock
