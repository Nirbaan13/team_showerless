package spaceapps

import spaceapps.domain.*
import spaceapps.service.*
import spaceapps.repository.Repository
import spaceapps.controller.Api
import spaceapps.integrations.grpc.GrpcServer
import spaceapps.integrations.grpc.v1.{ObservationMetadataRequest,EquipmentRequest,CalibrationFileRequest}
import spaceapps.integrations.grpc.v1.ZioRetrieval.RetrievalServiceClient
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder
import scalapb.zio_grpc.ZManagedChannel
import zio.*
import zio.http.*
import zio.json.*
import zio.json.ast.Json
import zio.test.*
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.nio.file.{Files,Paths}
import java.nio.charset.StandardCharsets.UTF_8

object ArchiveDetailsApiSpec extends ZIOSpecDefault:
  private val yaml = "detectors:\n  1: [1.0, 2.0]\n"
  private def field(value:Json,name:String):Json=value.asObject.flatMap(_.get(name)).getOrElse(Json.Null)
  private def fixture[A](use:(Api,RetrievalServiceClient)=>ZIO[Scope,Throwable,A],fileStatus:Int=200):ZIO[Scope & Client,Throwable,A]=
    for
      dir <- ZIO.attempt(Files.createTempDirectory("details-api-"))
      server <- ZIO.acquireRelease(ZIO.attempt {
        val s=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
        s.createContext("/",ex=>{
          val query=Option(ex.getRequestURI.getQuery).getOrElse("")
          val body=if ex.getRequestURI.getPath=="/tap" then
            "<VOTABLE><RESOURCE><INFO name=\"QUERY_STATUS\" value=\"OK\"/><TABLE>"+
              "<FIELD name=\"contentchecksum\" datatype=\"char\" arraysize=\"*\"/><FIELD name=\"contentlength\" datatype=\"long\" unit=\"byte\"/><FIELD name=\"quality_flag\" datatype=\"char\" arraysize=\"*\"/>"+
              "<DATA><TABLEDATA><TR><TD>md5:abc</TD><TD>2880</TD><TD></TD></TR></TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>"
          else if query.contains("list-type=2") then
            val contents=if query.contains("gain_factors/") then
              s"<Contents><Key>dr1/gain_factors/base-2026-191/gain_factors_spx_base-2026-191.yaml</Key><Size>${yaml.getBytes(UTF_8).length}</Size></Contents>"
            else "<CommonPrefixes><Prefix>dr1/gain_factors/</Prefix></CommonPrefixes>"
            s"<ListBucketResult><IsTruncated>false</IsTruncated>$contents</ListBucketResult>"
          else yaml
          val bytes=body.getBytes(UTF_8)
          val status=if ex.getRequestURI.getPath=="/tap" || query.contains("list-type=2") then 200 else fileStatus
          ex.sendResponseHeaders(status,bytes.length)
          try ex.getResponseBody.write(bytes) finally ex.close()
        })
        s.start();s
      })(s=>ZIO.succeed(s.stop(0)))
      base=s"http://127.0.0.1:${server.getAddress.getPort}"
      image=ArchiveImage(Observation("known-frame","2025-04-29T00:00:00Z",1,"DR1",header_metadata=Map(
        "obs_publisher_did"->Json.Str("ivo://irsa/frame"),"obs_collection"->Json.Str("spherex_dr1"),
        "access_url"->Json.Str(base+"/dr1/frame.fits"))),base+"/dr1/frame.fits")
      repo <- Repository.open(dir.resolve("jobs.sqlite"))
      source=new Archive:
        def search(q:Query)=ZIO.succeed(List(image))
        def fetch(i:ArchiveImage,p:java.nio.file.Path)=ZIO.fail(ApiError("unexpected_download","Metadata must not download a science image"))
      jobs <- Jobs.make(repo,source,NoProcessing,dir)
      client <- ZIO.service[Client]
      metadata <- MetadataService.make(repo,jobs.cachedImage,client,base+"/tap")
      equipment <- EquipmentService.make(repo,dir,client,base+"/")
      api <- Api.make(jobs,"details-test",Paths.get("docs/openapi.yaml"),metadata=Some(metadata),equipment=Some(equipment))
      port <- GrpcServer.start(jobs,"details-test","127.0.0.1",0,metadata=Some(metadata),equipment=Some(equipment))
      grpc <- RetrievalServiceClient.scoped(ZManagedChannel(NettyChannelBuilder.forAddress("127.0.0.1",port).usePlaintext()))
      _ <- repo.remember(List(image))
      result <- use(api,grpc)
    yield result
  def spec=suite("Archive details transport contract")(
    test("archive transfer failures are unavailable responses instead of client validation errors") {
      ZIO.scoped(fixture({ (api,grpc)=>
        for
          response <- api.routes.runZIO(Request.get("http://localhost/api/equipment"))
          text <- response.body.asString
          document <- ZIO.fromEither(text.fromJson[Json]).mapError(new RuntimeException(_))
          product=field(document,"calibration_products").asArray.get.head
          id=field(product,"id").asString.get
          download <- api.routes.runZIO(Request.get("http://localhost"+field(product,"download_url").asString.get))
          rpc <- grpc.getCalibrationFile(CalibrationFileRequest(id)).runCollect.either
        yield assertTrue(download.status==Status.ServiceUnavailable,
          rpc.left.exists(_.getStatus.getCode==io.grpc.Status.Code.UNAVAILABLE))
      },fileStatus=503))
    },
    test("frame metadata is reachable by known ID through HTTP and gRPC without downloading science bytes") {
      ZIO.scoped(fixture { (api,grpc)=>
        for
          response <- api.routes.runZIO(Request.get("http://localhost/api/observations/meta?frame_id=known-frame"))
          text <- response.body.asString
          document <- ZIO.fromEither(text.fromJson[Json]).mapError(new RuntimeException(_))
          rpc <- grpc.getObservationMetadata(ObservationMetadataRequest("known-frame"))
          absent <- api.routes.runZIO(Request.get("http://localhost/api/observations/meta?frame_id=missing"))
          missingParameter <- api.routes.runZIO(Request.get("http://localhost/api/observations/meta"))
        yield assertTrue(response.status==Status.Ok,field(document,"frame_id")==Json.Str("known-frame"),
          field(field(document,"tap"),"status")==Json.Str("available"),
          field(field(document,"fits"),"status")==Json.Str("not_downloaded"),
          rpc.metadata.exists(_.fields("frame_id").getStringValue=="known-frame"),
          absent.status==Status.NotFound,missingParameter.status==Status.UnprocessableEntity)
      })
    },
    test("equipment JSON identifies files whose original bytes both transports actually serve") {
      ZIO.scoped(fixture { (api,grpc)=>
        for
          response <- api.routes.runZIO(Request.get("http://localhost/api/equipment?release=DR1&detector_array=1"))
          text <- response.body.asString
          document <- ZIO.fromEither(text.fromJson[Json]).mapError(new RuntimeException(_))
          product=field(document,"calibration_products").asArray.get.head
          id=field(product,"id").asString.get
          url=field(product,"download_url").asString.get
          download <- api.routes.runZIO(Request.get("http://localhost"+url))
          bytes <- download.body.asString
          rpc <- grpc.getCalibrationFile(CalibrationFileRequest(id)).runCollect
          rpcEquipment <- grpc.getEquipment(EquipmentRequest("DR1",Some(1)))
        yield assertTrue(response.status==Status.Ok,download.status==Status.Ok,bytes==yaml,
          new String(rpc.flatMap(_.data.toByteArray).toArray,UTF_8)==yaml,
          rpcEquipment.equipment.exists(_.fields("release").getStringValue=="DR1"))
      })
    },
    test("invalid equipment filters are client errors and unknown file IDs remain not found") {
      ZIO.scoped(fixture { (api,grpc)=>
        for
          bad <- api.routes.runZIO(Request.get("http://localhost/api/equipment?release=unknown"))
          absent <- api.routes.runZIO(Request.get("http://localhost/api/equipment/calibrations/missing"))
          rpc <- grpc.getEquipment(EquipmentRequest("unknown")).either
        yield assertTrue(bad.status==Status.UnprocessableEntity,absent.status==Status.NotFound,
          rpc.left.exists(_.getStatus.getCode==io.grpc.Status.Code.INVALID_ARGUMENT))
      })
    }
  ).provideLayerShared(Client.default)
