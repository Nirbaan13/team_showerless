package spaceapps.unification

import spaceapps.service.FitsCache
import zio.*
import zio.test.*
import java.nio.file.Files

object UnificationCapacitySpec extends ZIOSpecDefault:
  def spec=suite("Unified staging capacity")(
    test("staged bytes consume one directory reservation and adoption needs no second product budget") {
      ZIO.scoped { for
        root <- ZIO.acquireRelease(ZIO.attemptBlocking(Files.createTempDirectory("unification-capacity")))(p=>ZIO.attemptBlocking {
          val stream=Files.walk(p)
          try stream.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally stream.close()
        }.orDie)
        cache <- FitsCache.open(root,root.resolve("state.sqlite"),100,60,0)
        _ <- ZIO.attemptBlocking(Files.write(root.resolve("existing.dat"),Array.fill[Byte](20)(1)))
        job=root.resolve("unifications/12345678-1234-1234-1234-123456789abc")
        output=job.resolve("output/dataset.npz")
        target=job.resolve("dataset.npz")
        _ <- cache.withReservation(job,80) {
          for
            _ <- ZIO.attemptBlocking { Files.createDirectories(output.getParent);Files.write(output,Array.fill[Byte](50)(2));() }
            _ <- cache.adopt(target,output)
          yield ()
        }
        bytes <- ZIO.attemptBlocking(Files.readAllBytes(target))
        staged <- ZIO.attemptBlocking(Files.exists(output))
        // The adopted output participates in the same eviction index as normal products.
        _ <- cache.withReservation(40)(ZIO.unit)
        evicted <- ZIO.attemptBlocking(!Files.exists(target))
      yield assertTrue(bytes.length==50,bytes.forall(_==2),!staged,evicted) }
    }
  )
