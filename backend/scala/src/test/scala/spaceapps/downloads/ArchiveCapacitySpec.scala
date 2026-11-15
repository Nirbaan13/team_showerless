package spaceapps.downloads
import spaceapps.irsa.model.*
import spaceapps.downloads.model.*
import spaceapps.infra.service.FileCache

import spaceapps.irsa.service.*
import spaceapps.downloads.service.*
import spaceapps.downloads.repository.DownloadsRepository
import spaceapps.downloads.bootstrap.DownloadsRuntime
import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.integrations.protocol.*
import spaceapps.infra.service.FileCache
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
        cache <- FileCache.open(root,root.resolve("jobs.sqlite"),maxCacheBytes=5000,maxProductBytes=2880,minFreeBytes=0)
        result <- new StreamingDownloader(new ArchiveTransport(client),root.resolve("archive-assets"),maxBytes=2880,capacity=Some(cache)).fetch(ArchiveAsset("key","eso",base),policy).either
      yield assertTrue(result.left.toOption.exists(_.code=="cache_capacity"),!Files.exists(root.resolve("archive-assets/key")),Files.size(root.resolve("unrelated-existing-product"))==3000) }
    },
    test("native gzip reserves both transferred and decoded temporary storage") {
      ArchiveTransferSpec.server(ArchiveTransferSpec.gzip(ArchiveTransferSpec.fits)) { (base,policy)=>for
        client <- ZIO.service[Client]
        root <- ZIO.attempt(Files.createTempDirectory("shared-gzip-capacity-"))
        cache <- FileCache.open(root,root.resolve("jobs.sqlite"),maxCacheBytes=5000,maxProductBytes=2880,minFreeBytes=0)
        result <- new StreamingDownloader(new ArchiveTransport(client),root.resolve("archive-assets"),maxBytes=2880,capacity=Some(cache)).fetch(ArchiveAsset("key","eso",base),policy).either
        remaining <- ZIO.attempt {val s=Files.list(root.resolve("archive-assets"));try s.count() finally s.close()}
      yield assertTrue(result.left.toOption.exists(_.code=="cache_capacity"),remaining==0) }
    },
    test("published archive assets are evicted before legacy admission through the same coordinator") {
      ArchiveTransferSpec.server(ArchiveTransferSpec.fits) { (base,policy)=>for
        client <- ZIO.service[Client]
        root <- ZIO.attempt(Files.createTempDirectory("shared-legacy-capacity-"))
        cache <- FileCache.open(root,root.resolve("jobs.sqlite"),maxCacheBytes=5000,maxProductBytes=2880,minFreeBytes=0)
        _ <- new StreamingDownloader(new ArchiveTransport(client),root.resolve("archive-assets"),maxBytes=2880,capacity=Some(cache)).fetch(ArchiveAsset("key","eso",base),policy)
        legacy <- cache.transfer(root.resolve("raw/legacy.part"))(ZIO.unit).either
      yield assertTrue(legacy.isRight,!Files.exists(root.resolve("archive-assets/key"))) }
    },
    test("free-space reserve rejects transfer before publishing any artifact") {
      ArchiveTransferSpec.server(ArchiveTransferSpec.fits) { (base,policy)=>for
        client <- ZIO.service[Client]
        root <- ZIO.attempt(Files.createTempDirectory("shared-free-space-"))
        cache <- FileCache.open(root,root.resolve("jobs.sqlite"),maxCacheBytes=10000,maxProductBytes=2880,minFreeBytes=Long.MaxValue)
        result <- new StreamingDownloader(new ArchiveTransport(client),root.resolve("archive-assets"),maxBytes=2880,capacity=Some(cache)).fetch(ArchiveAsset("key","eso",base),policy).either
      yield assertTrue(result.left.toOption.exists(_.code=="cache_capacity"),!Files.exists(root.resolve("archive-assets/key"))) }
    }
  ).provide(Client.default) @@ TestAspect.withLiveClock
