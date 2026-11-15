package spaceapps.processing

import spaceapps.infra.service.FileCache
import zio.*
import zio.test.*
import java.nio.file.Files
import java.util.concurrent.atomic.{AtomicBoolean,AtomicReference}

object CacheScanRaceSpec extends ZIOSpecDefault:
  def spec=suite("Cache scans during file replacement")(
    test("disappearing WAL sidecars cannot fail otherwise admissible native transfers") {
      ZIO.scoped {for
        root <- ZIO.acquireRelease(ZIO.attemptBlocking(Files.createTempDirectory("cache-scan-race")))(p=>ZIO.attemptBlocking {
          val stream=Files.walk(p)
          try stream.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally stream.close()
        }.orDie)
        data=root.resolve("data")
        cache <- FileCache.open(data,root.resolve("state.sqlite"),2*1024*1024,1024*1024,0)
        running=new AtomicBoolean(true)
        threadError=new AtomicReference[Throwable]()
        thread <- ZIO.acquireRelease(ZIO.attemptBlocking {
          val sidecar=data.resolve("archive.sqlite-wal")
          val worker=new Thread(new Runnable:
            def run():Unit=
              try
                while running.get() do
                  Files.write(sidecar,Array[Byte](1))
                  Files.deleteIfExists(sidecar)
              catch case error:Throwable=>threadError.set(error)
          )
          worker.start();worker
        })(worker=>ZIO.attemptBlocking {running.set(false);worker.join();()}.orDie)
        attempts <- ZIO.foreach(1 to 1000)(_=>cache.transfer(data.resolve("probe.part"))(ZIO.unit).either)
        failures=attempts.collect {case Left(error)=>error.getClass.getName+": "+error.getMessage}
      yield assertTrue(failures.size==0,threadError.get()==null) }
    }
  ) @@ TestAspect.withLiveClock @@ TestAspect.timeout(60.seconds)
