package spaceapps.processing.controller

import spaceapps.infra.model.ApiError
import spaceapps.processing.integrations.HttpPipelineClient
import zio.*
import zio.http.*
import zio.json.*
import zio.json.ast.Json
import java.nio.charset.StandardCharsets.UTF_8

/** Validation and transport live in Scala. Python's existing API is unchanged. */
final class PipelineApi(client:HttpPipelineClient):
  private def invalid(message:String):Nothing=throw ApiError("invalid_request",message)
  private def numeric(value:String,name:String,low:Double,high:Double,exclusive:Boolean=false):Double=
    val n=scala.util.Try(value.toDouble).getOrElse(invalid(s"$name must be numeric"))
    if !n.isFinite || n<low || n>high || (exclusive && n==high) then invalid(s"$name outside supported range")
    n
  private def coordinates(values:Map[String,String]):Unit=
    numeric(values.getOrElse("ra",invalid("ra is required")),"ra",0,360,true)
    numeric(values.getOrElse("dec",invalid("dec is required")),"dec",-90,90)
    ()
  private def query(request:Request,spectrum:Boolean):Task[String]=ZIO.attempt {
    val names=if spectrum then Set("ra","dec","radius_pix","size_arcmin","max_frames","candidate_id","subtraction")
      else Set("ra","dec","size_arcmin","subtraction")
    val values=names.flatMap { name=>
      val all=request.url.queryParams.getAll(name)
      if all.size>1 then invalid(s"$name must appear once")
      all.headOption.map(name->_)
    }.toMap
    coordinates(values)
    values.get("size_arcmin").foreach(v=>numeric(v,"size_arcmin",if spectrum then .5 else .01,if spectrum then 10 else 600))
    values.get("radius_pix").foreach(v=>numeric(v,"radius_pix",.5,10))
    values.get("max_frames").foreach { v=>if !numeric(v,"max_frames",1,400).isWhole then invalid("max_frames must be an integer") }
    values.get("candidate_id").foreach(v=>if v.length>256 || v.exists(_.isControl) then invalid("candidate_id is invalid"))
    values.get("subtraction").foreach { v=>
      if !Set("raw_calibrated","zodi_subtracted").contains(v) then invalid("Unsupported subtraction mode")
      if spectrum && v!="zodi_subtracted" then invalid("The existing Python spectrum endpoint supports zodi_subtracted only")
    }
    values.toList.sortBy(_._1).map((k,v)=>java.net.URLEncoder.encode(k,UTF_8)+"="+java.net.URLEncoder.encode(v,UTF_8)).mkString("&")
  }
  private def payload(request:Request,measure:Boolean):Task[Json]=
    for
      bytes<-request.body.asStream.take(65537).runCollect
      _<-ZIO.fail(ApiError("invalid_request","Pipeline request body exceeds 64 KiB")).when(bytes.size>65536)
      document<-ZIO.fromEither(new String(bytes.toArray,UTF_8).fromJson[Json]).mapError(_=>ApiError("invalid_request","Expected a JSON object"))
      valid<-ZIO.attempt {
        val pairs=document match
          case Json.Obj(values)=>values
          case _=>invalid("Expected a JSON object")
        if pairs.map(_._1).distinct.size!=pairs.size then invalid("JSON properties must appear once")
        val fields=pairs.toMap
        val allowed=if measure then Set("ra","dec","radius_pix","cutout_paths") else Set("ra","dec","size_arcmin","collection","detector_array")
        if fields.keys.exists(!allowed.contains(_)) then invalid("Unsupported pipeline request property")
        val text=fields.map((k,v)=>k->(v match
          case Json.Str(s)=>s
          case Json.Num(n)=>n.toString
          case _=>"invalid")).toMap
        coordinates(text)
        if measure then
          text.get("radius_pix").foreach(v=>numeric(v,"radius_pix",.5,10))
          fields.get("cutout_paths").foreach { values=>
            val names=values.asArray.getOrElse(invalid("cutout_paths must be an array"))
            if names.size>120 || names.exists(v=> !v.asString.exists(s=>s.nonEmpty && s.length<=256 && s.matches("[A-Za-z0-9_.-]+") && !s.contains(".."))) then
              invalid("Supply at most120 cache filenames without directories")
          }
        else
          text.get("size_arcmin").foreach(v=>numeric(v,"size_arcmin",.01,600))
          text.get("collection").foreach(v=>if !v.matches("spherex_[a-z0-9_]{1,32}") then invalid("Unsupported collection"))
          if fields.contains("detector_array") then invalid("The existing Python cutout search does not implement detector filtering")
        document
      }
    yield valid
  private def relay(method:String,path:String,request:Request):Task[Response]=
    for
      params<-if method=="GET" then query(request,path=="/api/spectrum") else ZIO.succeed("")
      body<-if method=="POST" then payload(request,path.endsWith("/measure")).map(Some(_)) else ZIO.none
      result<-client.request(method,path,params,body)
    yield Response(body=Body.fromChunk(zio.Chunk.fromArray(result.bytes))).addHeader("Content-Type",result.contentType)
      .addHeader("Cache-Control","no-store")
  private def safe(effect:Task[Response]):UIO[Response]=effect.catchAll { error=>
    val e=ApiError.from(error)
    val status=e.code match
      case "invalid_request" | "pipeline_invalid_request"=>Status.UnprocessableEntity
      case "pipeline_not_found"=>Status.NotFound
      case "pipeline_timeout"=>Status.GatewayTimeout
      case "pipeline_unavailable"=>Status.ServiceUnavailable
      case _=>Status.BadGateway
    ZIO.logWarning(s"Pipeline request failed: ${e.code}").as(Response.json(e.toJson).status(status).addHeader("Cache-Control","no-store"))
  }
  val routes:Routes[Any,Response]=Routes(
    Method.GET / "api" / "spectrum" -> handler((r:Request)=>safe(relay("GET","/api/spectrum",r))),
    Method.POST / "api" / "spectrum" / "measure" -> handler((r:Request)=>safe(relay("POST","/api/spectrum/measure",r))),
    Method.POST / "api" / "cutout" / "search" -> handler((r:Request)=>safe(relay("POST","/api/cutout/search",r))),
    Method.GET / "api" / "cutout" / "render" -> handler((r:Request)=>safe(relay("GET","/api/cutout/render",r)))
  )
