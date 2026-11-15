package spaceapps.processing.controller

import spaceapps.processing.integrations.HttpHistoricalMotionClient
import spaceapps.processing.service.Unifications
import spaceapps.infra.model.ApiError
import zio.*
import zio.http.*
import zio.json.*
import zio.json.ast.Json
import java.nio.charset.StandardCharsets.UTF_8

final class HistoricalMotionApi(unifications:Unifications,client:HttpHistoricalMotionClient):
  private def search(request:Request):ZIO[Scope,Throwable,Response]=for
    bytes <- request.body.asStream.take(4097).runCollect
    _ <- ZIO.fail(ApiError("invalid_request","Motion request exceeds 4 KiB")).when(bytes.size>4096)
    parsed <- ZIO.fromEither(new String(bytes.toArray,UTF_8).fromJson[Json]).mapError(_=>ApiError("invalid_request","Expected valid JSON"))
    id <- ZIO.fromEither(HistoricalMotionApi.selection(parsed))
    artifact <- unifications.artifact(id)
    review <- client.prepared(id,artifact)
  yield Response.json(review.toJson).addHeader("Cache-Control","no-store")
  private def safe(work:ZIO[Scope,Throwable,Response]):ZIO[Scope,Nothing,Response]=work.catchAll { t=>
    val e=ApiError.from(t)
    val status=e.code match
      case "unsupported_legacy_operation"=>Status.NotImplemented
      case "not_found"=>Status.NotFound
      case "artifact_unavailable" | "source_changed"=>Status.Conflict
      case "motion_unavailable"=>Status.ServiceUnavailable
      case "motion_timeout"=>Status.GatewayTimeout
      case "motion_protocol" | "motion_upstream_error"=>Status.BadGateway
      case _=>Status.UnprocessableEntity
    ZIO.succeed(Response.json(e.toJson).status(status).addHeader("Cache-Control","no-store"))
  }
  val routes:Routes[Any,Response]=Routes(
    Method.POST / "api" / "motion" / "search" -> Handler.scoped[Any](handler((request:Request)=>safe(search(request))))
  )

object HistoricalMotionApi:
  private[processing] def selection(json:Json):Either[ApiError,String]=json match
    case Json.Obj(fields) if fields.exists(_._1=="unification_id")=>
      val values=fields.toMap
      if fields.size!=2 || values.keySet!=Set("unification_id","profile") || values.get("profile")!=Some(Json.Str("stellar_proper_motion")) then
        Left(ApiError("invalid_request","Expected only unification_id and profile stellar_proper_motion"))
      else values("unification_id") match
        case Json.Str(id) if id.matches("[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")=>Right(id)
        case _=>Left(ApiError("invalid_request","Expected a server-issued unification UUID"))
    case _=>Left(ApiError("unsupported_legacy_operation","Coordinate acquisition is unsupported; prepare downloaded observations through image-unifications"))
