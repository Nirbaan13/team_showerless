package spaceapps.integrations.grpc

import spaceapps.{domain as d}
import spaceapps.service.Analyses
import spaceapps.integrations.grpc.v1.*
import spaceapps.integrations.grpc.v1.ZioRetrieval.RCAnalysisService
import com.google.protobuf.struct.{Struct,Value}
import io.grpc.{Status,StatusException,Metadata}
import scalapb.zio_grpc.RequestContext
import zio.*
import zio.json.*
import zio.json.ast.Json
import zio.stream.*

private[grpc] final class AnalysisGrpc(service:Analyses) extends RCAnalysisService:
  private def failure(t:Throwable):StatusException=
    val e=d.ApiError.from(t)
    val status=e.code match
      case "not_found"=>Status.NOT_FOUND
      case "capacity_exceeded"=>Status.RESOURCE_EXHAUSTED
      case "preset_unavailable" | "model_unavailable"=>Status.UNAVAILABLE
      case "internal_error" | "storage_error"=>Status.INTERNAL
      case _=>Status.INVALID_ARGUMENT
    val trailers=new Metadata()
    trailers.put(Metadata.Key.of("spaceapps-error-bin",Metadata.BINARY_BYTE_MARSHALLER),GrpcMapping.error(e).toByteArray)
    status.withDescription(e.message).asException(trailers)
  private def preserve(e:StatusException,c:RequestContext):UIO[Unit]=Option(e.getTrailers).fold[UIO[Unit]](ZIO.unit)(t=>c.responseMetadata.wrap(_.merge(t)))
  private def run[A](c:RequestContext)(a:Task[A]):IO[StatusException,A]=a.mapError(failure).tapError(preserve(_,c))
  private def json(v:Value):Json=v.kind match
    case Value.Kind.StringValue(s)=>Json.Str(s)
    case Value.Kind.NumberValue(n) if n.isFinite=>Json.Num(n)
    case Value.Kind.NumberValue(_)=>throw d.ApiError("invalid_request","Options must be finite")
    case Value.Kind.BoolValue(b)=>Json.Bool(b)
    case Value.Kind.ListValue(l)=>Json.Arr(zio.Chunk.fromIterable(l.values.map(json)))
    case Value.Kind.StructValue(s)=>Json.Obj(zio.Chunk.fromIterable(s.fields.map((k,v)=>k->json(v))))
    case _=>Json.Null
  private def struct(j:Json):Struct=GrpcMapping.value(j).kind.structValue.get
  private def job(a:d.Analysis):AnalysisJob=
    val state=a.status match
      case "queued"=>AnalysisState.QUEUED
      case "waiting_for_download"=>AnalysisState.WAITING_FOR_DOWNLOAD
      case "preparing"=>AnalysisState.PREPARING
      case "inferencing"=>AnalysisState.INFERENCING
      case "completed"=>AnalysisState.COMPLETED
      case "failed"=>AnalysisState.FAILED
      case _=>AnalysisState.ANALYSIS_STATE_UNSPECIFIED
    AnalysisJob(a.id,state,a.download_id,a.status_url,a.events_url,a.result.map(struct),a.error.map(GrpcMapping.error))
  def submitAnalysis(r:SubmitAnalysisRequest,c:RequestContext):IO[StatusException,AnalysisJob]=run(c) {
    ZIO.attempt {
      val source=r.source match
        case SubmitAnalysisRequest.Source.DownloadId(id)=>List("download_id"->Json.Str(id))
        case SubmitAnalysisRequest.Source.Preset(id)=>List("preset"->Json.Str(id))
        case _=>Nil
      val fields=source++r.options.map(o=>"options"->Json.Obj(zio.Chunk.fromIterable(o.fields.map((k,v)=>k->json(v)))))
      d.AnalysisRequest.parse(Json.Obj(zio.Chunk.fromIterable(fields)).toJson)
    }.flatMap(ZIO.fromEither(_)).flatMap(service.submit).map(job)
  }
  def getAnalysis(r:AnalysisRequest,c:RequestContext):IO[StatusException,AnalysisJob]=run(c)(service.get(r.analysisId).map(job))
  def watchAnalysis(r:AnalysisRequest,c:RequestContext):Stream[StatusException,AnalysisEvent]=service.events(r.analysisId).mapZIO { e=>
    ZIO.fromEither(e.data.fromJson[d.Analysis]).mapError(_=>d.ApiError("storage_error","Stored analysis event is invalid")).map(a=>AnalysisEvent(e.sequence,e.name,Some(job(a))))
  }.mapError(failure).tapError(preserve(_,c))
  def getModels(r:ModelsRequest,c:RequestContext):IO[StatusException,ModelsResponse]=run(c)(service.models.map { j=>
    val list=j.asInstanceOf[Json.Obj].fields.toMap.apply("models").asInstanceOf[Json.Arr].elements
    ModelsResponse(list.map(struct).toSeq)
  })
  def getPresets(r:PresetsRequest,c:RequestContext):IO[StatusException,PresetsResponse]=run(c)(service.presetList.map(ps=>PresetsResponse(ps.map(p=>spaceapps.integrations.grpc.v1.AnalysisPreset(p.id,p.title,p.description,p.source_url)))))
