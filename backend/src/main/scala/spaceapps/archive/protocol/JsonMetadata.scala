package spaceapps.archive.protocol
import spaceapps.archive.*
import zio.json.*
import zio.json.ast.Json
import java.nio.charset.StandardCharsets.UTF_8
object JsonMetadata:
  def parse(bytes: Array[Byte]): Json =
    if bytes.isEmpty || bytes.length>8*1024*1024 then throw ArchiveFailure("invalid_response","Empty or oversized JSON metadata")
    new String(bytes,UTF_8).fromJson[Json].fold(_=>throw ArchiveFailure("invalid_response","Expected structured JSON metadata"),identity)
  def fields(value: Json): Map[String,Json] = value match
    case Json.Obj(v)=>v.toMap
    case _=>throw ArchiveFailure("invalid_response","Expected JSON object")
  def list(value: Json): List[Json] = value match
    case Json.Arr(v)=>v.toList
    case _=>throw ArchiveFailure("invalid_response","Expected JSON array")
  def text(value: Json): String = value match
    case Json.Str(v)=>v
    case v=>v.toJson
  def native(value: Json): Map[String,String] = fields(value).collect { case (k,v) if v!=Json.Null => k->text(v) }
