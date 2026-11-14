package spaceapps

import zio.*
import zio.test.*
import java.nio.file.{Files,Path}

object CapacitySpec extends ZIOSpecDefault:
  def spec=suite("Cache admission")(
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
