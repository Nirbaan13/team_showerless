package spaceapps.bootstrap

import spaceapps.controller.Api
import spaceapps.domain.*
import spaceapps.integrations.irsa.LiveArchive
import spaceapps.integrations.grpc.GrpcServer
import spaceapps.repository.Repository
import spaceapps.service.*

import zio.{Chunk as _, *}
import zio.http.*
import zio.json.*
import java.nio.file.{Files,Path}

object Main extends ZIOAppDefault:
  private def env(name:String,default:String):String=java.lang.System.getenv().getOrDefault(name,default)
  def run=ZIO.scoped {
    for
      data <- ZIO.attempt(Path.of(env("DATA_DIR","data")).toAbsolutePath)
      _ <- ZIO.attemptBlocking(Files.createDirectories(data))
      client <- ZIO.service[Client]
      bands <- ZIO.fromEither(env("CHANNEL_BANDS_JSON","{}").fromJson[Map[String,List[Double]]]).mapError(_=>ApiError("invalid_configuration","CHANNEL_BANDS_JSON must be a JSON mapping of channel numbers to wavelength intervals in meters"))
      channelBands <- ZIO.attempt {
        bands.map { (key,values)=>
          val index=key.toInt
          require(index>=1 && index<=102 && values.size==2 && values.forall(v=>v.isFinite && v>0) && values(0)<values(1),"Invalid channel wavelength mapping")
          index -> (values(0),values(1))
        }
      }
      source = new LiveArchive(client,env("IRSA_SIA_URL","https://irsa.ipac.caltech.edu/SIA"),env("MAX_OBSERVATIONS","256").toInt,env("MAX_PRODUCT_BYTES","268435456").toLong,channelBands)
      archive <- CapacityArchive.make(source,data,env("MAX_CACHE_BYTES","21474836480").toLong,env("MAX_PRODUCT_BYTES","268435456").toLong,env("MIN_FREE_BYTES","536870912").toLong)
      repository <- Repository.open(data.resolve("jobs.sqlite"))
      jobs <- Jobs.make(repository,archive,NoProcessing,data,env("WORKERS","2").toInt,env("TRANSFERS","4").toInt,env("MAX_ACTIVE_JOBS","32").toInt)
      api <- Api.make(jobs,env("APP_REVISION","development"),Path.of(env("OPENAPI_PATH","docs/openai/openapi.yaml")),channelBands.keySet)
      grpcPort <- GrpcServer.start(jobs,env("APP_REVISION","development"),env("GRPC_HOST","0.0.0.0"),env("GRPC_PORT","50051").toInt,channelBands.keySet)
      _ <- ZIO.logInfo(s"gRPC listener started on port $grpcPort")
      _ <- ZIO.logInfo(s"Starting IRSA retrieval service, revision ${env("APP_REVISION","development")}")
      _ <- Server.serve(api.routes)
    yield ()
  }.provide(Client.default,Server.defaultWithPort(env("PORT","8000").toInt))
