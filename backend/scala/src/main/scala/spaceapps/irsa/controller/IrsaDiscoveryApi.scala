package spaceapps.irsa.controller

import spaceapps.irsa.model.*
import spaceapps.irsa.service.Archive
import spaceapps.irsa.repository.Repository
import spaceapps.infra.controller.HttpResponses.{json,safe}
import zio.*
import zio.http.*
import zio.json.*
import zio.json.ast.Json
import java.time.Instant
import java.nio.charset.StandardCharsets.UTF_8

final case class IrsaDiscoveryRequest(right_ascension_deg:Double,declination_deg:Double,radius_degrees:Double,
  detector_array:Option[Int]=None,observed_after:Option[String]=None,observed_before:Option[String]=None) derives JsonCodec

/** Shared discovery for Python consumers; it never downloads image pixels. */
final class IrsaDiscoveryApi(archive:Archive,repository:Repository):
  val routes:Routes[Any,Response]=Routes(
    Method.POST / "api" / "irsa" / "discovery" -> handler { (request:Request)=>safe {
      for
        bytes<-request.body.asStream.take(16385).runCollect
        _<-ZIO.fail(ApiError("invalid_request","Discovery request exceeds 16 KiB")).when(bytes.size>16384)
        body<-ZIO.fromEither(new String(bytes.toArray,UTF_8).fromJson[IrsaDiscoveryRequest]).mapError(_=>ApiError("invalid_request","Invalid discovery request JSON"))
        query<-ZIO.attempt(IrsaDiscoveryApi.query(body))
        images<-archive.search(query)
        _<-repository.remember(images)
        complete= !images.exists(_.observation.header_metadata.get("discovery_complete").contains(Json.Str("false")))
        encoded<-ZIO.fromEither(images.toJson.fromJson[Json]).mapError(_=>ApiError("internal_error","Cannot serialize discovery metadata"))
      yield json(Json.Obj("images"->encoded,"discovery_complete"->Json.Bool(complete)))
    }}
  )
object IrsaDiscoveryApi:
  private def invalid(message:String):Nothing=throw ApiError("invalid_request",message)
  private[spaceapps] def query(r:IrsaDiscoveryRequest):Query=
    if !r.right_ascension_deg.isFinite || r.right_ascension_deg<0 || r.right_ascension_deg>=360 ||
      !r.declination_deg.isFinite || math.abs(r.declination_deg)>90 || !r.radius_degrees.isFinite || r.radius_degrees<=0 || r.radius_degrees>5 ||
      r.detector_array.exists(n=>n<1 || n>6) then invalid("Invalid discovery coordinates, radius or detector")
    def date(s:String):Instant=scala.util.Try(Instant.parse(s)).getOrElse(invalid("Observation dates must be UTC ISO-8601 instants"))
    val start=r.observed_after.map(date);val stop=r.observed_before.map(date)
    if start.nonEmpty && stop.nonEmpty && !start.get.isBefore(stop.get) then invalid("Observation start must precede end")
    Query(Json.Obj(),s"CIRCLE ${r.right_ascension_deg} ${r.declination_deg} ${r.radius_degrees}",r.detector_array,
      after=r.observed_after,before=r.observed_before)
