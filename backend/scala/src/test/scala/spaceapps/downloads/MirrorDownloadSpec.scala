package spaceapps.downloads

import spaceapps.downloads.model.*
import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.integrations.providers.IrsaProvider
import spaceapps.downloads.integrations.protocol.*
import spaceapps.downloads.repository.DownloadsRepository
import spaceapps.downloads.service.*
import spaceapps.infra.service.FileCache
import spaceapps.irsa.model.{ArchiveImage,Observation,Query}
import spaceapps.irsa.service.Archive
import zio.*
import zio.http.Client
import zio.json.ast.Json
import zio.test.*
import java.nio.file.{Files,Path}
import java.util.concurrent.atomic.AtomicInteger

object MirrorDownloadSpec extends ZIOSpecDefault:
  private val parent="https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/dr1/level2/period/version/1/native.fits"
  private def bridge(base:String,repo:DownloadsRepository,mirror:Boolean=true):IrsaProvider=
    val image=ArchiveImage(Observation("mirror-frame","2025-05-06T00:00:00Z",1,"DR1",
      header_metadata=Map("discovery_source"->Json.Str(if mirror then "s3_mirror" else "irsa_sia"))),parent,Some(parent))
    val source=new Archive:
      def search(q:Query)=ZIO.succeed(List(image))
      override def select(i:ArchiveImage,q:Query)=ZIO.succeed(i.copy(accessUrl=base+"/ibe/cutout?center=1%2C2deg&size=0.02deg",sourceUrl=Some(parent)))
      def fetch(i:ArchiveImage,p:Path)=ZIO.dieMessage("The HTTP downloader must use its native cutout bridge")
    new IrsaProvider(source,repo)
  private def resolve(base:String,repo:DownloadsRepository,mirror:Boolean=true,delivery:DeliveryRequest=DeliveryRequest(DeliveryMode.require_cutout,Some(Circle(1,2,0.01)))):Task[ArchiveAsset]=
    val provider=bridge(base,repo,mirror)
    provider.search(ArchiveQuery(Circle(1,2,0.01),List("irsa-spherex")),None)
      .flatMap(page=>provider.resolve(page.records.head,delivery))
      .map(_.head)
  private def temporary[A](use:Path=>Task[A]):Task[A]=ZIO.scoped {
    ZIO.acquireRelease(ZIO.attempt(Files.createTempDirectory("mirror-download-")))(dir=>ZIO.attempt {
      val paths=Files.walk(dir)
      try paths.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally paths.close()
    }.ignore).flatMap(use)
  }
  private case class Result(job:DownloadSnapshot,nativeCalls:Int,httpCalls:Int,names:List[String],bytes:List[Byte],arguments:List[(String,String)],key:String)
  private def pipeline(bytes:Array[Byte],repeat:Boolean=false):ZIO[Client,Throwable,Result]=
    val hits=new AtomicInteger()
    ArchiveTransferSpec.server(ArchiveTransferSpec.fits,hits=hits) { (base,local)=>
      for
        client<-ZIO.service[Client]
        result<-temporary { dir=>for
          repo<-DownloadsRepository.open(dir.resolve("jobs.sqlite"))
          native<-Ref.make(List.empty[(String,String)])
          cutouts=(source:String,selected:String,path:Path)=>native.update(_:+(source,selected)) *> ZIO.attemptBlocking {Files.write(path,bytes);()}
          irsa=bridge(base,repo)
          provider=new ArchiveProvider:
            val id="irsa-spherex"
            override def origins=OriginPolicy(OriginPolicy.irsa.hosts,local.localOrigins)
            def capabilities=irsa.capabilities
            def search(q:ArchiveQuery,c:Option[ProviderCursor])=irsa.search(q,c)
            def resolve(r:ArchiveRecord,d:DeliveryRequest)=irsa.resolve(r,d)
          registry=new ProviderRegistry(List(provider))
          limits=ArchiveLimits(max_retries=0)
          discovery<-FederatedDiscovery.make(registry,repo,limits)
          search<-discovery.accept(ArchiveQuery(Circle(1,2,0.01),List("irsa-spherex")))
          _<-discovery.execute(search.id)
          found<-repo.search(search.id)
          record=found.records.head
          delivery=DeliveryRequest(DeliveryMode.require_cutout,Some(Circle(1,2,0.01)))
          selection=DownloadSelection(List(record.id),delivery)
          key=ArchiveAssetKey.key(record,delivery)
          cache<-FileCache.open(dir,dir.resolve("jobs.sqlite"),5760,2880,0)
          downloader=new StreamingDownloader(new ArchiveTransport(client),dir.resolve("archive-assets"),2880,Some(cache),Some(cutouts))
          jobs<-DownloadJobs.make(registry,repo,downloader,limits)
          first<-jobs.accept(selection)
          _<-jobs.execute(first.id)
          _<-ZIO.when(repeat)(jobs.accept(selection).flatMap(next=>jobs.execute(next.id)))
          job<-repo.download(first.id)
          calls<-native.get
          names<-ZIO.attempt {val paths=Files.list(dir.resolve("archive-assets"));try paths.toArray.map(_.asInstanceOf[Path].getFileName.toString).toList finally paths.close()}
          actual<-ZIO.attempt(if Files.exists(dir.resolve("archive-assets").resolve(key)) then Files.readAllBytes(dir.resolve("archive-assets").resolve(key)).toList else Nil)
        yield Result(job,calls.size,hits.get(),names,actual,calls,key) }
      yield result
    }
  def spec=suite("federated mirror pixel delivery")(
    test("a mirror cutout without native transport fails explicitly without contacting IBE") {
      val hits=new AtomicInteger()
      ArchiveTransferSpec.server(ArchiveTransferSpec.fits,hits=hits) { (base,local)=>for
        client<-ZIO.service[Client]
        result<-temporary { dir=>for
          repo<-DownloadsRepository.open(dir.resolve("jobs.sqlite"))
          asset<-resolve(base,repo)
          result<-new StreamingDownloader(new ArchiveTransport(client),dir.resolve("archive-assets"))
            .fetch(asset,OriginPolicy(OriginPolicy.irsa.hosts,local.localOrigins)).either
        yield result }
      yield assertTrue(result.left.toOption.exists(_.code=="native_cutout_unavailable"),hits.get()==0) }
    },
    test("federated discovery downloads native cutout bytes without IBE and reuses its verified cache") {
      pipeline(ArchiveTransferSpec.fits,repeat=true).map { result=>
        val stored=result.job.assets.head.asset
        val checksum=java.security.MessageDigest.getInstance("SHA-256").digest(ArchiveTransferSpec.fits).map(b=>f"${b & 255}%02x").mkString
        assertTrue(result.job.status=="completed",result.nativeCalls==1,result.httpCalls==0,
          result.names==List(result.key),result.bytes==ArchiveTransferSpec.fits.toList,
          stored.exists(s=>s.id==result.key && s.bytes==2880 && s.sha256==checksum),
          result.arguments.map(_._1)==List(parent),result.arguments.head._2.contains("/ibe/cutout?center=1%2C2deg"))
      }
    },
    test("malformed or oversized native helper output never enters the federated cache") {
      ZIO.foreach(List(("invalid".getBytes,"invalid_fits"),(ArchiveTransferSpec.fits++ArchiveTransferSpec.fits,"byte_limit"))) { (bytes,code)=>
        pipeline(bytes).map(result=>result.job.status=="failed" && result.nativeCalls==1 && result.httpCalls==0 && result.names.isEmpty && result.job.assets.head.error.exists(_.code==code))
      }.map(results=>assertTrue(results.forall(identity)))
    },
    test("both mirror source and selected URL origins are checked before native transfer") {
      for
        client<-ZIO.service[Client]
        result<-temporary { dir=>for
          calls<-Ref.make(0)
          transfer=(source:String,selection:String,path:Path)=>calls.update(_+1)
          downloader=new StreamingDownloader(new ArchiveTransport(client),dir,cutoutTransfer=Some(transfer))
          invalid<-ZIO.foreach(List(("https://evil.test/native.fits","https://irsa.ipac.caltech.edu/ibe/subset"),(parent,"https://evil.test/subset"))) { (source,selected)=>
            downloader.fetch(ArchiveAsset("key","irsa-spherex",selected,cutout_source_url=Some(source)),OriginPolicy.irsa).either
          }
          count<-calls.get
        yield invalid.forall(_.left.toOption.exists(_.code=="untrusted_origin")) && count==0 }
      yield assertTrue(result)
    },
    test("original delivery and primary cutouts retain ordinary HTTP transport") {
      temporary { dir=>for
        repo<-DownloadsRepository.open(dir.resolve("jobs.sqlite"))
        original<-resolve("https://irsa.ipac.caltech.edu",repo,delivery=DeliveryRequest(DeliveryMode.original))
        primary<-resolve("https://irsa.ipac.caltech.edu",repo,mirror=false)
      yield assertTrue(original.cutout_source_url.isEmpty,original.url==parent,primary.cutout_source_url.isEmpty) }
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock
