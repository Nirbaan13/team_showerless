package spaceapps

import spaceapps.domain.ApiError
import spaceapps.integrations.processing.HttpProcessingClient
import zio.*
import zio.test.*
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.nio.file.Files

object HttpProcessingClientSpec extends ZIOSpecDefault:
  private def check(status:Int,body:String,delay:Long=0):Task[Either[Throwable,Unit]]=ZIO.scoped {
    for
      server<-ZIO.acquireRelease(ZIO.attempt {
        val s=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
        s.createContext("/internal/processing",ex=>{
          ex.getRequestBody.readAllBytes()
          if delay>0 then Thread.sleep(delay)
          val bytes=body.getBytes(java.nio.charset.StandardCharsets.UTF_8)
          ex.sendResponseHeaders(status,bytes.length)
          try ex.getResponseBody.write(bytes) finally ex.close()
        });s.start();s
      })(s=>ZIO.succeed(s.stop(0)))
      service<-HttpProcessingClient.make(s"http://127.0.0.1:${server.getAddress.getPort}",timeout=if delay>0 then 200.millis else 5.seconds)
      dir<-ZIO.attempt(Files.createTempDirectory("processing-http-"))
      result<-service.preview(dir.resolve("input.fits"),dir.resolve("out.png")).either
    yield result
  }
  private def code(result:Either[Throwable,Unit])=result.left.toOption.collect{case e:ApiError=>e.code}
  def spec=suite("Separate pipeline HTTP client")(
    test("pipeline overload is explicit and does not generate an output") {
      check(503,"""{"status":"error","error":{"code":"busy","message":"Try later"}}""").map(r=>assertTrue(code(r).contains("processing_busy")))
    },
    test("an unavailable HTTP response cannot be accepted as a scientific result") {
      check(200,"x"*70000).map(r=>assertTrue(code(r).contains("processing_protocol")))
    },
    test("pipeline network requests have a finite deadline") {
      check(200,"{}",1000).map(r=>assertTrue(code(r).contains("processing_timeout")))
    },
    test("request cancellation retains the input scope until remote processing acknowledges completion") {
      ZIO.scoped {
        for
          entered<-ZIO.succeed(new java.util.concurrent.CountDownLatch(1))
          finish<-ZIO.succeed(new java.util.concurrent.CountDownLatch(1))
          released<-Ref.make(false)
          server<-ZIO.acquireRelease(ZIO.attempt {
            val s=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
            s.createContext("/internal/processing",ex=>{
              ex.getRequestBody.readAllBytes();entered.countDown()
              finish.await(3,java.util.concurrent.TimeUnit.SECONDS)
              val bytes="""{"status":"error","error":{"code":"invalid_fits"}}""".getBytes
              ex.sendResponseHeaders(422,bytes.length)
              try ex.getResponseBody.write(bytes) finally ex.close()
            });s.start();s
          })(s=>ZIO.succeed(s.stop(0)))
          service<-HttpProcessingClient.make(s"http://127.0.0.1:${server.getAddress.getPort}",timeout=5.seconds)
          dir<-ZIO.attempt(Files.createTempDirectory("processing-cancel-"))
          task<-ZIO.scoped {
            ZIO.acquireRelease(ZIO.unit)(_=>released.set(true)) *>
              service.preview(dir.resolve("in.fits"),dir.resolve("out.png"))
          }.fork
          _<-ZIO.attemptBlocking(entered.await(3,java.util.concurrent.TimeUnit.SECONDS))
          cancelling<-task.interrupt.fork
          _<-ZIO.sleep(100.millis)
          early<-released.get
          _<-ZIO.succeed(finish.countDown())
          _<-cancelling.join
          after<-released.get
        yield assertTrue(!early,after)
      }
    }
  ) @@ TestAspect.withLiveClock
