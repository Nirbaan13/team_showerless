package spaceapps.catalogs.controller

import spaceapps.catalogs.service.Catalogs
import spaceapps.infra.model.ApiError
import spaceapps.infra.controller.HttpResponses.{json,safe}
import zio.*
import zio.http.*
import zio.json.*
import zio.json.ast.Json

final class CatalogApi(service:Option[Catalogs]):
  private def query(request:Request):Task[Response]=for
    values<-ZIO.attempt {
      def one(key:String,default:Option[String]=None):String=
        val all=request.url.queryParams.getAll(key)
        if all.size>1 then throw ApiError("invalid_request",s"$key must appear once")
        all.headOption.orElse(default).getOrElse(throw ApiError("invalid_request",s"$key is required"))
      def number(key:String,low:Double,high:Double,default:Option[String]=None):Double=
        val value=scala.util.Try(one(key,default).toDouble).getOrElse(throw ApiError("invalid_request",s"$key must be numeric"))
        if !value.isFinite || value<low || value>high || (key=="ra" && value==360) then throw ApiError("invalid_request",s"Invalid $key")
        value
      val candidate=Option(one("candidate_id",Some(""))).filter(_.nonEmpty)
      if candidate.exists(s=>s.length>256 || s.exists(_.isControl)) then throw ApiError("invalid_request","Invalid candidate_id")
      (number("ra",0,360),number("dec",-90,90),number("fov_arcmin",.01,30,Some("5")),candidate)
    }
    catalogs<-ZIO.fromOption(service).orElseFail(ApiError("service_unavailable","Live catalogue queries are not configured",true))
    result<-catalogs.query(values._1,values._2,values._3,values._4)
  yield Response.json(result._1.toJson).status(if result._2 then Status.ServiceUnavailable else Status.Ok).addHeader("Cache-Control","no-store")
  val routes=Routes(Method.GET / "api" / "motion" / "catalog" -> handler((r:Request)=>safe(query(r))))
