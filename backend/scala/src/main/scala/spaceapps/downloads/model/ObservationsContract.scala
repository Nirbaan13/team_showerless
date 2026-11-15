package spaceapps.downloads.model

import spaceapps.infra.model.Event
import zio.json.*
import zio.json.ast.Json

/** Only server-known IDs are accepted: downloading never performs discovery. */
final case class ObservationSelection(observation_ids:List[String],delivery:DeliveryRequest=DeliveryRequest()) derives JsonCodec
final case class ObservationChunk(id:String,frame_id:String,status:String,preview_status:String,image_url:String,fits_cutout_url:String,error:Option[ArchiveFailure]=None) derives JsonCodec
final case class ObservationDownload(id:String,status:String,mode:String,query:Json,observations:List[Json],chunks:List[ObservationChunk],progress:DownloadProgress,status_url:String,events_url:String,errors:List[ArchiveFailure],assets:List[AssetOutcome]) derives JsonCodec
final case class ObservationsFound(observations:List[Json],outcomes:List[ProviderOutcome],returned_count:Int) derives JsonCodec

object ObservationsContract:
  val base="/api/observations-download"
  def observation(record:ArchiveRecord):Json=
    val original=record.toJsonAST.toOption.get.asObject.get
    val aliases=List("frame_id"->Json.Str(record.id),"is_available"->Json.Bool(record.original || record.cutout)) ++
      record.time.start_utc.filter(_=>record.time.quality==TimeQuality.verified).map(v=>"observation_date"->Json.Str(v)) ++ record.native.get("release").map(v=>"release"->Json.Str(v)) ++
      record.wavelength_min_m.map(v=>"wavelength_min_um"->Json.Num(v*1e6)) ++ record.wavelength_max_m.map(v=>"wavelength_max_um"->Json.Num(v*1e6))
    Json.Obj(zio.Chunk.fromIterable(original.fields.toList++aliases))
  def download(job:DownloadSnapshot,records:List[ArchiveRecord]):ObservationDownload=
    val chunks=job.selection.record_ids.flatMap(id=>job.chunks.filter(_.record_id==id)).map { c=>
      val status=c.status match
        case "downloading"=>"pending"
        case "skipped"=>"unavailable"
        case other=>other
      ObservationChunk(c.id,c.record_id,status,"unavailable",s"$base/chunks/${c.id}/preview",s"$base/chunks/${c.id}",c.error)
    }
    val status=job.status match
      case "running"=>"preparing"
      case "partial"=>"completed_with_errors"
      case other=>other
    val query=Json.Obj("observation_ids"->job.selection.record_ids.toJsonAST.toOption.get,"delivery"->job.selection.delivery.toJsonAST.toOption.get)
    val errors=(job.assets.flatMap(_.error)++chunks.flatMap(_.error)).distinct
    ObservationDownload(job.id,status,"default",query,records.map(observation),chunks,job.manifest.progress,s"$base/${job.id}",s"$base/${job.id}/events",errors,job.assets)
  def event(event:Event,job:ObservationDownload,target:Option[String]):Event=
    val chunk=target.flatMap(id=>job.chunks.find(_.id==id))
    val full=job.toJson.dropRight(1)+s",\"job_id\":${job.id.toJson}}"
    if Set("chunk.ready","chunk.failed")(event.name) && chunk.nonEmpty then
      val c=chunk.get
      event.copy(data=c.toJson.dropRight(1)+s",\"job_id\":${job.id.toJson},\"chunk_id\":${c.id.toJson},\"progress\":${job.progress.toJson}}")
    else event.copy(name=if event.name=="job.completed" then "job.completed" else "job.updated",data=full)
