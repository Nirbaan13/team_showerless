package spaceapps

import spaceapps.processing.controller.PipelineApi
import spaceapps.processing.integrations.HttpPipelineClient
import zio.*
import zio.http.*
import zio.test.*
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.nio.charset.StandardCharsets.UTF_8

object PipelineApiSpec extends ZIOSpecDefault:
  private def fixture[A](status:Int=200,body:String="""{"spectrum":[{"flux_mjy":1.25}],"total_channels":1}""",delay:Long=0)
    (run:(PipelineApi,java.util.concurrent.ConcurrentLinkedQueue[String])=>ZIO[Scope,Throwable,A]):Task[A]=ZIO.scoped {
    for
      calls<-ZIO.succeed(new java.util.concurrent.ConcurrentLinkedQueue[String]())
      server<-ZIO.acquireRelease(ZIO.attempt {
        val s=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
        s.createContext("/",ex=>{
          calls.add(ex.getRequestMethod+" "+ex.getRequestURI.toString+" "+new String(ex.getRequestBody.readAllBytes(),UTF_8))
          if delay>0 then Thread.sleep(delay)
          val bytes=body.getBytes(UTF_8)
          ex.getResponseHeaders.add("Content-Type","application/json")
          ex.sendResponseHeaders(status,bytes.length)
          try ex.getResponseBody.write(bytes) finally ex.close()
        });s.start();s
      })(s=>ZIO.succeed(s.stop(0)))
      client<-HttpPipelineClient.make(s"http://127.0.0.1:${server.getAddress.getPort}",timeout=if delay>0 then 200.millis else 5.seconds)
      result<-run(new PipelineApi(client),calls)
    yield result
  }
  def spec=suite("Scala adapter for unchanged team pipeline HTTP API")(
    test("spectrum waits for the existing synchronous JSON without changing its contract") {
      fixture() { (api,calls)=>
        for
          response<-api.routes.runZIO(Request.get("http://localhost/api/spectrum?ra=120&dec=-20&radius_pix=2&candidate_id=Known"))
          text<-response.body.asString
        yield assertTrue(response.status==Status.Ok,text.contains("1.25"),!text.contains("download_id"),
          calls.peek().startsWith("GET /api/spectrum?"),calls.peek().contains("candidate_id=Known"))
      }
    },
    test("invalid coordinates and unsupported raw spectra fail before calling Python") {
      fixture() { (api,calls)=>
        for
          invalid<-api.routes.runZIO(Request.get("http://localhost/api/spectrum?ra=NaN&dec=0"))
          raw<-api.routes.runZIO(Request.get("http://localhost/api/spectrum?ra=120&dec=0&subtraction=raw_calibrated"))
        yield assertTrue(invalid.status==Status.UnprocessableEntity,raw.status==Status.UnprocessableEntity,calls.isEmpty)
      }
    },
    test("Python failures remain explicit gateway failures rather than fabricated successful spectra") {
      fixture(500,"""{"detail":"NameError: fits is not defined"}""") { (api,_)=>
        for
          response<-api.routes.runZIO(Request.get("http://localhost/api/spectrum?ra=120&dec=0"))
          text<-response.body.asString
        yield assertTrue(response.status==Status.BadGateway,text.contains("pipeline_upstream_error"),!text.contains("spectrum"))
      }
    },
    test("pipeline requests have finite HTTP deadlines") {
      fixture(delay=1000) { (api,_)=>api.routes.runZIO(Request.get("http://localhost/api/spectrum?ra=120&dec=0"))
        .map(response=>assertTrue(response.status==Status.GatewayTimeout)) }
    },
    test("bounded cutout search bodies reach the original Python route") {
      fixture(body="""{"total":0,"results":[]}""") { (api,calls)=>
        for
          response<-api.routes.runZIO(Request.post("http://localhost/api/cutout/search",Body.fromString("""{"ra":120,"dec":-20,"size_arcmin":3}""")))
        yield assertTrue(response.status==Status.Ok,calls.peek().startsWith("POST /api/cutout/search"))
      }
    }
  ) @@ TestAspect.withLiveClock
