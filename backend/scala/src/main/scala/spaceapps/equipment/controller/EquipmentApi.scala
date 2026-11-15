package spaceapps.equipment.controller
import spaceapps.equipment.service.EquipmentService
import spaceapps.infra.model.ApiError
import spaceapps.infra.controller.HttpResponses.{json as respond,safe}
import zio.*
import zio.http.*
final class EquipmentApi(equipment:Option[EquipmentService]):
  private def equipmentCatalogue(request:Request):Task[Response]=
    for
      values <- ZIO.attempt {
        List("release","detector_array").flatMap { name=>
          val values=request.url.queryParams.getAll(name)
          if values.size>1 then throw ApiError("invalid_request",s"$name must appear once")
          values.headOption.map(name->_)
        }.toMap
      }
      detector <- values.get("detector_array") match
        case None | Some("all") => ZIO.none
        case Some(value) => ZIO.fromOption(value.toIntOption.filter(n=>n>=1 && n<=6)).map(Some(_))
          .orElseFail(ApiError("invalid_request","detector_array must be all or an integer from1 to6"))
      service <- ZIO.fromOption(equipment).orElseFail(ApiError("service_unavailable","Equipment service is not configured",true))
      result <- service.catalog(values.getOrElse("release","DR1"),detector)
    yield respond(result)
  private def calibrationFile(id:String):ZIO[Scope,Throwable,Response]=
    for
      service <- ZIO.fromOption(equipment).orElseFail(ApiError("service_unavailable","Equipment service is not configured",true))
      file <- service.leasedFile(id)
      body <- Body.fromFile(file.path.toFile)
      name = file.fileName.replaceAll("[^A-Za-z0-9._-]","_")
    yield Response(body=body).addHeader("Content-Type",file.contentType)
      .addHeader("Content-Disposition",s"attachment; filename=\"$name\"").addHeader("Cache-Control","private, max-age=3600")
  val routes:Routes[Any,Response]=Routes(
    Method.GET / "api" / "equipment" -> handler((r:Request)=>safe(equipmentCatalogue(r))),
    Method.GET / "api" / "equipment" / "calibrations" / string("id") -> Handler.scoped[Any](handler((id:String,r:Request)=>safe(calibrationFile(id))))
  )
