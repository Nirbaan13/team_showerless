package spaceapps

import spaceapps.irsa.model.*
import spaceapps.irsa.service.Archive
import spaceapps.irsa.integrations.ResilientArchive
import spaceapps.infra.service.ExternalServices
import zio.*
import zio.json.ast.Json
import zio.test.*
import java.nio.file.Path

object ResilientArchiveSpec extends ZIOSpecDefault:
  private val query=Query(Json.Obj(),"CIRCLE 250 5.79 0.025")
  private val image=ArchiveImage(Observation("mirror-frame","2025-04-24T18:01:05Z",1,"QR2",
    header_metadata=Map("discovery_source"->Json.Str("s3_mirror"))),
    "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/qr2/level2/2025W17_4B/version/1/native.fits")
  private def archive(find:Task[List[ArchiveImage]])=new Archive:
    def search(q:Query)=find
    def fetch(i:ArchiveImage,p:Path)=ZIO.unit
  def spec=suite("ResilientArchiveSpec")(
    test("a stalled primary opens its circuit and reaches the mirror inside the generic 30-second deadline") {
      ZIO.scoped { for
        services<-ExternalServices.make(Map("irsa_sia"->ZIO.unit))
        _<-services.checkNow("irsa_sia")
        _<-services.isAvailable("irsa_sia").repeatUntil(identity)
        source=ResilientArchive(archive(ZIO.never),archive(ZIO.succeed(List(image))),services)
        done<-source.search(query).timeout(30.seconds).forkScoped
        _<-TestClock.adjust(16.seconds)
        result<-done.join
        available<-services.isAvailable("irsa_sia")
      yield assertTrue(result.contains(List(image)),!available) }
    },
    test("open SIA routes to real mirror without attempting live discovery") {
      ZIO.scoped { for
        calls<-Ref.make(0)
        services<-ExternalServices.make(Map("irsa_sia"->ZIO.never))
        source=ResilientArchive(archive(calls.update(_+1).as(Nil)),archive(ZIO.succeed(List(image))),services)
        result<-source.search(query)
        count<-calls.get
      yield assertTrue(result==List(image),count==0) }
    },
    test("successful health probe restores primary discovery; transient failure immediately falls back") {
      ZIO.scoped { for
        calls<-Ref.make(0)
        services<-ExternalServices.make(Map("irsa_sia"->ZIO.unit))
        _<-services.checkNow("irsa_sia")
        _<-services.isAvailable("irsa_sia").repeatUntil(identity)
        source=ResilientArchive(archive(calls.update(_+1)*>ZIO.fail(ApiError("archive_http_error","HTTP502",true))),archive(ZIO.succeed(List(image))),services)
        first<-source.search(query)
        second<-source.search(query)
        count<-calls.get
      yield assertTrue(first==List(image),second==List(image),count==1) }
    },
    test("validation failures do not become unrelated mirror results") {
      ZIO.scoped { for
        services<-ExternalServices.make(Map("irsa_sia"->ZIO.unit))
        _<-services.checkNow("irsa_sia")
        _<-services.isAvailable("irsa_sia").repeatUntil(identity)
        source=ResilientArchive(archive(ZIO.fail(ApiError("archive_overflow","narrow the field"))),archive(ZIO.succeed(List(image))),services)
        result<-source.search(query).either
      yield assertTrue(result.left.toOption.exists{case a:ApiError=>a.code=="archive_overflow";case _=>false}) }
    },
    test("mirror native selection maps the exact artifact to an IBE cutout and preserves S3 identity") {
      ZIO.scoped { for
        services<-ExternalServices.make(Map("irsa_sia"->ZIO.never))
        source=ResilientArchive(archive(ZIO.succeed(Nil)),archive(ZIO.succeed(List(image))),services)
        selected<-source.select(image,query)
      yield assertTrue(selected.sourceUrl.contains(image.accessUrl),
        selected.accessUrl.startsWith("https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/2025W17_4B/version/1/native.fits?center="),
        selected.observation.release=="QR2") }
    },
    test("mirror pixel transfers use the mirror transport without contacting primary IBE") {
      ZIO.scoped { for
        primaryCalls<-Ref.make(0)
        mirrorCalls<-Ref.make(0)
        services<-ExternalServices.make(Map("irsa_sia"->ZIO.never))
        primary=new Archive:
          def search(q:Query)=ZIO.succeed(Nil)
          def fetch(i:ArchiveImage,p:Path)=primaryCalls.update(_+1)*>ZIO.fail(ApiError("archive_http_error","IBE offline",true))
        mirror=new Archive:
          def search(q:Query)=ZIO.succeed(List(image))
          def fetch(i:ArchiveImage,p:Path)=mirrorCalls.update(_+1)
        source=ResilientArchive(primary,mirror,services)
        selected<-source.select(image,query)
        result<-source.fetch(selected,Path.of("unused-cutout.fits")).either
        primaries<-primaryCalls.get
        mirrors<-mirrorCalls.get
      yield assertTrue(result.isRight,primaries==0,mirrors==1) }
    }
  )
