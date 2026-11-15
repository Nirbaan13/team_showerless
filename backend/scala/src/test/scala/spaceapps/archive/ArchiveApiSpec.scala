package spaceapps.archive
import spaceapps.domain.*
import spaceapps.archive.domain.*
import spaceapps.service.*
import spaceapps.archive.service.*
import spaceapps.archive.repository.ArchiveRepository
import spaceapps.archive.bootstrap.ArchiveRuntime
import spaceapps.archive.integrations.ArchiveProvider
import spaceapps.archive.integrations.protocol.*
import spaceapps.archive.controller.ArchiveApi
import zio.*
import zio.http.*
import zio.json.*
import zio.test.*
import java.nio.file.Files
object ArchiveApiSpec extends ZIOSpecDefault:
  def withRuntime[A](use: ArchiveRuntime=>ZIO[Client & Scope,Throwable,A]): ZIO[Client,Throwable,A]=ZIO.scoped { for
    dir <- ZIO.attempt(Files.createTempDirectory("archive-api-"))
    repo <- ArchiveRepository.open(dir.resolve("jobs.sqlite"))
    provider=FederatedArchiveSpec.provider("eso",ZIO.succeed(ProviderPage(List(ArchiveRecord.create("eso","VISTA","one",ProductKind.image)),Completeness.truncated)))
    registry=new ProviderRegistry(List(provider))
    discovery <- FederatedDiscovery.make(registry,repo)
    client <- ZIO.service[Client]
    downloads <- ArchiveDownloads.make(registry,repo,new StreamingDownloader(new ArchiveTransport(client),dir.resolve("assets")))
    result <- use(ArchiveRuntime(registry,repo,discovery,downloads))
  yield result
  }
  def spec=suite("archive HTTP API")(
    test("202 search status URL, persisted records and inventory expose additive contract") {
      withRuntime { runtime=>
        val api=new ArchiveApi(runtime.service)
        for
          inventory <- api.routes.runZIO(Request.get("http://localhost/api/archives"))
          post <- api.routes.runZIO(Request.post("http://localhost/api/archive-searches",Body.fromString(ArchiveQuery(Circle(1,2,0.1),List("eso")).toJson)))
          body <- post.body.asString
          accepted <- ZIO.fromEither(body.fromJson[AcceptedJob]).mapError(new RuntimeException(_))
          _ <- runtime.discovery.execute(accepted.id)
          result <- api.routes.runZIO(Request.get("http://localhost"+accepted.status_url+"?limit=1"))
          text <- result.body.asString
        yield assertTrue(post.status==Status.Accepted,accepted.status_url==s"/api/archive-searches/${accepted.id}",inventory.status==Status.Ok,text.contains("truncated"),text.contains("analysisEligible"))
      }
    },
    test("unknown providers, arbitrary upstream URLs and unknown record IDs are rejected") {
      withRuntime { runtime=>
        val api=new ArchiveApi(runtime.service)
        for
          unknown <- api.routes.runZIO(Request.post("http://localhost/api/archive-searches",Body.fromString(ArchiveQuery(Circle(1,2,0.1),List("unknown")).toJson)))
          url <- api.routes.runZIO(Request.post("http://localhost/api/archive-downloads",Body.fromString("{\"record_ids\":[\"https://evil.test/file\"],\"url\":\"https://evil.test/file\"}")))
          missing <- api.routes.runZIO(Request.post("http://localhost/api/archive-downloads",Body.fromString(DownloadSelection(List("missing")).toJson)))
          cursor <- api.routes.runZIO(Request.get("http://localhost/api/archive-searches/missing?limit=201"))
        yield assertTrue(unknown.status==Status.UnprocessableEntity,url.status==Status.UnprocessableEntity,missing.status==Status.NotFound,cursor.status==Status.NotFound)
      }
    },
    test("foreign image download stores native bytes, serves only known assets and survives reopen") {
      ArchiveTransferSpec.server(ArchiveTransferSpec.fits) { (base,policy)=>for
        dir <- ZIO.attempt(Files.createTempDirectory("archive-native-"))
        repo <- ArchiveRepository.open(dir.resolve("state.sqlite"))
        client <- ZIO.service[Client]
        record=ArchiveRecord.create("eso","VISTA","native",ProductKind.image).copy(provenance=Map("archive"->"ESO"))
        _ <- repo.saveSearch(SearchSnapshot("search",ArchiveQuery(Circle(1,2,0.1),List("eso")),records=List(record)))
        source=new ArchiveProvider:
          val id="eso"
          override def origins=policy
          def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image),original=true))
          def search(q: ArchiveQuery,c: Option[ProviderCursor])=ZIO.succeed(ProviderPage(Nil,Completeness.complete))
          def resolve(r: ArchiveRecord,d: DeliveryRequest)=ZIO.succeed(List(ArchiveAsset(ArchiveAssetKey.key(r,d),id,base+"/native")))
        registry=new ProviderRegistry(List(source))
        downloads <- ArchiveDownloads.make(registry,repo,new StreamingDownloader(new ArchiveTransport(client),dir.resolve("assets")))
        job <- downloads.accept(DownloadSelection(List(record.id)))
        _ <- downloads.execute(job.id)
        reopened <- ArchiveRepository.open(dir.resolve("state.sqlite"))
        result <- reopened.download(job.id)
        artifact <- downloads.artifact(result.assets.head.asset.get.id)
        unknown <- downloads.artifact("0"*64).either
      yield assertTrue(result.status=="completed",!result.assets.head.asset.get.analysisEligible,result.assets.head.provenance("archive")=="ESO",Files.size(artifact._1)==2880,unknown.isLeft) }
    },
    test("failed foreign delivery persists provenance without invoking SPHEREx processing") {
      withRuntime { runtime=>
        for
          search <- runtime.discovery.accept(ArchiveQuery(Circle(1,2,0.1),List("eso")))
          _ <- runtime.discovery.execute(search.id)
          page <- runtime.repository.page(search.id,None,50)
          job <- runtime.downloads.accept(DownloadSelection(List(page.records.head.id)))
          _ <- runtime.downloads.execute(job.id)
          result <- runtime.repository.download(job.id)
        yield assertTrue(result.status=="failed",result.assets.head.error.exists(_.code=="unsupported_delivery"),result.assets.head.asset.isEmpty)
      }
    },
    test("admission stays responsive while an existing native transfer is running") {
      for
        dir <- ZIO.attempt(Files.createTempDirectory("archive-admission-"))
        repo <- ArchiveRepository.open(dir.resolve("state.sqlite"))
        client <- ZIO.service[Client]
        entered <- Promise.make[Nothing,Unit]
        record=ArchiveRecord.create("slow","native","one",ProductKind.image)
        _ <- repo.saveSearch(SearchSnapshot("search",ArchiveQuery(Circle(1,2,0.1),List("slow")),records=List(record)))
        source=new ArchiveProvider:
          val id="slow"
          def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image),original=true))
          def search(q: ArchiveQuery,c: Option[ProviderCursor])=ZIO.succeed(ProviderPage(Nil,Completeness.complete))
          def resolve(r: ArchiveRecord,d: DeliveryRequest)=entered.succeed(()) *> ZIO.never
        downloads <- ArchiveDownloads.make(new ProviderRegistry(List(source)),repo,new StreamingDownloader(new ArchiveTransport(client),dir.resolve("assets")))
        first <- downloads.accept(DownloadSelection(List(record.id)))
        running <- downloads.execute(first.id).fork
        _ <- entered.await
        next <- downloads.accept(DownloadSelection(List(record.id))).timeout(150.millis)
        _ <- running.interrupt
      yield assertTrue(next.nonEmpty)
    },
    test("a resolver defect is persisted as a sanitized per-record failure") {
      withRuntime { runtime=>for
        client <- ZIO.service[Client]
        dir <- ZIO.attempt(Files.createTempDirectory("archive-resolver-defect-"))
        record=ArchiveRecord.create("broken","native","one",ProductKind.image)
        _ <- runtime.repository.saveSearch(SearchSnapshot("search",ArchiveQuery(Circle(1,2,0.1),List("broken")),records=List(record)))
        source=new ArchiveProvider:
          val id="broken"
          def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image),original=true))
          def search(q: ArchiveQuery,c: Option[ProviderCursor])=ZIO.succeed(ProviderPage(Nil,Completeness.complete))
          def resolve(r: ArchiveRecord,d: DeliveryRequest)=ZIO.die(new IllegalStateException("private grant URL"))
        downloads <- ArchiveDownloads.make(new ProviderRegistry(List(source)),runtime.repository,new StreamingDownloader(new ArchiveTransport(client),dir))
        accepted <- downloads.accept(DownloadSelection(List(record.id)))
        _ <- downloads.execute(accepted.id).exit
        result <- runtime.repository.download(accepted.id)
      yield assertTrue(result.status=="failed",result.assets.headOption.flatMap(_.error).exists(e=>e.code=="provider_error" && !e.message.contains("private"))) }
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock
