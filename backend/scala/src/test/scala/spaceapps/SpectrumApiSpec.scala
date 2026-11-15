package spaceapps

import spaceapps.controller.Api
import spaceapps.domain.*
import spaceapps.repository.Repository
import spaceapps.service.*
import zio.*
import zio.http.*
import zio.json.*
import zio.json.ast.Json
import zio.test.*
import java.nio.file.{Files,Path,Paths}

object SpectrumApiSpec extends ZIOSpecDefault:
  private def field(json:Json,key:String)=json.asObject.flatMap(_.get(key)).getOrElse(Json.Null)
  private def document(response:Response)=response.body.asString.flatMap(s=>ZIO.fromEither(s.fromJson[Json]).mapError(new RuntimeException(_)))
  def spec=suite("Team pipeline spectrum integration")(
    test("coordinates hand off to durable downloads then publish measured points through Scala") {
      ZIO.scoped {
        for
          dir<-ZIO.attempt(Files.createTempDirectory("spectrum-api-"))
          gate<-Promise.make[Nothing,Unit]
          archive=new Archive:
            def search(q:Query)=ZIO.succeed(List(ArchiveImage(Observation("spectral-frame","2023-02-25T06:00:00Z",1,"DR1"),"https://irsa.example/frame.fits")))
            def fetch(image:ArchiveImage,path:Path)=gate.await *> ZIO.attemptBlocking {
              val source=getClass.getResourceAsStream("/processing/spectral_fixture.fits")
              try Files.copy(source,path) finally source.close()
              ()
            }
          repo<-Repository.open(dir.resolve("jobs.sqlite"))
          processor<-ProcessingHttpFixture.start(dir)
          jobs<-Jobs.make(repo,archive,processor,dir)
          spectra<-SpectrumService.make(jobs,processor,dir)
          api<-Api.make(jobs,"spectrum-test",Paths.get("docs/openapi.yaml"),spectra=Some(spectra),processingModes=processor.supportedModes)
          url="http://localhost/api/spectrum?ra=120&dec=-20&radius_pix=1.1&candidate_id=KnownStar"
          pending<-api.routes.runZIO(Request.get(url))
          accepted<-document(pending)
          _<-gate.succeed(())
          completed<-api.routes.runZIO(Request.get(url)).repeatWhile(_.status==Status.Accepted).timeoutFail(new RuntimeException("spectrum never completed"))(45.seconds)
          result<-document(completed)
          point=field(result,"spectrum").asArray.get.head
          id=field(result,"download_id").asString.get
          raw<-api.routes.runZIO(Request.get(s"http://localhost/api/spectrum?download_id=$id&ra=120&dec=-20&radius_pix=1.1&subtraction=raw_calibrated"))
          rawResult<-document(raw)
          malformed<-api.routes.runZIO(Request.get("http://localhost/api/spectrum?ra=NaN&dec=-20"))
          repeated<-api.routes.runZIO(Request.get("http://localhost/api/spectrum?ra=120&ra=121&dec=-20"))
        yield assertTrue(pending.status==Status.Accepted,field(accepted,"status_url").asString.exists(_.startsWith("/api/spectrum?")),
          completed.status==Status.Ok,field(result,"scientifically_calibrated")==Json.Bool(false),
          field(result,"quality")==Json.Str("experimental_visualization_photometry"),field(result,"total_channels")==Json.Num(1),
          field(point,"frame_id")==Json.Str("spectral-frame"),
          math.abs(field(point,"flux_mjy").asNumber.get.value.doubleValue-2.232920901214299)<1e-9,
          raw.status==Status.Ok,field(rawResult,"subtraction_mode")==Json.Str("raw_calibrated"),
          malformed.status==Status.UnprocessableEntity,repeated.status==Status.UnprocessableEntity,
          !result.toJson.contains(dir.toString))
      }
    }
  ) @@ TestAspect.withLiveClock @@ TestAspect.sequential
