package spaceapps.downloads

import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.integrations.providers.UnwiseProvider
import scala.jdk.CollectionConverters.*
import spaceapps.downloads.integrations.protocol.*
import spaceapps.downloads.model.*
import spaceapps.downloads.repository.DownloadsRepository
import spaceapps.downloads.service.*
import spaceapps.infra.model.Hash
import zio.*
import zio.http.{Client,Request,Status}
import zio.json.*
import spaceapps.downloads.controller.DownloadsApi
import zio.test.*
import java.nio.file.Files

object UnwiseProviderSpec extends ZIOSpecDefault:
  def spec=suite("unWISE acquisition")(
    test("public observation date search passes federation and filters actual visit intervals") {
      UnwiseFixtures.server(headers=Map(0->UnwiseFixtures.resourceHeader("unwise-e000-header.txt"),22->UnwiseFixtures.header())) { f=>ZIO.scoped { for
        client <- ZIO.service[Client]
        root <- ZIO.attempt(Files.createTempDirectory("unwise-public-dates-"))
        repo <- DownloadsRepository.open(root.resolve("jobs.sqlite"))
        transport=new ArchiveTransport(client)
        provider=new UnwiseProvider(transport,f.base,f.policy)
        registry=new ProviderRegistry(List(provider))
        discovery <- FederatedDiscovery.make(registry,repo)
        _ <- discovery.start
        jobs <- DownloadJobs.make(registry,repo,new StreamingDownloader(transport,root.resolve("assets")))
        api=new DownloadsApi(new DownloadsService(registry,repo,discovery,jobs))
        results <- ZIO.foreach(List(
          ("2024-04-15T00:00:00Z","2024-04-18T00:00:00Z"),
          ("2011-01-01T00:00:00Z","2013-12-31T00:00:00Z"),
          ("2010-01-01T00:00:00Z","2025-01-01T00:00:00Z"))) { (after,before)=>for
            response <- api.routes.runZIO(Request.get(ArchiveTransport.params("http://localhost/api/observations-search",List(
              "right_ascension_deg"->"133.795125","declination_deg"->"-7.245139","radius_degrees"->"0.01","providers"->"unwise-neo11",
              "observed_after"->after,"observed_before"->before))))
            text <- response.body.asString
            found <- ZIO.fromEither(text.fromJson[ObservationsFound]).mapError(new RuntimeException(_))
          yield response.status->found }
        downloads <- repo.allDownloads
        dates=results.last._2.observations.flatMap(o=>o.asObject.flatMap(_.get("observation_date")).flatMap(_.asString))
      yield assertTrue(results.forall(_._1==Status.Ok),results.head._2.returned_count==1,
        results.head._2.outcomes.exists(o=>o.status=="success" && o.completeness==Completeness.indexed_subset),
        results(1)._2.returned_count==0,results(1)._2.outcomes.exists(_.status=="empty"),
        results.last._2.returned_count==2,dates.exists(_.startsWith("2010-05-03")),dates.exists(_.startsWith("2024-04-14")),downloads.isEmpty) } }
    },
    test("bounded range follows same-origin redirects and rejects ignored, oversized, and malformed ranges") {
      ZIO.foreach(List("normal","ignored","oversize","bad-range")) { mode=>
        UnwiseFixtures.server(rangeMode=mode) { f=>for
          client <- ZIO.service[Client]
          result <- new ArchiveTransport(client).metadataRange(f.base+"/redirect",f.policy,11520).either
        yield if mode=="normal" then result.exists(_.length==5760) else result.isLeft }
      }.map(results=>assertTrue(results.forall(identity)))
    },
    test("discovery uses actual MJD intervals, ignores W1-only epochs and unavailable W2, and caches metadata") {
      UnwiseFixtures.server() { f=>for
        client <- ZIO.service[Client]
        provider=new UnwiseProvider(new ArchiveTransport(client),f.base,f.policy)
        query=ArchiveQuery(Circle(134.24,-7.57,0.01),List("unwise-neo11"))
        first <- provider.search(query,None)
        second <- provider.search(query.copy(time_start_utc=Some("2024-04-15T00:00:00Z"),time_end_utc=Some("2024-04-18T00:00:00Z")),None)
        assets <- provider.resolve(second.records.head,DeliveryRequest(DeliveryMode.original))
        bad <- provider.resolve(second.records.head.copy(native_id="../../outside"),DeliveryRequest(DeliveryMode.original)).either
        cutout <- provider.resolve(second.records.head,DeliveryRequest(DeliveryMode.require_cutout)).either
        paths=f.requests.asScala.toList
      yield assertTrue(first.records.size==2,first.completeness==Completeness.indexed_subset,second.records.size==1,
        second.records.head.time.start_utc.exists(_.startsWith("2024-04-14")),second.records.head.time.end_utc.exists(_.startsWith("2024-04-19")),
        first.records.exists(_.time.start_utc.exists(_.startsWith("2010-01-28"))),
        first.records.forall(r=>r.analysisEligible && r.native("FILTER")=="W2" && r.native("release")=="neo11"),
        second.records.head.native("MAGZP")=="22.5",assets.map(_.semantic)==List("#this","#inverse-variance","#coverage","#contributors"),
        assets.map(_.url.split("/").last)==List("unwise-1342m076-w2-img-m.fits","unwise-1342m076-w2-invvar-m.fits.gz","unwise-1342m076-w2-n-m.fits.gz","unwise-1342m076-w2-frames.fits"),
        bad.isLeft,cutout.isLeft,paths.count(_._1.endsWith("atlas.fits"))==1,!paths.exists(_._1.contains("e001")),
        paths.filterNot(_._1.endsWith("atlas.fits")).forall(_._2.contains("bytes=0-11519")),first.warnings.exists(_.contains("404"))) }
    },
    test("early real W2 header without BAND qualifies through its W2 reference and actual MJD") {
      val early=UnwiseFixtures.resourceHeader("unwise-e000-header.txt")
      UnwiseFixtures.server(headers=Map(0->early,22->UnwiseFixtures.header())) { f=>for
        client <- ZIO.service[Client]
        provider=new UnwiseProvider(new ArchiveTransport(client),f.base,f.policy)
        page <- provider.search(ArchiveQuery(Circle(134.24,-7.57,0.01),List("unwise-neo11")),None)
        e0=page.records.find(_.native_id=="1342m076:w2:e000")
      yield assertTrue(e0.exists(r=>r.analysisEligible && r.native("MJDMIN")=="55319.36486639" && r.time.start_utc.exists(_.startsWith("2010-05-03")) && r.provenance("band_identity_source")=="atlas_w2+archive_product_path+REFEREN1")) }
    },
    test("unsupported calibration remains ineligible and epoch identity mismatch never becomes an observation") {
      UnwiseFixtures.server(headers=Map(0->UnwiseFixtures.header(0,Map("MAGZP"->"20.0")),22->UnwiseFixtures.header(21))) { f=>for
        client <- ZIO.service[Client]
        provider=new UnwiseProvider(new ArchiveTransport(client),f.base,f.policy)
        page <- provider.search(ArchiveQuery(Circle(134.24,-7.57,0.01),List("unwise-neo11")),None)
      yield assertTrue(page.records.size==1,!page.records.head.analysisEligible,page.records.head.provenance.contains("analysis_ineligible_reason"),page.warnings.exists(_.contains("invalid_response"))) }
    },
    test("a conflicting present BAND or FILTER is rejected even on the generated W2 archive path") {
      val wrongFilter=UnwiseFixtures.header().grouped(80).flatMap { card=>
        if new String(card,java.nio.charset.StandardCharsets.US_ASCII).startsWith("UNW_VER") then "FILTER  = 'W1'".padTo(80,' ').getBytes(java.nio.charset.StandardCharsets.US_ASCII) else card
      }.toArray
      UnwiseFixtures.server(headers=Map(0->UnwiseFixtures.header(0,Map("BAND"->"1")),22->wrongFilter)) { f=>for
        client <- ZIO.service[Client]
        page <- new UnwiseProvider(new ArchiveTransport(client),f.base,f.policy).search(ArchiveQuery(Circle(134.24,-7.57,0.01),List("unwise-neo11")),None)
      yield assertTrue(page.records.isEmpty,page.warnings.count(_.contains("invalid_response"))==2) }
    },
    test("wide queries are refused and result truncation does not claim completeness") {
      UnwiseFixtures.server() { f=>for
        client <- ZIO.service[Client]
        provider=new UnwiseProvider(new ArchiveTransport(client),f.base,f.policy)
        wide <- provider.search(ArchiveQuery(Circle(134.24,-7.57,1),List("unwise-neo11")),None).either
        page <- provider.search(ArchiveQuery(Circle(134.24,-7.57,0.01),List("unwise-neo11"),limit_per_provider=1),None)
      yield assertTrue(wide.left.toOption.exists(_.code=="unsupported_geometry"),page.records.size==1,page.completeness==Completeness.truncated,page.warnings.nonEmpty) }
    },
    test("header and tile budgets report truncation instead of fabricating coverage") {
      val crowded=UnwiseFixtures.atlas(List(("1342m076",134.237284,-7.572222,(0 to 110).map(_->3).toList)))
      UnwiseFixtures.server(atlasBytes=crowded) { f=>for
        client <- ZIO.service[Client]
        provider=new UnwiseProvider(new ArchiveTransport(client),f.base,f.policy)
        page <- provider.search(ArchiveQuery(Circle(134.24,-7.57,0.01),List("unwise-neo11")),None)
        requests=f.requests.asScala.toList
      yield assertTrue(page.completeness==Completeness.truncated,page.warnings.exists(_.contains("header budget")),requests.count(_._2.nonEmpty)==96) }
    },
    test("unWISE origin policy rejects arbitrary hosts, ports, schemes, and lookalike domains") {
      val policy=OriginPolicy.forProvider("unwise-neo11")
      assertTrue(scala.util.Try(policy.validate("https://portal.nersc.gov/project/coadd.fits")).isSuccess,
        List("http://portal.nersc.gov/f","https://portal.nersc.gov:8443/f","https://portal.nersc.gov.evil.test/f","https://evil.test/f").forall(u=>scala.util.Try(policy.validate(u)).isFailure))
    },
    test("related products retain semantic roles on success, failure, and a cached repeat") {
      ArchiveTransferSpec.server(ArchiveTransferSpec.fits) { (base,policy)=>ZIO.scoped { for
        client <- ZIO.service[Client]
        root <- ZIO.attempt(Files.createTempDirectory("unwise-related-"))
        repo <- DownloadsRepository.open(root.resolve("jobs.sqlite"))
        record=ArchiveRecord.create("unwise-neo11","neo11","1342m076:w2:e022",ProductKind.image)
        _ <- repo.saveSearch(SearchSnapshot("search",ArchiveQuery(Circle(134.2,-7.5,0.01),List("unwise-neo11")),records=List(record)))
        provider=new ArchiveProvider:
          val id="unwise-neo11"
          override def origins=policy
          def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image),original=true))
          def search(q:ArchiveQuery,c:Option[ProviderCursor])=ZIO.succeed(ProviderPage(Nil,Completeness.indexed_subset))
          def resolve(r:ArchiveRecord,d:DeliveryRequest)=ZIO.succeed(List(
            ArchiveAsset(ArchiveAssetKey.key(r,d),id,base,"#this"),
            ArchiveAsset(Hash.sha256(r.id+"invvar"),id,base,"#inverse-variance"),
            ArchiveAsset(Hash.sha256(r.id+"coverage"),id,"https://evil.test/coverage","#coverage")))
        jobs <- DownloadJobs.make(new ProviderRegistry(List(provider)),repo,new StreamingDownloader(new ArchiveTransport(client),root.resolve("assets")))
        first <- jobs.accept(DownloadSelection(List(record.id),DeliveryRequest(DeliveryMode.original)))
        _ <- jobs.execute(first.id)
        a <- jobs.status(first.id)
        second <- jobs.accept(DownloadSelection(List(record.id),DeliveryRequest(DeliveryMode.original)))
        _ <- jobs.execute(second.id)
        b <- jobs.status(second.id)
      yield assertTrue(a.status=="partial",b.status=="partial",a.assets.size==3,b.assets.size==3,
        List(a,b).forall(_.assets.map(_.provenance.getOrElse("asset_role","")).toSet==Set("#this","#inverse-variance","#coverage")),
        b.assets.find(_.provenance.get("asset_role").contains("#coverage")).exists(_.error.exists(_.code=="untrusted_origin"))) } }
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock @@ TestAspect.timeout(30.seconds)
