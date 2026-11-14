package spaceapps.controller

import spaceapps.domain.*
import spaceapps.service.{Jobs,Resource,MetadataService,EquipmentService,Analyses}

import zio.{Chunk as _, *}
import zio.http.*
import zio.json.*
import zio.json.ast.Json
import zio.stream.*
import java.nio.file.{Files,Path as FilePath}
import java.nio.charset.StandardCharsets
import org.yaml.snakeyaml.{Yaml,LoaderOptions}
import org.yaml.snakeyaml.constructor.SafeConstructor
import scala.jdk.CollectionConverters.*

final class Api private(jobs:Jobs,revision:String,specification:String,openapi:Json, channels:Set[Int],
  metadata:Option[MetadataService], equipment:Option[EquipmentService], analyses:Option[Analyses]):
  private def json[A:JsonEncoder](value:A,status:Status=Status.Ok):Response =
    Response.json(value.toJson).status(status).addHeader("Cache-Control","no-store")
  private def errorResponse(t:Throwable):Response =
    val e=ApiError.from(t)
    val status=e.code match
      case "not_found"=>Status.NotFound
      case "capacity_exceeded" | "cache_capacity" | "service_unavailable"=>Status.ServiceUnavailable
      case "calibration_configuration" | "calibration_cache_error" | "metadata_serialization"=>Status.InternalServerError
      case c if c.startsWith("calibration_") || c == "metadata_cache_capacity"=>Status.ServiceUnavailable
      case c if c.startsWith("archive_") && c != "archive_overflow" =>Status.ServiceUnavailable
      case "internal_error" | "storage_error"=>Status.InternalServerError
      case _=>Status.UnprocessableEntity
    json(e,status)
  private def safe[R](task:ZIO[R,Throwable,Response]):ZIO[R,Nothing,Response]=task.catchAll(t=>ZIO.logWarning(s"API error: ${ApiError.from(t).code}").as(errorResponse(t)))
  private val names=List("right_ascension_deg","declination_deg","width_arcmin","height_arcmin","detector_array","channel_index","observed_after","observed_before","right_ascension_min_deg","right_ascension_max_deg","declination_min_deg","declination_max_deg","verices_degrees","reference_frame_id","survey","frame_id","release")
  private def parameters(request:Request):Task[Map[String,String]]=ZIO.attempt {
    names.flatMap { name=>
      val values=request.url.queryParams.getAll(name)
      if values.size>1 then throw ApiError("invalid_request",s"$name must appear once")
      values.headOption.map(name->_)
    }.toMap
  }
  private def supported(query:Query):Task[Query]=
    if query.channel.exists(c=> !channels.contains(c)) then ZIO.fail(ApiError("unsupported_channel","No authoritative wavelength calibration is configured for this channel"))
    else ZIO.succeed(query)
  private def query(shape:String,request:Request):Task[Query]=parameters(request).flatMap(p=>ZIO.fromEither(Query.fromParameters(shape,p))).flatMap(supported)
  private def prepare(shape:String,request:Request):Task[Response]=
    for
      q <- query(shape,request)
      job <- jobs.submit(q,"default",None)
    yield json(job,if job.terminal then Status.Ok else Status.Accepted).addHeader("Location",job.status_url)
  private def prepareDeep(request:Request):Task[Response]=
    for
      values <- parameters(request)
      families = List(
        "default" -> List("right_ascension_deg","declination_deg","width_arcmin","height_arcmin"),
        "range" -> List("right_ascension_min_deg","right_ascension_max_deg","declination_min_deg","declination_max_deg"),
        "polygon" -> List("verices_degrees")).filter((_,keys)=>keys.exists(values.contains))
      _ <- ZIO.fail(ApiError("invalid_request","Supply exactly one geometry: center, range or polygon")).when(families.size!=1)
      q <- ZIO.fromEither(Query.fromParameters(families.head._1,values.updated("survey","deep"))).flatMap(supported)
      job <- jobs.submit(q,"default",None)
    yield json(job,if job.terminal then Status.Ok else Status.Accepted).addHeader("Location",job.status_url)
  private def observationMetadata(request:Request):Task[Response]=
    for
      values <- parameters(request)
      id <- ZIO.fromOption(values.get("frame_id").filter(_.nonEmpty)).orElseFail(ApiError("invalid_request","frame_id is required"))
      service <- ZIO.fromOption(metadata).orElseFail(ApiError("service_unavailable","Metadata service is not configured",true))
      result <- service.get(id)
    yield json(result)
  private def equipmentCatalogue(request:Request):Task[Response]=
    for
      values <- parameters(request)
      detector <- values.get("detector_array") match
        case None | Some("all") => ZIO.none
        case Some(value) => ZIO.fromOption(value.toIntOption.filter(n=>n>=1 && n<=6)).map(Some(_))
          .orElseFail(ApiError("invalid_request","detector_array must be all or an integer from1 to6"))
      service <- ZIO.fromOption(equipment).orElseFail(ApiError("service_unavailable","Equipment service is not configured",true))
      result <- service.catalog(values.getOrElse("release","DR1"),detector)
    yield json(result)
  private def calibrationFile(id:String):Task[Response]=
    for
      service <- ZIO.fromOption(equipment).orElseFail(ApiError("service_unavailable","Equipment service is not configured",true))
      file <- service.file(id)
      body <- Body.fromFile(file.path.toFile)
      name = file.fileName.replaceAll("[^A-Za-z0-9._-]","_")
    yield Response(body=body).addHeader("Content-Type",file.contentType)
      .addHeader("Content-Disposition",s"attachment; filename=\"$name\"").addHeader("Cache-Control","private, max-age=3600")
  private def search(request:Request):Task[Response]=
    for
      bytes <- request.body.asStream.take(65537).runCollect
      _ <- ZIO.fail(ApiError("invalid_request","Search body exceeds 64 KiB")).when(bytes.size>65536)
      q <- ZIO.fromEither(Query.fromJson(new String(bytes.toArray,StandardCharsets.UTF_8))).flatMap(supported)
      observations <- jobs.search(q)
    yield Response.json(s"{\"observations\":${observations.toJson}}")
  private def resource(id:String,preview:Boolean):ZIO[Scope,Throwable,Response]=jobs.leasedResource(id,preview).flatMap {
    case Resource.Pending=>ZIO.succeed(Response.json(s"{\"id\":${id.toJson},\"status\":\"pending\"}").status(Status.Accepted).addHeader("Retry-After","1").addHeader("Cache-Control","no-store"))
    case Resource.Failed(error)=>ZIO.succeed(json(error,Status.Conflict))
    case Resource.Ready(path)=>Body.fromFile(path.toFile).map { body=>
      Response(body=body).addHeader("Content-Type",if preview then "image/png" else "application/fits")
        .addHeader("Content-Disposition",s"inline; filename=\"$id.${if preview then "png" else "fits"}\"")
        .addHeader("Cache-Control","private, max-age=3600")
    }
  }
  private def events(id:String):Task[Response]=
    jobs.get(id).as {
      val stream=jobs.events(id).map(e=>s"id: ${e.sequence}\nevent: ${e.name}\ndata: ${e.data}\n\n")
      Response(body=Body.fromStreamChunked(stream.mapConcat(_.getBytes(StandardCharsets.UTF_8))))
        .addHeader("Content-Type","text/event-stream").addHeader("Cache-Control","no-store")
        .addHeader("X-Accel-Buffering","no")
    }
  private def deferred:Response=json(ApiError("unsupported_processing","PNG previews and scientific processing are deferred until the team supplies its pipeline"),Status.NotImplemented)
  private val retrievalRoutes:Routes[Any,Response]=Routes(
    Method.GET / Root -> handler(json(Map("service"->"SPHEREx Backend API","version"->revision,"docs"->"/docs"))),
    Method.GET / "health" -> handler(json(Map("status"->"ok","revision"->revision))),
    Method.GET / "version" -> handler(json(Map("version"->revision))),
    Method.GET / "openapi.json" -> handler(Response.json(openapi.toJson)),
    Method.GET / "openapi.yaml" -> handler(Response.text(specification).addHeader("Content-Type","application/yaml")),
    Method.GET / "docs" -> handler(Response.text(Api.swagger).addHeader("Content-Type","text/html; charset=UTF-8")),
    Method.POST / "api" / "observations" / "search" -> handler((r:Request)=>safe(search(r))),
    Method.GET / "api" / "observations" / "meta" -> handler((r:Request)=>safe(observationMetadata(r))),
    Method.GET / "api" / "equipment" -> handler((r:Request)=>safe(equipmentCatalogue(r))),
    Method.GET / "api" / "equipment" / "calibrations" / string("id") -> handler((id:String,r:Request)=>safe(calibrationFile(id))),
    Method.GET / "api" / "observationsDeep" -> handler((r:Request)=>safe(prepareDeep(r))),
    Method.GET / "api" / "observations" / "default" -> handler((r:Request)=>safe(prepare("default",r))),
    Method.GET / "api" / "observations" / "range" -> handler((r:Request)=>safe(prepare("range",r))),
    Method.GET / "api" / "observations" / "polygon" -> handler((r:Request)=>safe(prepare("polygon",r))),
    Method.GET / "api" / "observations" / "zodi-reference-subtracted" -> handler(deferred),
    Method.GET / "api" / "observations" / "epoch-difference" -> handler(deferred),
    Method.GET / "api" / "downloads" / string("id") -> handler((id:String,r:Request)=>safe(jobs.get(id).map(json(_)))),
    Method.GET / "api" / "downloads" / string("id") / "events" -> handler((id:String,r:Request)=>safe(events(id))),
    Method.GET / "api" / "chunks" / string("id") -> Handler.scoped[Any](handler((id:String,r:Request)=>safe(resource(id,false)))),
    Method.GET / "api" / "chunks" / string("id") / "preview" -> Handler.scoped[Any](handler((id:String,r:Request)=>safe(resource(id,true))))
  )

  val routes:Routes[Any,Response]=analyses.fold(retrievalRoutes)(s=>retrievalRoutes ++ new AnalysisApi(s).routes)

