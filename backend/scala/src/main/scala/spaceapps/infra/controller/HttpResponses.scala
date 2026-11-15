package spaceapps.infra.controller
import spaceapps.infra.model.ApiError
import zio.*
import zio.http.*
import zio.json.*
object HttpResponses:
  def json[A:JsonEncoder](value:A,status:Status=Status.Ok):Response =
    Response.json(value.toJson).status(status).addHeader("Cache-Control","no-store")
  def errorResponse(t:Throwable):Response =
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
  def safe[R](task:ZIO[R,Throwable,Response]):ZIO[R,Nothing,Response]=task.catchAll(t=>ZIO.logWarning(s"API error: ${ApiError.from(t).code}").as(errorResponse(t)))
