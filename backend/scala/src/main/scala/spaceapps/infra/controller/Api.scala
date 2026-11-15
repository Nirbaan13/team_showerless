package spaceapps.infra.controller
import spaceapps.irsa.service.{Jobs,MetadataService}
import spaceapps.irsa.controller.IrsaApi
import spaceapps.equipment.service.EquipmentService
import spaceapps.equipment.controller.EquipmentApi
import spaceapps.processing.integrations.HttpPipelineClient
import spaceapps.processing.controller.PipelineApi
import spaceapps.catalogs.controller.CatalogApi
import spaceapps.catalogs.service.Catalogs
import spaceapps.controller.LegacyAnalysisRoutes
import spaceapps.service.Analyses
import spaceapps.infra.controller.HttpResponses.{json as respond,safe}
import zio.*
import zio.http.*
import zio.json.*
import zio.json.ast.Json
import java.nio.file.{Files,Path as FilePath}
import org.yaml.snakeyaml.{Yaml,LoaderOptions}
import org.yaml.snakeyaml.constructor.SafeConstructor
import scala.jdk.CollectionConverters.*
final class Api private(jobs:Jobs,revision:String,specification:String,openapi:Json,channels:Set[Int],
  metadata:Option[MetadataService],equipment:Option[EquipmentService],analyses:Option[Analyses],pipeline:Option[HttpPipelineClient],catalogs:Option[Catalogs]):
  private def capabilities:Task[Response]=for
    worker<-pipeline.fold[UIO[Boolean]](ZIO.succeed(false))(_.healthy)
    model<-analyses.fold[UIO[Json]](ZIO.succeed(Json.Null))(_.models.orElseSucceed(Json.Null))
  yield Response.json(Json.Obj("revision"->Json.Str(revision),
    "pipeline"->Json.Obj("available"->Json.Bool(worker)),"motion_models"->model,
    "motion_analysis"->Json.Obj("status"->Json.Str(if model==Json.Null then "unavailable" else "supported"),"endpoint"->Json.Str("/api/analyses/motion")),
    "native_epoch_difference"->Json.Obj("status"->Json.Str("unsupported")),
    "native_zodi_subtraction"->Json.Obj("status"->Json.Str("unsupported")),
    "live_catalogs"->Json.Obj("configured"->Json.Bool(catalogs.nonEmpty),"endpoint"->Json.Str("/api/motion/catalog"),"availability"->Json.Str("reported_per_provider_per_request")),
    "legacy_motion_service"->Json.Obj("status"->Json.Str("unsupported")),
    "community_catalogue"->Json.Obj("status"->Json.Str("unsupported")),
    "external_submission"->Json.Obj("status"->Json.Str("disabled"))).toJson).addHeader("Cache-Control","no-store")
  private val documentation=Routes(
    Method.GET / Root -> handler(respond(Map("service"->"SPHEREx Backend API","version"->revision,"docs"->"/docs"))),
    Method.GET / "health" -> handler(respond(Map("status"->"ok","revision"->revision))),
    Method.GET / "version" -> handler(respond(Map("version"->revision))),
    Method.GET / "api" / "capabilities" -> handler(safe(capabilities)),
    Method.GET / "openapi.json" -> handler(Response.json(openapi.toJson)),
    Method.GET / "openapi.yaml" -> handler(Response.text(specification).addHeader("Content-Type","application/yaml")),
    Method.GET / "docs" -> handler(Response.text(Api.swagger).addHeader("Content-Type","text/html; charset=UTF-8"))
  )
  private val retrieval=documentation ++ new IrsaApi(jobs,channels,metadata).routes ++ new EquipmentApi(equipment).routes
  private val analysis=analyses.fold(retrieval)(s=>retrieval ++ LegacyAnalysisRoutes.routes(s))
  private val processing=pipeline.fold(analysis)(s=>analysis ++ new PipelineApi(s).routes)
  val routes:Routes[Any,Response]=processing ++ new CatalogApi(catalogs).routes ++ new LegacyUiApi().routes

object Api:
  private def ast(value:Any):Json=value match
    case null=>Json.Null
    case m:java.util.Map[?,?]=>Json.Obj(zio.Chunk.fromIterable(m.asScala.toList.map((k,v)=>k.toString->ast(v))))
    case l:java.util.List[?]=>Json.Arr(zio.Chunk.fromIterable(l.asScala.toList.map(ast)))
    case b:java.lang.Boolean=>Json.Bool(b.booleanValue())
    case n:java.lang.Number=>Json.Num(new java.math.BigDecimal(n.toString))
    case s=>Json.Str(s.toString)
  def make(jobs:Jobs,revision:String,path:FilePath,channels:Set[Int]=Set.empty,
    metadata:Option[MetadataService]=None,equipment:Option[EquipmentService]=None,analyses:Option[Analyses]=None,pipeline:Option[HttpPipelineClient]=None,catalogs:Option[Catalogs]=None):Task[Api]=ZIO.attemptBlocking {
    val text=Files.readString(path)
    val options=new LoaderOptions();options.setAllowDuplicateKeys(false)
    val document=new Yaml(new SafeConstructor(options)).load[java.util.Map[String,Object]](text)
    document.get("info").asInstanceOf[java.util.Map[String,Object]].put("version",revision)
    document.put("servers",java.util.List.of(java.util.Map.of("url","/")))
    val paths=document.get("paths").asInstanceOf[java.util.Map[String,java.util.Map[String,java.util.Map[String,Object]]]]
    List("/api/observations/zodi-reference-subtracted","/api/observations/epoch-difference").foreach { p=>
      val operation=paths.get(p).get("get")
      operation.put("description","The existing pipeline HTTP API does not provide this native-FITS processing operation. Returns HTTP501.")
      operation.get("responses").asInstanceOf[java.util.Map[String,Object]].put("501",java.util.Map.of("description","Processing is not implemented yet"))
    }
    new Api(jobs,revision,text,ast(document),channels,metadata,equipment,analyses,pipeline,catalogs)
  }
  private val swagger="""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SPHEREx API</title><link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.35.0/swagger-ui.css"></head><body><div id="swagger-ui"></div><script src="https://unpkg.com/swagger-ui-dist@5.35.0/swagger-ui-bundle.js"></script><script>SwaggerUIBundle({url:'openapi.json',dom_id:'#swagger-ui'});</script></body></html>"""