object Api:
  private def ast(value:Any):Json=value match
    case null=>Json.Null
    case m:java.util.Map[?,?]=>Json.Obj(zio.Chunk.fromIterable(m.asScala.toList.map((k,v)=>k.toString->ast(v))))
    case l:java.util.List[?]=>Json.Arr(zio.Chunk.fromIterable(l.asScala.toList.map(ast)))
    case b:java.lang.Boolean=>Json.Bool(b.booleanValue())
    case n:java.lang.Number=>Json.Num(new java.math.BigDecimal(n.toString))
    case s=>Json.Str(s.toString)
  def make(jobs:Jobs,revision:String,path:FilePath,channels:Set[Int]=Set.empty,
    metadata:Option[MetadataService]=None,equipment:Option[EquipmentService]=None,analyses:Option[Analyses]=None):Task[Api]=ZIO.attemptBlocking {
    val text=Files.readString(path)
    val options=new LoaderOptions();options.setAllowDuplicateKeys(false)
    val document=new Yaml(new SafeConstructor(options)).load[java.util.Map[String,Object]](text)
    document.get("info").asInstanceOf[java.util.Map[String,Object]].put("version",revision)
    document.put("servers",java.util.List.of(java.util.Map.of("url","/")))
    val paths=document.get("paths").asInstanceOf[java.util.Map[String,java.util.Map[String,java.util.Map[String,Object]]]]
    List("/api/observations/zodi-reference-subtracted","/api/observations/epoch-difference").foreach { p=>
      val operation=paths.get(p).get("get")
      operation.put("description","Deferred: scientific pipeline is not available yet. Returns HTTP501.")
      operation.get("responses").asInstanceOf[java.util.Map[String,Object]].put("501",java.util.Map.of("description","Processing is not implemented yet"))
    }
    new Api(jobs,revision,text,ast(document),channels,metadata,equipment,analyses)
  }
  private val swagger="""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SPHEREx API</title><link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.35.0/swagger-ui.css"></head><body><div id="swagger-ui"></div><script src="https://unpkg.com/swagger-ui-dist@5.35.0/swagger-ui-bundle.js"></script><script>SwaggerUIBundle({url:'/openapi.json',dom_id:'#swagger-ui'});</script></body></html>"""
