package spaceapps.irsa.integrations

import spaceapps.irsa.model.*
import spaceapps.irsa.service.{Archive,MirrorSearchGate}
import zio.*
import zio.json.*
import zio.json.ast.Json
import java.nio.file.Path

final class S3MirrorArchive private(process:MirrorProcess,transfer:Archive,state:Ref[Json],maxRecords:Int,gate:MirrorSearchGate) extends Archive:
  def status:UIO[Json]=state.get.zip(gate.admitted).map { (value,admitted)=>value match
    case Json.Obj(fields)=>Json.Obj(fields.filterNot(_._1=="admitted_searches") :+ ("admitted_searches"->Json.Num(admitted)))
    case other=>other
  }
  private def index(value:Json):Json=value match
    case Json.Obj(fields)=>fields.toMap.getOrElse("index",Json.Null)
    case _=>Json.Null
  def search(query:Query):Task[List[ArchiveImage]]=gate.run { for
    value<-process.run(List("search","--limit",maxRecords.toString),Some(query.toJson))
    _<-state.set(index(value))
    body<-value match
      case Json.Obj(fields)=>ZIO.fromOption(fields.toMap.get("images")).orElseFail(ApiError("archive_mirror_invalid_response","Mirror image list missing"))
      case _=>ZIO.fail(ApiError("archive_mirror_invalid_response","Mirror response is not an object"))
    images<-ZIO.fromEither(body.toJson.fromJson[List[ArchiveImage]]).mapError(_=>ApiError("archive_mirror_invalid_response","Mirror image metadata could not be decoded"))
  yield images
  }
  def fetch(image:ArchiveImage,destination:Path):Task[Unit]=transfer.fetch(image,destination)
  private def scan:Task[Boolean]=for
    value<-process.run(List("catalog","--page-size","128","--max-pages","4096","--workers","32","--max-seconds","180"))
    errors=value.asObject.flatMap(_.get("errors")).getOrElse(Json.Arr())
    progress=index(value) match
      case Json.Obj(fields)=>Json.Obj(fields :+ ("scan_errors"->errors))
      case other=>other
    _<-state.set(progress)
    _<-ZIO.logWarning("Mirror index has pending scan errors; check /api/infra/external-services").when(errors match
      case Json.Arr(items)=>items.nonEmpty
      case _=>false
    )
  yield progress match
    case Json.Obj(fields)=>fields.toMap.get("complete").contains(Json.Bool(true))
    case _=>false
  private def refresh:Task[Unit]=for
    value<-process.run(List("status"))
    _<-state.update { previous=>
      val errors=previous.asObject.flatMap(_.get("scan_errors")).getOrElse(Json.Arr())
      index(value) match
        case Json.Obj(fields)=>Json.Obj(fields :+ ("scan_errors"->errors))
        case other=>other
    }
  yield ()
  def start:ZIO[Scope,Nothing,Unit]=for
    // Catalogue batches run for minutes; refresh committed progress separately.
    _<-(refresh.catchAll(error=>ZIO.logWarning(s"Mirror catalogue status unavailable: ${error.getMessage}")) *> ZIO.sleep(15.seconds)).forever.forkScoped
    _<-(scan.foldZIO(
      error=>ZIO.logWarningCause("Public mirror index scan failed; progress will be retried",Cause.fail(error))*>ZIO.sleep(30.seconds),
      complete=>ZIO.sleep(if complete then 1.hour else 5.seconds)
    )).forever.forkScoped
  yield ()

object S3MirrorArchive:
  def make(process:MirrorProcess,transfer:Archive,maxRecords:Int=256):UIO[S3MirrorArchive]=
    for
      state<-Ref.make[Json](Json.Obj("complete"->Json.Bool(false),"state"->Json.Str("initializing")))
      gate<-MirrorSearchGate.make
    yield new S3MirrorArchive(process,transfer,state,maxRecords,gate)
