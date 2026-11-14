package spaceapps

import spaceapps.domain.*
import spaceapps.service.*
import spaceapps.repository.Repository
import spaceapps.integrations.irsa.LiveArchive
import spaceapps.controller.Api

import zio.*
import zio.http.*
import zio.json.*
import zio.test.*
import java.nio.file.Files

object ApiSpec extends ZIOSpecDefault:
  private val geometry="right_ascension_min_deg=1&right_ascension_max_deg=1.01&declination_min_deg=2&declination_max_deg=2.01"
  private def withApi[A](use:Api=>ZIO[Scope,Throwable,A]):ZIO[Scope,Throwable,A]=
    for
      dir <- ZIO.attempt(Files.createTempDirectory("api-test-"))
      repo <- Repository.open(dir.resolve("state.sqlite"))
      fake=new Archive:
        def search(q:Query)=ZIO.succeed(Nil)
        def fetch(i:ArchiveImage,p:java.nio.file.Path)=ZIO.unit
      jobs <- Jobs.make(repo,fake,NoProcessing,dir)
      api <- Api.make(jobs,"test-revision",java.nio.file.Paths.get("docs/openai/openapi.yaml"))
      result <- use(api)
    yield result
  def spec=suite("HTTP contract")(
    test("range is accepted immediately, cached completion and URLs match contract") {
      ZIO.scoped(withApi {api=>
        for
          response <- api.routes.runZIO(Request.get(s"http://localhost/api/observations/range?$geometry"))
          body <- response.body.asString
          job <- ZIO.fromEither(body.fromJson[Download]).mapError(new RuntimeException(_))
        yield assertTrue(response.status==Status.Accepted,job.query.toJson.contains("right_ascension_min_deg"),job.status_url==s"/api/downloads/${job.id}")
      })
    },
    test("malformed query and JSON return documented JSON422") {
      ZIO.scoped(withApi {api=>
        for
          r <- api.routes.runZIO(Request.get("http://localhost/api/observations/polygon?verices_degrees=0,0,1"))
          body <- r.body.asString
          post <- api.routes.runZIO(Request.post("http://localhost/api/observations/search",Body.fromString("{broken")))
        yield assertTrue(r.status==Status.UnprocessableEntity,body.fromJson[ApiError].isRight,post.status==Status.UnprocessableEntity)
      })
    },
    test("missing jobs and chunks are JSON404 and deferred modes cannot look like raw results") {
      ZIO.scoped(withApi {api=>
        for
          job <- api.routes.runZIO(Request.get("http://localhost/api/downloads/missing"))
          chunk <- api.routes.runZIO(Request.get("http://localhost/api/chunks/missing"))
          deferred <- api.routes.runZIO(Request.get("http://localhost/api/observations/epoch-difference?right_ascension_deg=1&declination_deg=2&reference_frame_id=missing"))
        yield assertTrue(job.status==Status.NotFound,chunk.status==Status.NotFound,deferred.status==Status.NotImplemented)
      })
    },
    test("health/version/OpenAPI preserve revision and all contract paths") {
      ZIO.scoped(withApi {api=>
        for
          r <- api.routes.runZIO(Request.get("http://localhost/version"))
          body <- r.body.asString
          o <- api.routes.runZIO(Request.get("http://localhost/openapi.json"))
          schema <- o.body.asString
        yield assertTrue(body.contains("test-revision"),schema.contains("verices_degrees"),schema.contains("/api/downloads/{id}/events"),schema.contains("/api/observations/range"))
      })
    }
  )
