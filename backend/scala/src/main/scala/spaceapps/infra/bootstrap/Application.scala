package spaceapps.infra.bootstrap

import spaceapps.infra.controller.Api
import spaceapps.downloads.controller.DownloadsApi
import spaceapps.downloads.bootstrap.DownloadsRuntime
import spaceapps.downloads.service.ArchiveLimits
import spaceapps.irsa.model.*
import spaceapps.irsa.integrations.{LiveArchive,ResilientArchive,S3MirrorArchive,MirrorProcess}
import spaceapps.infra.service.ExternalServices
import spaceapps.infra.integrations.ExternalServiceProbes
import spaceapps.infra.controller.ExternalHealthApi
import spaceapps.irsa.controller.IrsaDiscoveryApi
import spaceapps.irsa.integrations.grpc.GrpcServer
import spaceapps.processing.integrations.HttpPipelineClient
import spaceapps.processing.service.Unifications
import spaceapps.processing.controller.UnificationApi
import spaceapps.irsa.repository.Repository
import spaceapps.repository.AnalysisRepository
import spaceapps.infra.service.FileCache
import spaceapps.equipment.service.EquipmentService
import spaceapps.service.{Analyses,AnalysisConfig}
import spaceapps.irsa.service.*

import zio.{Chunk as _, *}
import zio.http.*
import zio.json.*
import java.nio.file.{Files,Path}

object Application:
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
      primary = new LiveArchive(client,env("IRSA_SIA_URL","https://irsa.ipac.caltech.edu/SIA"),env("MAX_OBSERVATIONS","256").toInt,env("MAX_PRODUCT_BYTES","268435456").toLong,channelBands)
      external <- ExternalServices.make(ExternalServiceProbes.irsa(client,
        env("IRSA_SIA_URL","https://irsa.ipac.caltech.edu/SIA"),env("IRSA_TAP_URL","https://irsa.ipac.caltech.edu/TAP/sync")),1.hour)
      mirror <- S3MirrorArchive.make(new MirrorProcess(env("ML_PYTHON","python3"),
        Path.of(env("IRSA_MIRROR_SCRIPT","python/irsa_mirror.py")),data.resolve("irsa-mirror.sqlite"),
        "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/",env("IRSA_MIRROR_RELEASES","qr2,dr1,qr3")),primary,env("MAX_OBSERVATIONS","256").toInt)
      source = new ResilientArchive(primary,mirror,external)
      _ <- mirror.start.when(env("IRSA_MIRROR_SCAN_ENABLED","true").toBoolean)
      _ <- FileCache.recover(data)
      repository <- Repository.open(data.resolve("jobs.sqlite"))
      cache <- FileCache.open(data,data.resolve("jobs.sqlite"),env("MAX_CACHE_BYTES","21474836480").toLong,env("MAX_PRODUCT_BYTES","268435456").toLong,env("MIN_FREE_BYTES","536870912").toLong)
      archive <- CapacityArchive.make(source,data,env("MAX_CACHE_BYTES","21474836480").toLong,env("MAX_PRODUCT_BYTES","268435456").toLong,env("MIN_FREE_BYTES","536870912").toLong,Some(cache))
      jobs <- Jobs.make(repository,archive,NoProcessing,data,env("WORKERS","2").toInt,env("TRANSFERS","4").toInt,env("MAX_ACTIVE_JOBS","32").toInt)
      metadata <- MetadataService.make(repository,jobs.cachedImage,client,env("IRSA_TAP_URL","https://irsa.ipac.caltech.edu/TAP/sync"),Some(external))
      equipment <- EquipmentService.make(repository,data,client,env("IRSA_CALIBRATION_URL","https://nasa-irsa-spherex.s3.amazonaws.com/"),capacity=Some(cache))
      analysisRepository <- AnalysisRepository.open(data.resolve("jobs.sqlite"))
      analyses <- Analyses.make(analysisRepository,jobs,data,AnalysisConfig(Path.of(env("ML_ROOT","../ml/pvusatov/backend/inference")),env("ML_PYTHON","python3")))
      pipeline <- HttpPipelineClient.make(env("PROCESSING_URL","http://pipeline:8002"))
      catalogs <- spaceapps.catalogs.service.Catalogs.make(new spaceapps.catalogs.integrations.TapCatalogs(client))
      api <- Api.make(jobs,env("APP_REVISION","development"),Path.of(env("OPENAPI_PATH","docs/openapi.yaml")),channelBands.keySet,metadata=Some(metadata),equipment=Some(equipment),analyses=Some(analyses),pipeline=Some(pipeline),catalogs=Some(catalogs))
      downloadsRuntime <- DownloadsRuntime.make(client,source,data,data.resolve("jobs.sqlite"),ArchiveLimits(
        global_parallelism=env("ARCHIVE_PARALLELISM","3").toInt,
        per_provider_parallelism=env("ARCHIVE_PROVIDER_PARALLELISM","1").toInt,
        request_timeout_ms=env("ARCHIVE_METADATA_TIMEOUT_MS","30000").toLong,
        search_deadline_ms=env("ARCHIVE_SEARCH_DEADLINE_MS","120000").toLong,
        metadata_bytes=env("ARCHIVE_METADATA_BYTES","8388608").toLong,
        file_bytes=math.min(env("ARCHIVE_FILE_BYTES","268435456").toLong,env("MAX_PRODUCT_BYTES","268435456").toLong),
        max_active_jobs=env("ARCHIVE_MAX_ACTIVE_JOBS","32").toInt),Some(cache))
      downloadsApi=new DownloadsApi(downloadsRuntime.service)
      unifications <- Unifications.make(jobs,downloadsRuntime.service,downloadsRuntime.repository,cache,data,data.resolve("jobs.sqlite"),pipeline.unify)
      unificationApi=new UnificationApi(unifications)
      grpcPort <- GrpcServer.start(jobs,env("APP_REVISION","development"),env("GRPC_HOST","0.0.0.0"),env("GRPC_PORT","50051").toInt,channelBands.keySet,metadata=Some(metadata),equipment=Some(equipment),analyses=Some(analyses))
      _ <- ZIO.logInfo(s"gRPC listener started on port $grpcPort")
      _ <- ZIO.logInfo(s"Starting IRSA retrieval service, revision ${env("APP_REVISION","development")}")
      _ <- Server.serve(api.routes ++ downloadsApi.routes ++ unificationApi.routes ++ new IrsaDiscoveryApi(source,repository).routes ++ new ExternalHealthApi(external,mirror.status).routes)
    yield ()
  }.provide(Client.default,Server.defaultWithPort(env("PORT","8000").toInt))
