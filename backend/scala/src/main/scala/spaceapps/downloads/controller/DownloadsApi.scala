package spaceapps.downloads.controller
import spaceapps.downloads.model.*
import spaceapps.downloads.service.DownloadsService
import zio.*
import zio.http.*
import zio.json.*
import zio.json.ast.Json
import zio.stream.ZStream
import java.nio.charset.StandardCharsets.UTF_8
final class DownloadsApi(service: DownloadsService):
  private def json[A:JsonEncoder](value: A,status: Status = Status.Ok): Response = Response.json(value.toJson).status(status).addHeader("Cache-Control","no-store")
  private def safe(task: IO[ArchiveFailure,Response]): UIO[Response] = task.catchAll { e=>
    val status=e.code match
      case "not_found"=>Status.NotFound
      case "storage_error"=>Status.InternalServerError
      case "capacity_exceeded"=>Status.TooManyRequests
      case "job_active" | "stale_cursor"=>Status.Conflict
      case _=>Status.UnprocessableEntity
    ZIO.succeed(json(e,status))
  }
  private def body(request: Request): IO[ArchiveFailure,String] =
    Ref.make(0L).flatMap { size=>request.body.asStream.mapChunksZIO(c=>size.updateAndGet(_+c.size).flatMap(n=>if n>65536 then ZIO.fail(ArchiveFailure("invalid_request","Request body exceeds 64 KiB")) else ZIO.succeed(c))).runCollect.map(c=>new String(c.toArray,UTF_8)) }.mapError(ArchiveFailure.from)
  private def objectFields(value: Json,allowed: Set[String]): Either[ArchiveFailure,Map[String,Json]] = value match
    case Json.Obj(fields) if fields.map(_._1).distinct.size==fields.size && fields.forall((k,_)=>allowed(k))=>Right(fields.toMap)
    case _=>Left(ArchiveFailure("invalid_request","JSON must contain only the documented properties, each once"))
  private def parse[A:JsonDecoder](request: Request,allowed: Set[String]): IO[ArchiveFailure,A] =
    for
      text <- body(request)
      ast <- ZIO.fromEither(text.fromJson[Json].left.map(_=>ArchiveFailure("invalid_request","Expected a JSON object")))
      fields <- ZIO.fromEither(objectFields(ast,allowed))
      _ <- ZIO.foreachDiscard(fields.get("region"))(v=>ZIO.fromEither(objectFields(v,Set("type","ra_degrees","dec_degrees","radius_degrees"))))
      _ <- ZIO.foreachDiscard(fields.get("delivery")) { v=>
        ZIO.fromEither(objectFields(v,Set("mode","region"))).flatMap(d=>ZIO.foreachDiscard(d.get("region"))(r=>ZIO.fromEither(objectFields(r,Set("type","ra_degrees","dec_degrees","radius_degrees")))))
      }
      value <- ZIO.fromEither(text.fromJson[A].left.map(_=>ArchiveFailure("invalid_request","JSON properties have invalid or missing types")))
    yield value
  private def page(id: String,request: Request): IO[ArchiveFailure,Response] =
    val parsed=request.url.queryParams.getAll("limit").headOption.fold[Either[ArchiveFailure,Int]](Right(50))(s=>s.toIntOption.toRight(ArchiveFailure("invalid_cursor","Page limit must be an integer")))
    ZIO.fromEither(parsed).flatMap(limit=>service.page(id,request.url.queryParams.getAll("cursor").headOption,limit)).map(json(_))
  private def events(id:String,request:Request):IO[ArchiveFailure,Response]=
    for
      after <- ZIO.fromEither(request.headers.get("Last-Event-ID").fold[Either[ArchiveFailure,Option[Long]]](Right(None))(s=>s.toLongOption.map(Some(_)).toRight(ArchiveFailure("invalid_cursor","Last-Event-ID must be a nonnegative integer"))))
      stream <- service.events(id,after)
    yield Response(body=Body.fromStreamChunked(stream.map(e=>s"id: ${e.sequence}\nevent: ${e.name}\ndata: ${e.data}\n\n").mapConcat(_.getBytes(UTF_8))))
      .addHeader("Content-Type","text/event-stream").addHeader("Cache-Control","no-store").addHeader("X-Accel-Buffering","no")
  private def artifact(id:String):ZIO[Scope,ArchiveFailure,Response]=service.resource(id).map {
    case AssetResource.Pending=>json(Map("id"->id,"status"->"pending"),Status.Accepted).addHeader("Retry-After","1")
    case AssetResource.Failed(error)=>json(error,Status.Conflict)
    case AssetResource.Ready(path,asset)=>
      Response(body=Body.fromStreamChunked(ZStream.fromPath(path))).addHeader("Content-Type",if asset.compression=="gzip" then "application/gzip" else "application/fits")
        .addHeader("Content-Disposition",s"attachment; filename=\"${asset.id}.fits${if asset.compression=="gzip" then ".gz" else ""}\"")
  }
  val routes: Routes[Any,Response] = Routes(
    Method.GET / "api" / "archives" -> handler(safe(service.inventory.map(json(_)))),
    Method.POST / "api" / "archive-searches" -> handler { (request: Request)=>safe(parse[ArchiveQuery](request,Set("region","providers","product_kinds","time_start_utc","time_end_utc","limit_per_provider")).flatMap(service.search).map(j=>json(j,Status.Accepted))) },
    Method.GET / "api" / "archive-searches" / string("id") -> handler { (id: String,request: Request)=>safe(page(id,request)) },
    Method.POST / "api" / "archive-searches" / string("id") / "continue" -> handler { (id: String,request: Request)=>
      safe(parse[Map[String,String]](request,Set("provider")).flatMap(m=>ZIO.fromOption(m.get("provider")).orElseFail(ArchiveFailure("invalid_request","Select a provider"))).flatMap(service.continue(id,_)).map(j=>json(j,Status.Accepted)))
    },
    Method.POST / "api" / "archive-downloads" -> handler { (request: Request)=>safe(parse[DownloadSelection](request,Set("record_ids","delivery")).flatMap(service.download).map(j=>json(j,Status.Accepted))) },
    Method.GET / "api" / "archive-downloads" / string("id") -> handler { (id: String,request: Request)=>safe(service.downloadStatus(id).map(json(_))) },
    Method.GET / "api" / "archive-downloads" / string("id") / "events" -> handler { (id:String,request:Request)=>safe(events(id,request)) },
    Method.GET / "api" / "archive-assets" / string("id") -> Handler.scoped[Any](handler { (id:String,request:Request)=>
      artifact(id).catchAll(error=>ZIO.succeed(json(error,if error.code=="not_found" then Status.NotFound else Status.InternalServerError)))
    })
  )
