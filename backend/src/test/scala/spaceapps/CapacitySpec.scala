package spaceapps

import spaceapps.domain.*
import spaceapps.service.*
import spaceapps.repository.Repository
import spaceapps.integrations.irsa.LiveArchive
import spaceapps.controller.Api

import zio.*
import zio.test.*
import java.nio.file.{Files,Path}

object CapacitySpec extends ZIOSpecDefault:
  def spec=suite("Cache admission")(
    test("active partial bytes are not counted twice when admitting another transfer") {
      ZIO.scoped {
        for
          dir <- ZIO.attempt(Files.createTempDirectory("capacity-overlap-"))
          written <- Promise.make[Nothing,Unit]
          release <- Promise.make[Nothing,Unit]
          delegate=new Archive:
            def search(q:Query)=ZIO.succeed(Nil)
            def fetch(i:ArchiveImage,p:Path)=
              if i.observation.frame_id=="first" then ZIO.attempt(Files.write(p,Array.fill[Byte](50)(1))) *> written.succeed(()) *> release.await
              else ZIO.attempt(Files.write(p,Array.fill[Byte](100)(2))).unit
          bounded <- CapacityArchive.make(delegate,dir,200L,100L,0L)
          first=ArchiveImage(Observation("first","2026-01-01T00:00:00Z",1,"DR1"),"https://example.test/first")
          second=first.copy(observation=first.observation.copy(frame_id="second"))
          fiber <- bounded.fetch(first,dir.resolve("first.part")).forkScoped
          _ <- written.await
          result <- bounded.fetch(second,dir.resolve("second.part")).exit
          _ <- release.succeed(())
          _ <- fiber.join
        yield assertTrue(result.isSuccess,Files.exists(dir.resolve("second.part")))
      }
    },
    test("disk budget is checked before product transfer") {
      for
        dir <- ZIO.attempt(Files.createTempDirectory("capacity-test-"))
        _ <- ZIO.attempt(Files.write(dir.resolve("existing"),Array.fill[Byte](90)(1)))
        called <- Ref.make(false)
        delegate=new Archive:
          def search(q:Query)=ZIO.succeed(Nil)
          def fetch(i:ArchiveImage,p:Path)=called.set(true)
        bounded <- CapacityArchive.make(delegate,dir,100L,20L,0L)
        result <- bounded.fetch(ArchiveImage(Observation("one","2026-01-01T00:00:00Z",1,"DR1"),"https://irsa.ipac.caltech.edu/one"),dir.resolve("new")).exit
        invoked <- called.get
      yield assertTrue(result.isFailure,!invoked)
    }
  )
