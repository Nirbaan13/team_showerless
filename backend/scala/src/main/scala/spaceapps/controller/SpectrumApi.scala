package spaceapps.controller

import spaceapps.domain.ApiError
import spaceapps.service.*
import zio.*
import zio.http.*
import zio.json.*

final class SpectrumApi(service:SpectrumService):
  private val names=Set("ra","dec","radius_pix","subtraction","size_arcmin","max_frames","candidate_id",
    "download_id","detector_array","observed_after","observed_before")
  private def get(request:Request):Task[Response]=
    for
      values<-ZIO.attempt {
        names.flatMap { name=>
          val all=request.url.queryParams.getAll(name)
          if all.size>1 then throw ApiError("invalid_request",s"$name must appear once")
          all.headOption.map(name->_)
        }.toMap
      }
      query<-ZIO.fromEither(SpectrumQuery.parse(values))
      reply<-service.get(query)
    yield reply match
      case SpectrumReply.Ready(result)=>Response.json(result.toJson).addHeader("Cache-Control","no-store")
      case SpectrumReply.Pending(download)=>
        val statusUrl=request.url.path.encode+"?"+request.url.queryParams.encode+
          (if values.contains("download_id") then "" else "&download_id="+download.id)
        Response.json(s"{\"id\":${download.id.toJson},\"download_id\":${download.id.toJson},\"status\":${download.status.toJson},\"status_url\":${statusUrl.toJson},\"download_status_url\":${download.status_url.toJson}}")
          .status(Status.Accepted).addHeader("Location",statusUrl).addHeader("Retry-After","2").addHeader("Cache-Control","no-store")
  val routes:Routes[Any,Response]=Routes(Method.GET / "api" / "spectrum" -> handler((r:Request)=>get(r).catchAll { error=>
    val e=ApiError.from(error)
    val status=e.code match
      case "not_found"=>Status.NotFound
      case "capacity_exceeded" | "cache_capacity" | "processing_unavailable" | "processing_capacity_exceeded" | "processing_busy"=>Status.ServiceUnavailable
      case "processing_timeout"=>Status.GatewayTimeout
      case "processing_protocol" | "internal_error"=>Status.InternalServerError
      case "no_measurements" | "processing_no_measurements"=>Status.NotFound
      case _=>Status.UnprocessableEntity
    ZIO.logWarning(s"Spectrum request failed: ${e.code}").as(Response.json(e.toJson).status(status).addHeader("Cache-Control","no-store"))
  }))
