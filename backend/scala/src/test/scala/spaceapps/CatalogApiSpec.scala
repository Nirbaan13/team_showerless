package spaceapps

import spaceapps.catalogs.controller.CatalogApi
import spaceapps.catalogs.integrations.TapCatalogs
import spaceapps.catalogs.service.Catalogs
import zio.*
import zio.http.*
import zio.json.*
import zio.json.ast.Json
import zio.test.*
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.nio.charset.StandardCharsets.UTF_8

object CatalogApiSpec extends ZIOSpecDefault:
  private def fixture[A](response:String=> (Int,String))(run:(CatalogApi,java.util.concurrent.ConcurrentLinkedQueue[String])=>ZIO[Scope,Throwable,A]):Task[A]=
    ZIO.scoped {
      for
        calls<-ZIO.succeed(new java.util.concurrent.ConcurrentLinkedQueue[String]())
        server<-ZIO.acquireRelease(ZIO.attempt {
          val server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
          server.createContext("/",ex=>{
            val query=java.net.URLDecoder.decode(ex.getRequestURI.getRawQuery,UTF_8)
            calls.add(query)
            val (status,body)=response(query)
            val bytes=body.getBytes(UTF_8)
            ex.getResponseHeaders.add("Content-Type","application/json")
            ex.sendResponseHeaders(status,bytes.length)
            try ex.getResponseBody.write(bytes) finally ex.close()
          });server.start();server
        })(s=>ZIO.succeed(s.stop(0)))
        client<-ZIO.service[Client]
        url=s"http://127.0.0.1:${server.getAddress.getPort}"
        service<-Catalogs.make(new TapCatalogs(client,url,url))
        result<-run(new CatalogApi(Some(service)),calls)
      yield result
    }.provide(Client.default)
  private val request=Request.get("http://localhost/api/motion/catalog?ra=250&dec=10&fov_arcmin=5")
  def spec=suite("Real catalogues never invent scientific sources")(
    test("a successful empty TAP result stays empty for every catalogue") {
      fixture(_=>(200,"""{"data":[]}""")) { (api,calls)=>
        for
          response<-api.routes.runZIO(request)
          text<-response.body.asString
          data<-ZIO.fromEither(text.fromJson[Json]).mapError(new RuntimeException(_))
        yield assertTrue(response.status==Status.Ok,text.contains("live_agency"),calls.size==3,
          data.asObject.flatMap(_.get("totalObjects")).contains(Json.Num(0)),
          !text.contains("Gaia DR3 3"),text.contains("\"ephemerisSources\":[]"))
      }
    },
    test("all failing providers produce 503 and no successful live status or generated sources") {
      fixture(_=>(502,"""{"error":"archive unavailable"}""")) { (api,_)=>
        for
          response<-api.routes.runZIO(request)
          text<-response.body.asString
        yield assertTrue(response.status==Status.ServiceUnavailable,text.contains("catalog_upstream_error"),
          text.contains("\"totalObjects\":0"),!text.contains("live_agency"))
      }
    },
    test("partial catalogue success preserves the exact supplied source and unknown measurements") {
      fixture(q=>if q.contains("gaiadr3") then (200,"""{"data":[["1234567890123456789",250.001,10.002,null,null,3.2]]}""") else (503,"{}")) { (api,_)=>
        for
          response<-api.routes.runZIO(request)
          text<-response.body.asString
        yield assertTrue(response.status==Status.Ok,text.contains("partial_agency"),
          text.contains("Gaia DR3 1234567890123456789"),text.contains("\"mag\":null"),text.contains("\"pmRa\":null"),
          text.contains("\"wiseSources\":[]"),text.contains("\"totalObjects\":1"))
      }
    },
    test("malformed upstream JSON objects are failures rather than empty coverage") {
      fixture(_=>(200,"{}")) { (api,_)=>
        for
          response<-api.routes.runZIO(request)
          text<-response.body.asString
        yield assertTrue(response.status==Status.ServiceUnavailable,text.contains("catalog_protocol"))
      }
    },
    test("invalid or duplicated coordinates fail before any catalogue request") {
      fixture(_=>(200,"""{"data":[]}""")) { (api,calls)=>
        for
          invalid<-api.routes.runZIO(Request.get("http://localhost/api/motion/catalog?ra=NaN&dec=10"))
          duplicate<-api.routes.runZIO(Request.get("http://localhost/api/motion/catalog?ra=1&ra=2&dec=10"))
        yield assertTrue(invalid.status==Status.UnprocessableEntity,duplicate.status==Status.UnprocessableEntity,calls.isEmpty)
      }
    }
  ) @@ TestAspect.withLiveClock
