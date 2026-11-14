package spaceapps.integrations.grpc

import spaceapps.{domain as d}
import spaceapps.integrations.grpc.{v1 as p}
import com.google.protobuf.struct.{Struct, Value, ListValue, NullValue}
import zio.json.*
import zio.json.ast.Json

private[grpc] object GrpcMapping:
  def query(input: Option[p.Query], channels: Set[Int]): Either[d.ApiError, d.Query] =
    input.toRight(d.ApiError("invalid_request", "A query is required")).flatMap { q =>
      val filters = q.detectorArray.map(v => "detector_array" -> v.toString).toList ++
        q.channelIndex.map(v => "channel_index" -> v.toString) ++
        q.observedAfter.map("observed_after" -> _) ++ q.observedBefore.map("observed_before" -> _)
      val geometry: Either[d.ApiError, (String, Map[String,String])] = q.region match
        case p.Query.Region.Center(c) => Right("default" -> (Map("right_ascension_deg" -> c.rightAscensionDeg.toString, "declination_deg" -> c.declinationDeg.toString) ++
          c.widthArcmin.map(v => "width_arcmin" -> v.toString) ++ c.heightArcmin.map(v => "height_arcmin" -> v.toString)))
        case p.Query.Region.Range(r) => Right("range" -> Map("right_ascension_min_deg" -> r.rightAscensionMinDeg.toString,
          "right_ascension_max_deg" -> r.rightAscensionMaxDeg.toString, "declination_min_deg" -> r.declinationMinDeg.toString, "declination_max_deg" -> r.declinationMaxDeg.toString))
        case p.Query.Region.Polygon(poly) => Right("polygon" -> Map("verices_degrees" -> poly.verticesDegrees.flatMap(v => Seq(v.rightAscensionDeg, v.declinationDeg)).mkString(",")))
        case p.Query.Region.Empty => Left(d.ApiError("invalid_request", "A query region is required"))
      geometry.flatMap((shape, values) => d.Query.fromParameters(shape, values ++ filters)).flatMap { validated =>
        if validated.channel.exists(c => !channels.contains(c)) then Left(d.ApiError("invalid_request", "The requested channel has no configured wavelength mapping"))
        else Right(validated)
      }
    }

  private def fields(json: Json): Map[String,Json] = json match
    case Json.Obj(values) => values.toMap
    case _ => throw d.ApiError("storage_error", "Stored query must be an object")
  private def number(value: Json): Double = value match
    case Json.Num(n) => n.doubleValue
    case _ => throw d.ApiError("storage_error", "Stored query contains a nonnumeric coordinate")
  private def string(value: Json): String = value match
    case Json.Str(s) => s
    case _ => throw d.ApiError("storage_error", "Stored query contains a nontext filter")
  def query(json: Json): p.Query =
    val f = fields(json)
    def n(key: String) = number(f(key))
    val region = if f.contains("verices_degrees") then
      val values = f("verices_degrees") match
        case Json.Arr(vs) => vs.toList.map(number)
        case _ => throw d.ApiError("storage_error", "Stored polygon must be an array")
      p.Query.Region.Polygon(p.Polygon(values.grouped(2).map(v => p.Vertex(v(0), v(1))).toSeq))
    else if f.contains("right_ascension_min_deg") then
      p.Query.Region.Range(p.Range(n("right_ascension_min_deg"), n("right_ascension_max_deg"), n("declination_min_deg"), n("declination_max_deg")))
    else p.Query.Region.Center(p.Center(n("right_ascension_deg"), n("declination_deg"), f.get("width_arcmin").map(number), f.get("height_arcmin").map(number)))
    p.Query(region, f.get("detector_array").collect { case Json.Num(v) => v.intValue }, f.get("channel_index").map(number(_).toInt),
      f.get("observed_after").map(string), f.get("observed_before").map(string))

  private def value(json: Json): Value = Value(json match
    case Json.Null => Value.Kind.NullValue(NullValue.NULL_VALUE)
    case Json.Str(s) => Value.Kind.StringValue(s)
    case Json.Bool(b) => Value.Kind.BoolValue(b)
    case Json.Num(n) => Value.Kind.NumberValue(n.doubleValue)
    case Json.Arr(vs) => Value.Kind.ListValue(ListValue(vs.map(value).toSeq))
    case Json.Obj(vs) => Value.Kind.StructValue(Struct(vs.map((k,v) => k -> value(v)).toMap)))
  def error(e: d.ApiError): p.ApiError = p.ApiError(e.code, e.message, e.retryable)
  def observation(o: d.Observation): p.Observation = p.Observation(o.frame_id, o.observation_date, o.detector_array, o.release,
    o.is_available, o.wavelength_min_um, o.wavelength_max_um, o.channel_index, o.skip_reason,
    Some(Struct(o.header_metadata.map((k,v) => k -> value(v)))))
  def chunk(c: d.Chunk): p.Chunk = p.Chunk(c.id, c.frame_id, c.status, c.preview_status, c.image_url, c.fits_cutout_url, c.error.map(error))
  def progress(v: d.Progress): p.Progress = p.Progress(v.discovery_complete, v.total_chunks, v.ready_chunks, v.failed_chunks, v.unavailable_chunks)
  def download(v: d.Download): p.Download = p.Download(v.id, v.status, v.mode, Some(query(v.query)), v.observations.map(observation),
    v.chunks.map(chunk), Some(progress(v.progress)), v.status_url, v.events_url, v.reference_frame_id, v.errors.map(error))

  private case class ChunkEnvelope(job_id: String, progress: d.Progress) derives JsonDecoder
  private def decode[A: JsonDecoder](body: String): A = body.fromJson[A].fold(_ => throw d.ApiError("storage_error", "Stored event could not be decoded"), identity)
  def event(v: d.Event): p.DownloadEvent =
    val payload = if v.name == "job.updated" || v.name == "job.completed" then
      p.DownloadEvent.Payload.Download(download(decode[d.Download](v.data)))
    else
      val envelope = decode[ChunkEnvelope](v.data)
      p.DownloadEvent.Payload.ChunkUpdate(p.ChunkUpdate(envelope.job_id, Some(chunk(decode[d.Chunk](v.data))), Some(progress(envelope.progress))))
    p.DownloadEvent(v.sequence, v.name, payload)
