package spaceapps

import spaceapps.domain.*
import spaceapps.service.*
import spaceapps.repository.Repository
import spaceapps.controller.Api
import spaceapps.integrations.processing.PythonProcessor
import spaceapps.integrations.grpc.GrpcServer
import spaceapps.integrations.grpc.v1.{PrepareRequest,Query as RpcQuery,Center as RpcCenter,ChunkRequest}
import spaceapps.integrations.grpc.v1.ZioRetrieval.RetrievalServiceClient
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder
import scalapb.zio_grpc.ZManagedChannel
import zio.*
import zio.http.*
import zio.json.*
import zio.test.*
import java.nio.file.{Files,Path,Paths}

object PythonJobsSpec extends ZIOSpecDefault:
  private val python=sys.env.getOrElse("PROCESSING_PYTHON",Paths.get(java.lang.System.getProperty("user.home"),"edu","UtilsAI",".venv","bin","python").toString)
  private def fixture[A](use:(Api,Jobs,RetrievalServiceClient)=>ZIO[Scope,Throwable,A]):ZIO[Scope,Throwable,A]=
    for
      dir <- ZIO.attempt(Files.createTempDirectory("python-jobs-"))
      repo <- Repository.open(dir.resolve("jobs.sqlite"))
      source=new Archive:
        def search(q:Query)=ZIO.succeed(List(ArchiveImage(Observation("real-fixture","2025-04-29T00:00:00Z",1,"DR1"),"https://example.test/native.fits")))
        def fetch(image:ArchiveImage,path:Path)=ZIO.attemptBlocking {
          val input=getClass.getResourceAsStream("/processing/native_fixture.fits")
          try { Files.copy(input,path,java.nio.file.StandardCopyOption.REPLACE_EXISTING);() } finally input.close()
        }
      archive <- CapacityArchive.make(source,dir,2*1024*1024,256*1024,0)
      processor <- PythonProcessor.make(python,Paths.get("processing/worker.py"),Paths.get("../pipeline"))
      jobs <- Jobs.make(repo,archive,processor,dir)
      api <- Api.make(jobs,"python-jobs-test",Paths.get("docs/openai/openapi.yaml"),processingModes=processor.supportedModes)
      port <- GrpcServer.start(jobs,"python-jobs-test","127.0.0.1",0,processingModes=processor.supportedModes)
      grpc <- RetrievalServiceClient.scoped(ZManagedChannel(NettyChannelBuilder.forAddress("127.0.0.1",port).usePlaintext()))
      result <- use(api,jobs,grpc)
    yield result
  private def completed(jobs:Jobs,id:String):Task[Download]=jobs.get(id).flatMap { job=>
    if job.terminal then ZIO.succeed(job) else ZIO.sleep(25.millis) *> completed(jobs,id)
  }
  def spec=suite("Verified Python job flow")(
    test("enabling previews refreshes an old native-only job while reusing its cached FITS") {
      ZIO.scoped {
        for
          dir <- ZIO.attempt(Files.createTempDirectory("python-upgrade-"))
          repo <- Repository.open(dir.resolve("jobs.sqlite"))
          fetched <- Ref.make(0)
          source=new Archive:
            def search(q:Query)=ZIO.succeed(List(ArchiveImage(Observation("upgrade-fixture","2025-04-29T00:00:00Z",1,"DR1"),"https://example.test/upgrade.fits")))
            def fetch(image:ArchiveImage,path:Path)=fetched.update(_+1) *> ZIO.attemptBlocking {
              val input=getClass.getResourceAsStream("/processing/native_fixture.fits")
              try { Files.copy(input,path,java.nio.file.StandardCopyOption.REPLACE_EXISTING);() } finally input.close()
            }
          archive <- CapacityArchive.make(source,dir,2*1024*1024,256*1024,0)
          q=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get
          old <- ZIO.scoped {
            for
              jobs <- Jobs.make(repo,archive,NoProcessing,dir)
              submitted <- jobs.submit(q,"default",None)
              done <- completed(jobs,submitted.id)
            yield done
          }
          processor <- PythonProcessor.make(python,Paths.get("processing/worker.py"),Paths.get("../pipeline"))
          jobs <- Jobs.make(repo,archive,processor,dir)
          next <- jobs.submit(q,"default",None)
          done <- completed(jobs,next.id)
          transfers <- fetched.get
        yield assertTrue(old.chunks.head.preview_status=="unavailable",old.id!=done.id,
          done.status=="completed",done.chunks.head.preview_status=="ready",transfers==1)
      }
    },
    test("gRPC selects verified ZODI processing and streams the resulting FITS") {
      ZIO.scoped(fixture { (_,jobs,grpc)=>
        for
          submitted <- grpc.prepareObservations(PrepareRequest(Some(RpcQuery(region=RpcQuery.Region.Center(RpcCenter(1,2)))),mode="zodi_reference_subtracted"))
          done <- completed(jobs,submitted.id)
          bytes <- grpc.getChunk(ChunkRequest(done.chunks.head.id)).runCollect
          data=bytes.flatMap(_.data.toByteArray).toArray
        yield assertTrue(submitted.mode=="zodi_reference_subtracted",done.status=="completed",
          done.chunks.head.preview_status=="ready",new String(data.take(30),java.nio.charset.StandardCharsets.US_ASCII).startsWith("SIMPLE  ="))
      })
    },
    test("default retrieval publishes a real PNG preview after native FITS readiness") {
      ZIO.scoped(fixture { (api,jobs,_)=>
        for
          response <- api.routes.runZIO(Request.get("http://localhost/api/observations/default?right_ascension_deg=1&declination_deg=2"))
          body <- response.body.asString
          submitted <- ZIO.fromEither(body.fromJson[Download]).mapError(new RuntimeException(_))
          done <- completed(jobs,submitted.id)
          preview <- jobs.resource(done.chunks.head.id,true)
          bytes <- preview match
            case Resource.Ready(path)=>ZIO.attempt(Files.readAllBytes(path).take(8).toList)
            case other=>ZIO.fail(new RuntimeException(other.toString))
        yield assertTrue(response.status==Status.Accepted,done.status=="completed",done.chunks.head.status=="ready",
          done.chunks.head.preview_status=="ready",bytes==List[Byte](-119,80,78,71,13,10,26,10))
      })
    },
    test("ZODI endpoint uses verified processing while epoch difference remains explicitly unsupported") {
      ZIO.scoped(fixture { (api,jobs,_)=>
        for
          response <- api.routes.runZIO(Request.get("http://localhost/api/observations/zodi-reference-subtracted?right_ascension_deg=1&declination_deg=2"))
          body <- response.body.asString
          submitted <- ZIO.fromEither(body.fromJson[Download]).mapError(new RuntimeException(_))
          done <- completed(jobs,submitted.id)
          epoch <- api.routes.runZIO(Request.get("http://localhost/api/observations/epoch-difference?right_ascension_deg=1&declination_deg=2&reference_frame_id=none"))
        yield assertTrue(response.status==Status.Accepted,done.mode=="zodi_reference_subtracted",done.status=="completed",
          done.chunks.head.preview_status=="ready",epoch.status==Status.NotImplemented)
      })
    }
  ) @@ TestAspect.withLiveClock @@ TestAspect.timeout(30.seconds)
