package spaceapps.irsa.controller
import spaceapps.irsa.model.*
import spaceapps.irsa.service.{Jobs,Resource,MetadataService}
import spaceapps.infra.controller.HttpResponses.{json as respond,safe}
import zio.{Chunk as _,*}
import zio.http.*
import zio.json.*
import zio.stream.*
import java.nio.charset.StandardCharsets
final class IrsaApi(jobs:Jobs,channels:Set[Int],metadata:Option[MetadataService]):
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
    yield respond(job,if job.terminal then Status.Ok else Status.Accepted).addHeader("Location",job.status_url)
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
    yield respond(job,if job.terminal then Status.Ok else Status.Accepted).addHeader("Location",job.status_url)
  private def observationMetadata(request:Request):Task[Response]=
    for
      values <- parameters(request)
      id <- ZIO.fromOption(values.get("frame_id").filter(_.nonEmpty)).orElseFail(ApiError("invalid_request","frame_id is required"))
      service <- ZIO.fromOption(metadata).orElseFail(ApiError("service_unavailable","Metadata service is not configured",true))
      result <- service.get(id)
    yield respond(result)
  private def search(request:Request):Task[Response]=
    for
      bytes <- request.body.asStream.take(65537).runCollect
      _ <- ZIO.fail(ApiError("invalid_request","Search body exceeds 64 KiB")).when(bytes.size>65536)
      q <- ZIO.fromEither(Query.fromJson(new String(bytes.toArray,StandardCharsets.UTF_8))).flatMap(supported)
      observations <- jobs.search(q)
    yield Response.json(s"{\"observations\":${observations.toJson}}")
  private def resource(id:String,preview:Boolean):ZIO[Scope,Throwable,Response]=jobs.leasedResource(id,preview).flatMap {
    case Resource.Pending=>ZIO.succeed(Response.json(s"{\"id\":${id.toJson},\"status\":\"pending\"}").status(Status.Accepted).addHeader("Retry-After","1").addHeader("Cache-Control","no-store"))
    case Resource.Failed(error)=>ZIO.succeed(respond(error,Status.Conflict))
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
  private def deferred:Response=respond(ApiError("unsupported_processing","The existing pipeline HTTP API does not provide this native-FITS processing operation"),Status.NotImplemented)
  val routes:Routes[Any,Response]=Routes(
    Method.POST / "api" / "observations" / "search" -> handler((r:Request)=>safe(search(r))),
    Method.GET / "api" / "observations" / "meta" -> handler((r:Request)=>safe(observationMetadata(r))),
    Method.GET / "api" / "observationsDeep" -> handler((r:Request)=>safe(prepareDeep(r))),
    Method.GET / "api" / "observations" / "default" -> handler((r:Request)=>safe(prepare("default",r))),
    Method.GET / "api" / "observations" / "range" -> handler((r:Request)=>safe(prepare("range",r))),
    Method.GET / "api" / "observations" / "polygon" -> handler((r:Request)=>safe(prepare("polygon",r))),
    Method.GET / "api" / "observations" / "zodi-reference-subtracted" -> handler(deferred),
    Method.GET / "api" / "observations" / "epoch-difference" -> handler(deferred),
    Method.GET / "api" / "downloads" / string("id") -> handler((id:String,r:Request)=>safe(jobs.get(id).map(respond(_)))),
    Method.GET / "api" / "downloads" / string("id") / "events" -> handler((id:String,r:Request)=>safe(events(id))),
    Method.GET / "api" / "chunks" / string("id") -> Handler.scoped[Any](handler((id:String,r:Request)=>safe(resource(id,false)))),
    Method.GET / "api" / "chunks" / string("id") / "preview" -> Handler.scoped[Any](handler((id:String,r:Request)=>safe(resource(id,true))))
  )
