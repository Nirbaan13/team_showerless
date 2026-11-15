package spaceapps.processing

import spaceapps.processing.integrations.HttpHistoricalMotionClient
import spaceapps.processing.controller.HistoricalMotionApi
import spaceapps.infra.model.ApiError
import zio.*
import zio.json.ast.Json
import zio.test.*
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.nio.file.Files
import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest

object HistoricalMotionSpec extends ZIOSpecDefault:
  private val id="e31155f6-8ed3-42f2-a3ec-cc81a114c809"
  private def failure(status:Int,body:String):Task[Either[Throwable,Json]]=ZIO.scoped {
    for
      file <- ZIO.acquireRelease(ZIO.attempt(Files.createTempFile("motion-error",".npz")))(p=>ZIO.attempt(Files.deleteIfExists(p)).orDie)
      _ <- ZIO.attempt(Files.writeString(file,"fixture"))
      server <- ZIO.acquireRelease(ZIO.attempt {
        val server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
        server.createContext("/internal/motion/prepared",exchange=> {
          exchange.getRequestBody.readAllBytes()
          val output=body.getBytes(UTF_8)
          exchange.getResponseHeaders.add("Content-Type","application/json");exchange.sendResponseHeaders(status,output.length)
          try exchange.getResponseBody.write(output) catch case _:java.io.IOException=>() finally exchange.close()
        });server.start();server
      })(s=>ZIO.succeed(s.stop(0)))
      client <- HttpHistoricalMotionClient.make(s"http://127.0.0.1:${server.getAddress.getPort}")
      result <- client.prepared(id,file).either
    yield result
  }
  private def health(body:String):Task[Boolean]=ZIO.scoped {
    for
      server <- ZIO.acquireRelease(ZIO.attempt {
        val server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
        server.createContext("/health",exchange=> {
          val output=body.getBytes(UTF_8)
          exchange.getResponseHeaders.add("Content-Type","application/json");exchange.sendResponseHeaders(200,output.length)
          try exchange.getResponseBody.write(output) finally exchange.close()
        });server.start();server
      })(s=>ZIO.succeed(s.stop(0)))
      client <- HttpHistoricalMotionClient.make(s"http://127.0.0.1:${server.getAddress.getPort}")
      result <- client.healthy
    yield result
  }
  def spec=suite("managed historical motion bridge")(
    test("accepts only a managed unification ID and named profile") {
      val good=HistoricalMotionApi.selection(Json.Obj("unification_id"->Json.Str(id),"profile"->Json.Str("stellar_proper_motion")))
      val extra=HistoricalMotionApi.selection(Json.Obj("unification_id"->Json.Str(id),"profile"->Json.Str("stellar_proper_motion"),"url"->Json.Str("http://localhost/secret")))
      val legacy=HistoricalMotionApi.selection(Json.Obj("ra"->Json.Num(1),"dec"->Json.Num(2)))
      assertTrue(good==Right(id),extra.isLeft,legacy.left.exists(_.code=="unsupported_legacy_operation"))
    },
    test("advertises historical availability only for an explicitly qualified service profile") {
      for
        old <- health("{\"status\":\"ok\"}")
        current <- health("{\"status\":\"ok\",\"historical_motion\":{\"profile\":\"stellar_proper_motion\",\"available\":true}}")
      yield assertTrue(!old,current)
    },
    test("sanitizes upstream errors and bounds response bytes") {
      for
        failed <- failure(500,"{\"detail\":\"/secret/path\"}")
        overflow <- failure(200,"{\"padding\":\""+"x"*(4*1024*1024)+"\"}")
      yield assertTrue(failed.left.exists {case e:ApiError=>e.code=="motion_upstream_error" && !e.message.contains("secret");case _=>false},
        overflow.left.exists {case e:ApiError=>e.code=="motion_protocol";case _=>false})
    },
    test("rejects oversized prepared bytes before any HTTP call") {
      ZIO.scoped {for
        file <- ZIO.acquireRelease(ZIO.attempt(Files.createTempFile("oversized-motion",".npz")))(p=>ZIO.attempt(Files.deleteIfExists(p)).orDie)
        _ <- ZIO.attemptBlocking {
          val channel=java.nio.channels.FileChannel.open(file,java.nio.file.StandardOpenOption.WRITE)
          try channel.write(java.nio.ByteBuffer.wrap(Array[Byte](0)),192L*1024*1024) finally channel.close()
        }
        client <- HttpHistoricalMotionClient.make("http://127.0.0.1:1")
        result <- client.prepared(id,file).either
      yield assertTrue(result.left.exists {case e:ApiError=>e.code=="invalid_input";case _=>false}) }
    },
    test("streams exact managed bytes with computed checksum and unification identity") {
      ZIO.scoped {for
        file <- ZIO.acquireRelease(ZIO.attempt(Files.createTempFile("prepared-motion",".npz")))(p=>ZIO.attempt(Files.deleteIfExists(p)).orDie)
        bytes="managed NPZ protocol bytes".getBytes(UTF_8)
        _ <- ZIO.attempt(Files.write(file,bytes))
        seen <- Promise.make[Nothing,Boolean]
        runtime <- ZIO.runtime[Any]
        server <- ZIO.acquireRelease(ZIO.attempt {
          val server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
          server.createContext("/internal/motion/prepared",exchange=>{
            val actual=exchange.getRequestBody.readAllBytes()
            val expected=MessageDigest.getInstance("SHA-256").digest(bytes).map(b=>f"${b & 255}%02x").mkString
            val valid=java.util.Arrays.equals(actual,bytes) && exchange.getRequestHeaders.getFirst("X-Unification-Id")==id && exchange.getRequestHeaders.getFirst("X-Artifact-Sha256")==expected
            Unsafe.unsafe { implicit unsafe=>runtime.unsafe.run(seen.succeed(valid)).getOrThrowFiberFailure() }
            val output="{\"candidates\":[],\"search_profile\":\"stellar_proper_motion\"}".getBytes(UTF_8)
            exchange.getResponseHeaders.add("Content-Type","application/json");exchange.sendResponseHeaders(200,output.length)
            try exchange.getResponseBody.write(output) finally exchange.close()
          });server.start();server
        })(s=>ZIO.succeed(s.stop(0)))
        client <- HttpHistoricalMotionClient.make(s"http://127.0.0.1:${server.getAddress.getPort}")
        response <- client.prepared(id,file)
        valid <- seen.await
        invalid <- HttpHistoricalMotionClient.make("http://localhost:8001/arbitrary/path").either
      yield assertTrue(valid,response.asObject.flatMap(_.get("candidates")).contains(Json.Arr()),invalid.isLeft) }
    }
  ) @@ TestAspect.withLiveClock @@ TestAspect.timeout(20.seconds)
