package spaceapps.archive
import spaceapps.domain.*
import spaceapps.archive.domain.*
import spaceapps.service.*
import spaceapps.archive.service.*
import spaceapps.archive.repository.ArchiveRepository
import spaceapps.archive.bootstrap.ArchiveRuntime
import spaceapps.archive.integrations.ArchiveProvider
import spaceapps.archive.integrations.protocol.*
import spaceapps.service.FitsCache
import zio.*
import zio.http.Client
import zio.test.*
import java.nio.file.Files
object ArchiveCapacitySpec extends ZIOSpecDefault:
  def spec=suite("shared archive cache capacity")(
    test("existing DATA_DIR products consume the same quota before archive transfer") {
      ArchiveTransferSpec.server(ArchiveTransferSpec.fits) { (base,policy)=>for
        client <- ZIO.service[Client]
        root <- ZIO.attempt(Files.createTempDirectory("shared-capacity-"))
        _ <- ZIO.attempt(Files.write(root.resolve("unrelated-existing-product"),new Array[Byte](3000)))
        cache <- FitsCache.open(root,root.resolve("jobs.sqlite"),maxCacheBytes=5000,maxProductBytes=2880,minFreeBytes=0)
        result <- new StreamingDownloader(new ArchiveTransport(client),root.resolve("archive-assets"),maxBytes=2880,capacity=Some(cache)).fetch(ArchiveAsset("key","eso",base),policy).either
      yield assertTrue(result.left.toOption.exists(_.code=="cache_capacity"),!Files.exists(root.resolve("archive-assets/key")),Files.size(root.resolve("unrelated-existing-product"))==3000) }
    },
    test("native gzip reserves both transferred and decoded temporary storage") {
      ArchiveTransferSpec.server(ArchiveTransferSpec.gzip(ArchiveTransferSpec.fits)) { (base,policy)=>for
        client <- ZIO.service[Client]
        root <- ZIO.attempt(Files.createTempDirectory("shared-gzip-capacity-"))
        cache <- FitsCache.open(root,root.resolve("jobs.sqlite"),maxCacheBytes=5000,maxProductBytes=2880,minFreeBytes=0)
        result <- new StreamingDownloader(new ArchiveTransport(client),root.resolve("archive-assets"),maxBytes=2880,capacity=Some(cache)).fetch(ArchiveAsset("key","eso",base),policy).either
        remaining <- ZIO.attempt {val s=Files.list(root.resolve("archive-assets"));try s.count() finally s.close()}
      yield assertTrue(result.left.toOption.exists(_.code=="cache_capacity"),remaining==0) }
    },
    test("published archive assets block legacy admission through the same coordinator") {
      ArchiveTransferSpec.server(ArchiveTransferSpec.fits) { (base,policy)=>for
        client <- ZIO.service[Client]
        root <- ZIO.attempt(Files.createTempDirectory("shared-legacy-capacity-"))
        cache <- FitsCache.open(root,root.resolve("jobs.sqlite"),maxCacheBytes=5000,maxProductBytes=2880,minFreeBytes=0)
        _ <- new StreamingDownloader(new ArchiveTransport(client),root.resolve("archive-assets"),maxBytes=2880,capacity=Some(cache)).fetch(ArchiveAsset("key","eso",base),policy)
        legacy <- cache.transfer(root.resolve("raw/legacy.part"))(ZIO.unit).either
      yield assertTrue(legacy.left.toOption.exists {case e: spaceapps.domain.ApiError=>e.code=="cache_capacity";case _=>false},Files.size(root.resolve("archive-assets/key"))==2880) }
    },
    test("free-space reserve rejects transfer before publishing any artifact") {
      ArchiveTransferSpec.server(ArchiveTransferSpec.fits) { (base,policy)=>for
        client <- ZIO.service[Client]
        root <- ZIO.attempt(Files.createTempDirectory("shared-free-space-"))
        cache <- FitsCache.open(root,root.resolve("jobs.sqlite"),maxCacheBytes=10000,maxProductBytes=2880,minFreeBytes=Long.MaxValue)
        result <- new StreamingDownloader(new ArchiveTransport(client),root.resolve("archive-assets"),maxBytes=2880,capacity=Some(cache)).fetch(ArchiveAsset("key","eso",base),policy).either
      yield assertTrue(result.left.toOption.exists(_.code=="cache_capacity"),!Files.exists(root.resolve("archive-assets/key"))) }
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock
