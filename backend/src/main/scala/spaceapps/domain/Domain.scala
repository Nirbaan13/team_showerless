package spaceapps.domain

import zio.*
import zio.json.*
import zio.json.ast.Json
import java.security.MessageDigest
import java.time.Instant
import scala.util.Try

final case class ApiError(code: String, message: String, retryable: Boolean = false) extends Exception(message) derives JsonCodec
object ApiError:
  def from(t: Throwable): ApiError = t match
    case e: ApiError => e
    case _ => ApiError("internal_error", "The operation failed; inspect service logs", true)

final case class Observation(frame_id: String, observation_date: String, detector_array: Int, release: String,
  is_available: Boolean = true, wavelength_min_um: Option[Double] = None, wavelength_max_um: Option[Double] = None,
  channel_index: Option[Int] = None, skip_reason: Option[String] = None,
  header_metadata: Map[String, Json] = Map.empty) derives JsonCodec
final case class ArchiveImage(observation: Observation, accessUrl: String) derives JsonCodec
final case class Chunk(id: String, frame_id: String, status: String = "pending", preview_status: String = "pending",
  image_url: String, fits_cutout_url: String, error: Option[ApiError] = None) derives JsonCodec
final case class Progress(discovery_complete: Boolean = false, total_chunks: Int = 0, ready_chunks: Int = 0,
  failed_chunks: Int = 0, unavailable_chunks: Int = 0) derives JsonCodec
final case class Download(id: String, status: String, mode: String, query: Json,
  observations: List[Observation] = Nil, chunks: List[Chunk] = Nil, progress: Progress = Progress(),
  status_url: String, events_url: String, reference_frame_id: Option[String] = None,
  errors: List[ApiError] = Nil) derives JsonCodec:
  def terminal: Boolean = Set("completed", "completed_with_errors", "failed").contains(status)
final case class Event(sequence: Long, name: String, data: String) derives JsonCodec
final case class JobRecord(download: Download, query: Query, requestKey: String,
  images: List[ArchiveImage] = Nil) derives JsonCodec

final case class Query(document: Json, position: String, detector: Option[Int] = None, channel: Option[Int] = None,
  after: Option[String] = None, before: Option[String] = None) derives JsonCodec:
  def key(mode: String, reference: Option[String]): String = Hash.sha256(s"$mode|${reference.getOrElse("")}|${document.toJson}")

object Hash:
  def sha256(text: String): String = MessageDigest.getInstance("SHA-256").digest(text.getBytes(java.nio.charset.StandardCharsets.UTF_8)).map(b => f"${b & 255}%02x").mkString

object Query:
  private def invalid(message: String): Nothing = throw ApiError("invalid_request", message)
  private def number(value: String, name: String): Double =
    val n = Try(value.toDouble).getOrElse(invalid(s"$name must be numeric"))
    if !n.isFinite then invalid(s"$name must be finite")
    n
  private def bounded(n: Double, low: Double, high: Double, name: String, exclusive: Boolean = false): Double =
    if n < low || n > high || (exclusive && n == high) then invalid(s"$name outside supported range")
    if n == 0d then 0d else n
  private def jsonNumber(n: Double): Json = Json.Num(BigDecimal(n).bigDecimal.stripTrailingZeros())
  private def fields(values: (String, Json)*): Json = Json.Obj(zio.Chunk.fromIterable(values))
  private def vector(ra: Double, dec: Double): V =
    val a = math.toRadians(ra); val d = math.toRadians(dec)
    V(math.cos(d)*math.cos(a), math.cos(d)*math.sin(a), math.sin(d))
  private case class V(x: Double,y: Double,z: Double):
    def +(b: V): V = V(x+b.x,y+b.y,z+b.z)
    def *(n: Double): V = V(x*n,y*n,z*n)
    def dot(b: V): Double = x*b.x+y*b.y+z*b.z
    def cross(b: V): V = V(y*b.z-z*b.y,z*b.x-x*b.z,x*b.y-y*b.x)
    def norm: Double = math.sqrt(dot(this))
  private def validatePolygon(points: List[(Double,Double)]): Unit =
    val vs=points.map((a,d)=>vector(a,d))
    val center=vs.reduce(_+_)
    if center.norm < 1e-10 then invalid("Polygon must fit within a hemisphere")
    val signs=vs.indices.map: i =>
      val normal=vs(i).cross(vs((i+1)%vs.size))
      if normal.norm < 1e-10 then invalid("Polygon has duplicate or antipodal vertices")
      val sign=math.signum(normal.dot(center))
      if sign == 0 || vs.exists(v => normal.dot(v)*sign < -1e-12*normal.norm) then invalid("Polygon must be convex and in boundary order")
      sign
    if signs.distinct.size != 1 then invalid("Polygon must be convex")
    val degenerate=vs.sliding(3).forall { p =>
      val first=p(0).cross(p(1));val second=p(1).cross(p(2))
      math.abs(first.dot(p(2))) / (first.norm*second.norm) < 1e-10
    }
    if degenerate then invalid("Polygon is degenerate")
  def fromJson(body: String): Either[ApiError, Query] =
    body.fromJson[Json].left.map(_ => ApiError("invalid_request", "Expected a JSON object")).flatMap:
      case Json.Obj(values) =>
        val numeric=Set("right_ascension_deg","declination_deg","width_arcmin","height_arcmin","channel_index")
        val invalidType=values.exists { (key,value) =>
          if numeric.contains(key) then !value.isInstanceOf[Json.Num]
          else if key == "detector_array" then value match
            case Json.Str("all") | Json.Num(_) => false
            case _ => true
          else if Set("observed_after","observed_before").contains(key) then !value.isInstanceOf[Json.Str]
          else false
        }
        if values.map(_._1).distinct.size != values.size || invalidType then
          Left(ApiError("invalid_request", "JSON properties must have their documented types and appear once"))
        else
          val params=values.map: (key,value) =>
            key -> (value match
              case Json.Str(s) => s
              case Json.Num(n) => n.toString
              case _ => "invalid")
          fromParameters("default",params.toMap)
      case _ => Left(ApiError("invalid_request", "Expected a JSON object"))
  def fromParameters(shape: String, params: Map[String,String]): Either[ApiError, Query] =
    Try:
      def required(name: String) = params.getOrElse(name,invalid(s"Missing $name"))
      def n(name: String) = number(required(name),name)
      def ra(name: String, boundary: Boolean = false) = bounded(n(name),0,360,name,!boundary)
      def dec(name: String) = bounded(n(name),-90,90,name)
      val detector=params.get("detector_array").filter(_ != "all").map: value =>
        val v=number(value,"detector_array")
        if !v.isWhole || v<1 || v>6 then invalid("detector_array must be all or an integer from 1 to 6")
        v.toInt
      val channel=params.get("channel_index").map: value =>
        val v=number(value,"channel_index")
        if !v.isWhole || v<1 || v>102 then invalid("channel_index must be an integer from 1 to 102")
        v.toInt
      val dates=List("observed_after","observed_before").map(name=>params.get(name).map(s=>Try(Instant.parse(s).toString).getOrElse(invalid(s"$name must be an ISO timestamp"))))
      if dates.forall(_.isDefined) && !Instant.parse(dates(0).get).isBefore(Instant.parse(dates(1).get)) then invalid("observed_after must precede observed_before")
      val common=List("detector_array" -> detector.fold[Json](Json.Str("all"))(i=>jsonNumber(i))) ++ channel.map(i=>"channel_index"->jsonNumber(i)) ++ dates.zip(List("observed_after","observed_before")).flatMap((v,k)=>v.map(s=>k->Json.Str(s)))
      val (geometry,position)=shape match
        case "range" =>
          val lo=ra("right_ascension_min_deg",true); val hi=ra("right_ascension_max_deg",true)
          val bottom=dec("declination_min_deg"); val top=dec("declination_max_deg")
          if lo>=hi || bottom>=top then invalid("Range lower boundaries must precede upper boundaries; use polygon for RA wrap")
          if hi-lo>10 || top-bottom>10 then invalid("Supported range span is at most 10 degrees per axis")
          (List("right_ascension_min_deg"->jsonNumber(lo),"right_ascension_max_deg"->jsonNumber(hi),"declination_min_deg"->jsonNumber(bottom),"declination_max_deg"->jsonNumber(top)),s"RANGE $lo $hi $bottom $top")
        case "polygon" =>
          val coords=required("verices_degrees").split(",",-1).toList.map(v=>number(v,"verices_degrees"))
          if coords.size<6 || coords.size%2!=0 || coords.size>128 then invalid("Provide 3 to 64 coordinate pairs")
          val points=coords.grouped(2).map(p=>(bounded(p(0),0,360,"RA"),bounded(p(1),-90,90,"Dec"))).toList
          validatePolygon(points)
          (List("verices_degrees"->Json.Arr(zio.Chunk.fromIterable(coords.map(jsonNumber)))),"POLYGON "+coords.mkString(" "))
        case _ =>
          val a=ra("right_ascension_deg");val d=dec("declination_deg")
          val w=number(params.getOrElse("width_arcmin","3"),"width_arcmin");val h=number(params.getOrElse("height_arcmin","3"),"height_arcmin")
          if w<=0 || h<=0 || w>600 || h>600 then invalid("Supported angular dimensions are greater than 0 and at most 600 arcminutes")
          val c=vector(a,d);val east=V(-math.sin(math.toRadians(a)),math.cos(math.toRadians(a)),0)
          val north=V(-math.sin(math.toRadians(d))*math.cos(math.toRadians(a)),-math.sin(math.toRadians(d))*math.sin(math.toRadians(a)),math.cos(math.toRadians(d)))
          val corners=List((-1,-1),(1,-1),(1,1),(-1,1)).map: (x,y) =>
            val v=c+east*(x*math.tan(math.toRadians(w/120)))+north*(y*math.tan(math.toRadians(h/120)))
            val longitude=(math.toDegrees(math.atan2(v.y,v.x))+360)%360
            val latitude=math.toDegrees(math.atan2(v.z,math.hypot(v.x,v.y)))
            s"$longitude $latitude"
          (List("right_ascension_deg"->jsonNumber(a),"declination_deg"->jsonNumber(d),"width_arcmin"->jsonNumber(w),"height_arcmin"->jsonNumber(h)),"POLYGON "+corners.mkString(" "))
      Query(Json.Obj(zio.Chunk.fromIterable(geometry++common)),position,detector,channel,dates(0),dates(1))
    .toEither.left.map(ApiError.from)

