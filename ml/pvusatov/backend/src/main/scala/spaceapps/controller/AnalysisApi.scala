package spaceapps.controller

import spaceapps.domain.*
import spaceapps.service.Analyses
import zio.*
import zio.http.*
import zio.json.*
import java.nio.charset.StandardCharsets

private[controller] final class AnalysisApi(service:Analyses):
  private def json[A:JsonEncoder](a:A,status:Status=Status.Ok)=Response.json(a.toJson).status(status).addHeader("Cache-Control","no-store")
  private def safe(effect:Task[Response]):UIO[Response]=effect.catchAll { t=>
    val e=ApiError.from(t)
    val status=e.code match
      case "not_found"=>Status.NotFound
      case "capacity_exceeded" | "preset_unavailable" | "model_unavailable"=>Status.ServiceUnavailable
      case "internal_error" | "storage_error"=>Status.InternalServerError
      case _=>Status.UnprocessableEntity
    ZIO.succeed(json(e,status))
  }
  private def submit(request:Request):Task[Response]=for
    bytes<-request.body.asStream.take(65537).runCollect
    _<-ZIO.fail(ApiError("invalid_request","Analysis request exceeds 64 KiB")).when(bytes.size>65536)
    parsed<-ZIO.fromEither(AnalysisRequest.parse(new String(bytes.toArray,StandardCharsets.UTF_8)))
    a<-service.submit(parsed)
  yield json(a,Status.Accepted).addHeader("Location",a.status_url)
  private def events(id:String):Task[Response]=service.get(id).as {
    val stream=service.events(id).map(e=>s"id: ${e.sequence}\nevent: ${e.name}\ndata: ${e.data}\n\n")
    Response(body=Body.fromStreamChunked(stream.mapConcat(_.getBytes(StandardCharsets.UTF_8))))
      .addHeader("Content-Type","text/event-stream").addHeader("Cache-Control","no-store").addHeader("X-Accel-Buffering","no")
  }
  val routes:Routes[Any,Response]=Routes(
    Method.POST / "api" / "analyses" / "motion" -> handler((r:Request)=>safe(submit(r))),
    Method.GET / "api" / "analyses" / "models" -> handler(safe(service.models.map(json(_)))),
    Method.GET / "api" / "analyses" / "presets" -> handler(safe(service.presets.map(json(_)))),
    Method.GET / "api" / "analyses" / string("id") -> handler((id:String,r:Request)=>safe(service.get(id).map(json(_)))),
    Method.GET / "api" / "analyses" / string("id") / "events" -> handler((id:String,r:Request)=>safe(events(id))),
    Method.GET / "api" / "analyses" / string("id") / "resources" / string("name") -> handler((id:String,name:String,r:Request)=>safe(service.resource(id,name).flatMap(p=>Body.fromFile(p.toFile)).map(b=>Response(body=b).addHeader("Content-Type","image/png").addHeader("Cache-Control","private, max-age=3600"))))
  )
