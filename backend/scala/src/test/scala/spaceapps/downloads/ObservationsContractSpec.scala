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
import zio.json.ast.Json
import zio.test.*
import java.nio.file.Files
import java.util.concurrent.atomic.AtomicInteger

object ObservationsContractSpec extends ZIOSpecDefault:
  private case class Fixture(api:DownloadsApi,downloads:DownloadJobs,repo:DownloadsRepository,records:List[ArchiveRecord],searches:AtomicInteger,transfers:AtomicInteger)
  private def fixture[A](use:Fixture=>ZIO[Scope,Throwable,A]):ZIO[Client,Throwable,A]=
    val transfers=new AtomicInteger()
    ArchiveTransferSpec.server(ArchiveTransferSpec.fits,hits=transfers) { (base,policy)=>ZIO.scoped { for
      root <- ZIO.attempt(Files.createTempDirectory("observations-contract-"))
      repo <- DownloadsRepository.open(root.resolve("jobs.sqlite"))
      client <- ZIO.service[Client]
      searches=new AtomicInteger()
      records=List("first","second").map(id=>ArchiveRecord.create("eso","VISTA",id,ProductKind.image))
      _ <- repo.saveSearch(SearchSnapshot("seed",ArchiveQuery(Circle(1,2,0.1),List("eso")),status="completed",records=records))
      provider=new ArchiveProvider:
        val id="eso"
        override def origins=policy
        def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image),TimeFilterMode.exact_utc,original=true))
        def search(q:ArchiveQuery,c:Option[ProviderCursor])=ZIO.succeed {searches.incrementAndGet();ProviderPage(records,Completeness.complete)}
        def resolve(r:ArchiveRecord,d:DeliveryRequest)=ZIO.succeed(List(ArchiveAsset(ArchiveAssetKey.key(r,d),id,base)))
      registry=new ProviderRegistry(List(provider))
      discovery <- FederatedDiscovery.make(registry,repo)
      _ <- discovery.start
      cache <- FileCache.open(root,root.resolve("jobs.sqlite"),5760,2880,0)
      downloads <- DownloadJobs.make(registry,repo,new StreamingDownloader(new ArchiveTransport(client),root.resolve("archive-assets"),2880,Some(cache)))
      api=new DownloadsApi(new DownloadsService(registry,repo,discovery,downloads))
      result <- use(Fixture(api,downloads,repo,records,searches,transfers))
    yield result } }
  private def decode(response:Response):Task[Json]=response.body.asString.map(text=>text.fromJson[Json].getOrElse(Json.Null))
  private def field(value:Json,name:String):Option[Json]=value.asObject.flatMap(_.get(name))
  private def list(value:Json,name:String)=field(value,name).flatMap(_.asArray).toList.flatten.toList
  def spec=suite("common observations contract")(
    test("common aliases do not invent a data release or verified UTC time") {
      val record=ArchiveRecord.create("eso","VISTA","native",ProductKind.image,Some("product-version")).copy(time=ObservationTime(Some("2026-01-01T00:00:00Z"),quality=TimeQuality.native))
      val value=ObservationsContract.observation(record)
      assertTrue(field(value,"release").isEmpty,field(value,"observation_date").isEmpty,field(value,"detector_array").isEmpty,field(value,"channel_index").isEmpty,field(value,"id")==field(value,"frame_id"),field(value,"version").contains(Json.Str("product-version")))
    },
    test("GET search returns a list of stable IDs and metadata without downloading") {
      fixture { f=>for
        response <- f.api.routes.runZIO(Request.get("http://localhost/api/observations-search?right_ascension_deg=1&declination_deg=2&radius_degrees=0.1&providers=eso"))
        body <- decode(response)
        observations=list(body,"observations")
        downloads <- f.repo.allDownloads
      yield assertTrue(response.status==Status.Ok,observations.flatMap(field(_,"id").flatMap(_.asString)).toSet==f.records.map(_.id).toSet,
        observations.forall(o=>field(o,"frame_id")==field(o,"id")),field(body,"status_url").isEmpty,f.searches.get==1,f.transfers.get==0,downloads.isEmpty) }
    },
    test("POST downloads only client-selected IDs, returns a full common manifest and never searches") {
      fixture { f=>for
        response <- f.api.routes.runZIO(Request.post("http://localhost/api/observations-download",Body.fromString(s"""{"observation_ids":["${f.records.last.id}"],"delivery":{"mode":"original"}}""")))
        body <- decode(response)
        id <- ZIO.fromOption(field(body,"id").flatMap(_.asString)).orElseFail(new RuntimeException("Expected a download manifest"))
        _ <- f.downloads.execute(id)
        status <- f.api.routes.runZIO(Request.get(s"http://localhost/api/observations-download/$id"))
        done <- decode(status)
        events <- f.api.routes.runZIO(Request.get(s"http://localhost/api/observations-download/$id/events"))
        stream <- events.body.asString
        chunks=list(done,"chunks")
      yield assertTrue(response.status==Status.Accepted,list(body,"observations").size==1,list(body,"chunks").size==1,
        List("mode","query","progress","status_url","events_url","errors").forall(k=>field(body,k).nonEmpty),
        list(done,"observations").flatMap(field(_,"id").flatMap(_.asString))==List(f.records.last.id),
        chunks.flatMap(field(_,"frame_id").flatMap(_.asString))==List(f.records.last.id),chunks.forall(c=>field(c,"fits_cutout_url").nonEmpty && field(c,"preview_status").contains(Json.Str("unavailable"))),
        field(done,"status").contains(Json.Str("completed")),stream.contains("job.completed"),stream.contains("fits_cutout_url"),f.searches.get==0,f.transfers.get==1) }
    },
    test("pending chunk links and live SSE use the common legacy fields") {
      fixture { f=>for
        response <- f.api.routes.runZIO(Request.post("http://localhost/api/observations-download",Body.fromString(s"""{"observation_ids":["${f.records.head.id}"]}""")))
        body <- decode(response)
        id <- ZIO.fromOption(field(body,"id").flatMap(_.asString)).orElseFail(new RuntimeException("Expected download id"))
        chunk=list(body,"chunks").head
        link <- ZIO.fromOption(field(chunk,"fits_cutout_url").flatMap(_.asString)).orElseFail(new RuntimeException("Expected FITS URL"))
        pending <- f.api.routes.runZIO(Request.get("http://localhost"+link))
        events <- f.api.routes.runZIO(Request.get(s"http://localhost/api/observations-download/$id/events"))
        reader <- events.body.asString.forkScoped
        _ <- f.downloads.execute(id)
        text <- reader.join
        resource <- f.api.routes.runZIO(Request.get("http://localhost"+link))
        bytes <- resource.body.asChunk
        preview <- f.api.routes.runZIO(Request.get("http://localhost"+link+"/preview"))
        ready=text.split("\n\n").find(_.contains("event: chunk.ready")).toList.flatMap(_.split("\n").filter(_.startsWith("data: "))).headOption.map(_.drop(6)).flatMap(_.fromJson[Json].toOption).getOrElse(Json.Null)
      yield assertTrue(pending.status==Status.Accepted,resource.status==Status.Ok,bytes.toArray.toList==ArchiveTransferSpec.fits.toList,preview.status==Status.Conflict,
        field(ready,"frame_id").contains(Json.Str(f.records.head.id)),field(ready,"chunk_id")==field(chunk,"id"),field(ready,"job_id").contains(Json.Str(id)),field(ready,"progress").nonEmpty,field(ready,"fits_cutout_url").contains(Json.Str(link)),f.searches.get==0,f.transfers.get==1) }
    },
    test("download rejects geometry instead of implicitly performing a search") {
      fixture { f=>for
        response <- f.api.routes.runZIO(Request.post("http://localhost/api/observations-download",Body.fromString("""{"region":{"type":"circle","ra_degrees":1,"dec_degrees":2,"radius_degrees":0.1},"providers":["eso"]}""")))
        missing <- f.api.routes.runZIO(Request.post("http://localhost/api/observations-download",Body.fromString("""{"observation_ids":["missing"]}""")))
        empty <- f.api.routes.runZIO(Request.post("http://localhost/api/observations-download",Body.fromString("""{"observation_ids":[]}""")))
      yield assertTrue(response.status==Status.UnprocessableEntity,missing.status==Status.NotFound,empty.status==Status.UnprocessableEntity,f.searches.get==0,f.transfers.get==0) }
    },
    test("generic search rejects IRSA-only filters and malformed common coordinates") {
      fixture { f=>for
        responses <- ZIO.foreach(List("detector_array=1","channel_index=2","radius_degrees=NaN","providers=eso"))(extra=>f.api.routes.runZIO(Request.get("http://localhost/api/observations-search?right_ascension_deg=1&declination_deg=2&radius_degrees=0.1&providers=eso&"+extra)))
      yield assertTrue(responses.forall(_.status==Status.UnprocessableEntity),f.searches.get==0,f.transfers.get==0) }
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock @@ TestAspect.timeout(30.seconds)
