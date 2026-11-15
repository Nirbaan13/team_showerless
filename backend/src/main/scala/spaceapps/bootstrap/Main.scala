package spaceapps.bootstrap

import spaceapps.controller.Api
import spaceapps.archive.controller.ArchiveApi
import spaceapps.archive.bootstrap.ArchiveRuntime
import spaceapps.archive.service.ArchiveLimits
import spaceapps.domain.*
import spaceapps.integrations.irsa.LiveArchive
import spaceapps.integrations.grpc.GrpcServer
import spaceapps.repository.{Repository,AnalysisRepository}
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
      repository <- Repository.open(data.resolve("jobs.sqlite"))
      cache <- FitsCache.open(data,data.resolve("jobs.sqlite"),env("MAX_CACHE_BYTES","21474836480").toLong,env("MAX_PRODUCT_BYTES","268435456").toLong,env("MIN_FREE_BYTES","536870912").toLong)
      archive <- CapacityArchive.make(source,data,env("MAX_CACHE_BYTES","21474836480").toLong,env("MAX_PRODUCT_BYTES","268435456").toLong,env("MIN_FREE_BYTES","536870912").toLong,Some(cache))
      jobs <- Jobs.make(repository,archive,NoProcessing,data,env("WORKERS","2").toInt,env("TRANSFERS","4").toInt,env("MAX_ACTIVE_JOBS","32").toInt)
      metadata <- MetadataService.make(repository,jobs.cachedImage,client,env("IRSA_TAP_URL","https://irsa.ipac.caltech.edu/TAP/sync"))
      equipment <- EquipmentService.make(repository,data,client,env("IRSA_CALIBRATION_URL","https://nasa-irsa-spherex.s3.amazonaws.com/"))
      analysisRepository <- AnalysisRepository.open(data.resolve("jobs.sqlite"))
      analyses <- Analyses.make(analysisRepository,jobs,data,AnalysisConfig(Path.of(env("ML_ROOT","../ml/pvusatov/backend/inference")),env("ML_PYTHON","python3")))
      api <- Api.make(jobs,env("APP_REVISION","development"),Path.of(env("OPENAPI_PATH","docs/openai/openapi.yaml")),channelBands.keySet,metadata=Some(metadata),equipment=Some(equipment),analyses=Some(analyses))
      archiveRuntime <- ArchiveRuntime.make(client,source,data,data.resolve("jobs.sqlite"),ArchiveLimits(
        global_parallelism=env("ARCHIVE_PARALLELISM","3").toInt,
        per_provider_parallelism=env("ARCHIVE_PROVIDER_PARALLELISM","1").toInt,
        request_timeout_ms=env("ARCHIVE_METADATA_TIMEOUT_MS","30000").toLong,
        search_deadline_ms=env("ARCHIVE_SEARCH_DEADLINE_MS","120000").toLong,
        metadata_bytes=env("ARCHIVE_METADATA_BYTES","8388608").toLong,
        file_bytes=math.min(env("ARCHIVE_FILE_BYTES","268435456").toLong,env("MAX_PRODUCT_BYTES","268435456").toLong),
        max_active_jobs=env("ARCHIVE_MAX_ACTIVE_JOBS","32").toInt),Some(cache))
      archiveApi=new ArchiveApi(archiveRuntime.service)
      grpcPort <- GrpcServer.start(jobs,env("APP_REVISION","development"),env("GRPC_HOST","0.0.0.0"),env("GRPC_PORT","50051").toInt,channelBands.keySet,metadata=Some(metadata),equipment=Some(equipment),analyses=Some(analyses))
      _ <- ZIO.logInfo(s"gRPC listener started on port $grpcPort")
      _ <- ZIO.logInfo(s"Starting IRSA retrieval service, revision ${env("APP_REVISION","development")}")
      _ <- Server.serve(api.routes ++ archiveApi.routes)
    yield ()
  }.provide(Client.default,Server.defaultWithPort(env("PORT","8000").toInt))
