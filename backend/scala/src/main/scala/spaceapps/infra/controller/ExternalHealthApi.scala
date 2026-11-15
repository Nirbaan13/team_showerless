package spaceapps.infra.controller
import spaceapps.infra.service.ExternalServices
import zio.*
import zio.http.*
import zio.json.ast.Json
import spaceapps.infra.controller.HttpResponses.json
final class ExternalHealthApi(services:ExternalServices,mirror:UIO[Json]):
  val routes:Routes[Any,Response]=Routes(
    Method.GET / "api" / "infra" / "external-services" -> handler {
      for
        upstream<-services.status
        index<-mirror
      yield json(Json.Obj("upstream"->upstream,"mirror_index"->index))
    }
  )
