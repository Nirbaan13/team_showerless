package spaceapps.unification

import spaceapps.domain.ApiError
import zio.*
import zio.http.*
import zio.json.*
import zio.json.ast.Json
import java.nio.charset.StandardCharsets.UTF_8

final class UnificationApi(service:Unifications):
  private def json(value:UnificationJob,status:Status=Status.Ok)=Response.json(value.toJson).status(status).addHeader("Cache-Control","no-store")
  private def safe[R](work:ZIO[R,Throwable,Response]):ZIO[R,Nothing,Response]=work.catchAll { t=>
    val e=ApiError.from(t)
    val status=e.code match
      case "not_found"=>Status.NotFound
      case "artifact_unavailable"=>Status.Conflict
      case "capacity_exceeded" | "cache_capacity"=>Status.ServiceUnavailable
      case "internal_error" | "storage_error"=>Status.InternalServerError
      case _=>Status.UnprocessableEntity
    ZIO.succeed(Response.json(e.toJson).status(status).addHeader("Cache-Control","no-store"))
  }
  private def submit(request:Request):Task[Response]=for
    bytes <- request.body.asStream.take(65537).runCollect
    _ <- ZIO.fail(ApiError("invalid_request","Request body exceeds 64 KiB")).when(bytes.size>65536)
    parsed <- ZIO.fromEither(new String(bytes.toArray,UTF_8).fromJson[Json]).mapError(_=>ApiError("invalid_request","Expected valid JSON"))
    job <- service.submit(parsed)
  yield json(job,Status.Accepted).addHeader("Location",job.status_url)
  private def artifact(id:String):ZIO[Scope,Throwable,Response]=for
    path <- service.artifact(id)
    body <- Body.fromFile(path.toFile)
  yield Response(body=body).addHeader("Content-Type","application/octet-stream").addHeader("Content-Disposition",s"attachment; filename=\"$id.npz\"").addHeader("Cache-Control","no-store")
  val routes:Routes[Any,Response]=Routes(
    Method.POST / "api" / "image-unifications" -> handler((request:Request)=>safe(submit(request))),
    Method.GET / "api" / "image-unifications" / string("id") -> handler((id:String,request:Request)=>safe(service.get(id).map(json(_)))),
    Method.GET / "api" / "image-unifications" / string("id") / "artifact" -> Handler.scoped[Any](handler((id:String,request:Request)=>safe(artifact(id))))
  )
