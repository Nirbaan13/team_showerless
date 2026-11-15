package spaceapps

import spaceapps.processing.integrations.HttpPipelineClient
import spaceapps.infra.model.ApiError
import zio.*
import zio.json.*
import zio.json.ast.Json
import zio.test.*
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.nio.charset.StandardCharsets.UTF_8

object UnificationClientSpec extends ZIOSpecDefault:
  private def fixture[A](status:Int,body:String)(run:HttpPipelineClient=>Task[A]):Task[A]=ZIO.scoped {
    for
      server <- ZIO.acquireRelease(ZIO.attempt {
        val s=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
        s.createContext("/internal/image-unifications",ex=>{
          val request=new String(ex.getRequestBody.readAllBytes(),UTF_8)
          val output=(if request.contains("schema_version") then body else "invalid request").getBytes(UTF_8)
          ex.getResponseHeaders.add("Content-Type","application/json")
          ex.sendResponseHeaders(status,output.length)
          try ex.getResponseBody.write(output) finally ex.close()
        });s.start();s
      })(s=>ZIO.succeed(s.stop(0)))
      client <- HttpPipelineClient.make(s"http://127.0.0.1:${server.getAddress.getPort}",timeout=5.seconds)
      result <- run(client)
    yield result
  }
  def spec=suite("Private image unification HTTP client")(
    test("decodes the private operation JSON for the durable Scala service") {
      fixture(200,"""{"schema_version":1,"status":"completed","frame_count":3}""") { client=>
        client.unify(Json.Obj("schema_version"->Json.Num(1))).map(result=>assertTrue(result.asObject.flatMap(_.get("frame_count")).contains(Json.Num(3))))
      }
    },
    test("preserves bounded transport rejection and sanitized failures") {
      fixture(500,"""{"detail":"/secret/path failed"}""") { client=>
        client.unify(Json.Obj("schema_version"->Json.Num(1))).exit.map {
          case Exit.Failure(cause)=>assertTrue(cause.failureOption.exists {
            case e:ApiError=>e.code=="pipeline_upstream_error" && !e.message.contains("secret")
            case _=>false
          })
          case _=>assertTrue(false)
        }
      }
    },
    test("does not allow arbitrary pipeline paths") {
      fixture(200,"{}") { client=>
        client.request("GET","/internal/arbitrary").exit.map(exit=>assertTrue(exit.isFailure))
      }
    }
  ) @@ TestAspect.sequential
