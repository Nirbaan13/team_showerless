package spaceapps.irsa.integrations

import spaceapps.irsa.model.{ApiError, ArchiveImage}
import zio.*
import zio.http.{Client, Request}
import zio.json.ast.Json
import java.io.ByteArrayInputStream
import java.net.{URI, URLEncoder}
import java.nio.charset.StandardCharsets.UTF_8
import javax.xml.XMLConstants
import javax.xml.parsers.DocumentBuilderFactory
import org.w3c.dom.Element
import org.xml.sax.{ErrorHandler, SAXParseException}

/** Bounded, exact-product TAP lookup. Native science products are never requested here. */
final class TapMetadata(client: Client, endpoint: String, availability: Option[spaceapps.infra.service.ExternalServices] = None):
  private val byteLimit = 2L * 1024 * 1024
  private def invalid(message: String): Nothing = throw ApiError("metadata_invalid_response", message)
  private def obj(fields: (String, Json)*): Json = Json.Obj(Chunk.fromIterable(fields))
  private def arr(values: Iterable[Json]): Json = Json.Arr(Chunk.fromIterable(values))
  private def quote(value: String): String = "'" + value.replace("'", "''") + "'"
  private def identity(image: ArchiveImage): Option[String] =
    def field(key: String): Option[String] = image.observation.header_metadata.get(key).collect { case Json.Str(value) if value.nonEmpty => value }
    for
      did <- field("obs_publisher_did")
      collection <- field("obs_collection")
      access <- field("access_url").orElse(image.sourceUrl).orElse(Option(image.accessUrl).filter(_.nonEmpty))
      uri <- scala.util.Try(URI.create(access)).toOption
      path <- Option(uri.getPath).filter(_.nonEmpty)
    yield
      val artifacts = List(path.stripPrefix("/"), path, access).distinct.map(value => s"a.uri = ${quote(value)}").mkString("(", " OR ", ")")
      s"SELECT TOP 2 o.collection AS obs_collection, p.obs_publisher_did, p.productid, a.uri, a.contentchecksum, a.contentlength, p.quality_flag, p.provenance_version, p.metrics_background, p.metrics_backgroundstddev, p.metrics_fluxdensitylimit, p.time_bounds_lower, p.time_bounds_upper, p.energy_bandpassname FROM spherex.artifact a JOIN spherex.plane p ON a.planeid = p.planeid JOIN spherex.observation o ON p.obsid = o.obsid WHERE p.obs_publisher_did = ${quote(did)} AND o.collection = ${quote(collection)} AND $artifacts"
  def fetch(image: ArchiveImage): Task[Json] =
    availability.fold(fetchDirect(image))(_.call("irsa_tap")(fetchDirect(image)))
  private def fetchDirect(image: ArchiveImage): Task[Json] = identity(image) match
    case None => ZIO.succeed(obj("status" -> Json.Str("unavailable"), "reason" -> Json.Str("Persisted publisher, collection or exact artifact identity is missing")))
    case Some(query) =>
      val parameters = List("REQUEST" -> "doQuery", "LANG" -> "ADQL", "FORMAT" -> "votable", "MAXREC" -> "2", "QUERY" -> query)
      val url = endpoint + (if endpoint.contains("?") then "&" else "?") + parameters.map((key, value) => key + "=" + URLEncoder.encode(value, UTF_8)).mkString("&")
      ZIO.scoped {
        for
          response <- client.request(Request.get(url))
          _ <- ZIO.fail(ApiError("metadata_http_error", s"TAP returned HTTP ${response.status.code}", response.status.code == 429 || response.status.code >= 500)).unless(response.status.isSuccess)
          count <- Ref.make(0L)
          bytes <- response.body.asStream.mapChunksZIO { chunk =>
            count.updateAndGet(_ + chunk.size.toLong).flatMap { size =>
              if size > byteLimit then ZIO.fail(ApiError("metadata_size_limit", "TAP response exceeds the metadata byte limit")) else ZIO.succeed(chunk)
            }
          }.runCollect
          result <- ZIO.attemptBlocking(decode(bytes.toArray))
        yield result
      }.timeoutFail(ApiError("metadata_timeout", "TAP metadata request timed out", true))(15.seconds)
        .mapError {
          case error: ApiError => error
          case _ => ApiError("metadata_unavailable", "TAP metadata could not be retrieved", true)
        }

  private def elements(node: Element, name: String): List[Element] =
    val nodes = node.getElementsByTagNameNS("*", name)
    (0 until nodes.getLength).map(i => nodes.item(i).asInstanceOf[Element]).toList
  private def children(node: Element, name: String): List[Element] =
    val nodes = node.getChildNodes
    (0 until nodes.getLength).flatMap { i => nodes.item(i) match
      case e: Element if e.getLocalName == name => Some(e)
      case _ => None
    }.toList
  private def decode(bytes: Array[Byte]): Json =
    val factory = DocumentBuilderFactory.newInstance()
    factory.setNamespaceAware(true)
    factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true)
    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
    factory.setFeature("http://xml.org/sax/features/external-general-entities", false)
    factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false)
    factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "")
    factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "")
    factory.setXIncludeAware(false)
    factory.setExpandEntityReferences(false)
    val parser = factory.newDocumentBuilder()
    parser.setErrorHandler(new ErrorHandler:
      def warning(e: SAXParseException): Unit = ()
      def error(e: SAXParseException): Unit = throw e
      def fatalError(e: SAXParseException): Unit = throw e
    )
    val root = try parser.parse(new ByteArrayInputStream(bytes)).getDocumentElement catch
      case _: org.xml.sax.SAXException => invalid("TAP returned malformed or unsafe VOTable XML")
    if root.getLocalName != "VOTABLE" then invalid("Expected a TAP VOTable")
    val statuses = elements(root, "INFO").filter(_.getAttribute("name").equalsIgnoreCase("QUERY_STATUS")).map(_.getAttribute("value").toUpperCase(java.util.Locale.ROOT))
    if statuses.contains("ERROR") then throw ApiError("metadata_query_error", "TAP rejected the exact-product metadata query")
    if statuses.contains("OVERFLOW") then throw ApiError("metadata_overflow", "TAP metadata query overflowed its exact-product limit")
    if !statuses.contains("OK") then invalid("TAP response has no successful query status")
    val tables = elements(root, "TABLE")
    if tables.size != 1 then invalid("Expected one TAP results table")
    val table = tables.head
    val fields = children(table, "FIELD")
    val names = fields.map(_.getAttribute("name"))
    if fields.isEmpty || fields.size > 128 || names.exists(_.isEmpty) || names.distinct.size != names.size then invalid("Invalid TAP field declarations")
    val data = children(table, "DATA")
    if data.size != 1 || children(data.head, "TABLEDATA").size != 1 || List("BINARY", "BINARY2", "FITS").exists(name => elements(data.head, name).nonEmpty) then
      invalid("Only TAP TABLEDATA serialization is supported")
    val rows = elements(data.head, "TR")
    if rows.size > 1 then throw ApiError("metadata_ambiguous", "TAP returned multiple artifacts for one exact native image")
    val descriptors = fields.map { field =>
      val attrs = List("name", "datatype", "arraysize", "unit", "ucd", "utype", "ID").flatMap(key => Option(field.getAttribute(key)).filter(_.nonEmpty).map(value => key -> Json.Str(value)))
      val description = children(field, "DESCRIPTION").headOption.map(e => "description" -> Json.Str(e.getTextContent.trim))
      val nullValue = elements(field, "VALUES").headOption.flatMap(e => Option(e.getAttribute("null")).filter(_.nonEmpty)).map(value => "null" -> Json.Str(value))
      Json.Obj(Chunk.fromIterable(attrs ++ description ++ nullValue))
    }
    val decoded = rows.map { row =>
      val cells = children(row, "TD")
      if cells.size != fields.size then invalid("TAP row has an inconsistent field count")
      Json.Obj(Chunk.fromIterable(names.zip(fields.zip(cells).map((field, cell) => value(field, cell.getTextContent)))))
    }
    obj("status" -> Json.Str(if rows.isEmpty then "not_found" else "available"), "fields" -> arr(descriptors), "rows" -> arr(decoded))

  private def value(field: Element, text: String): Json =
    val trimmed = text.trim
    val nullValue = elements(field, "VALUES").headOption.flatMap(e => Option(e.getAttribute("null")).filter(_.nonEmpty))
    val datatype = field.getAttribute("datatype").toLowerCase(java.util.Locale.ROOT)
    def scalar(value: String): Json =
      if nullValue.contains(value) || value.isEmpty || (Set("float", "double").contains(datatype) && value.equalsIgnoreCase("nan")) then Json.Null
      else datatype match
        case "short" | "int" | "long" | "unsignedbyte" =>
          scala.util.Try(BigInt(value)).toOption.map(n => Json.Num(BigDecimal(n))).getOrElse(invalid("Invalid integral TAP value"))
        case "float" | "double" =>
          scala.util.Try(BigDecimal(value.replace('D', 'E').replace('d', 'e'))).toOption.map(Json.Num(_)).getOrElse(invalid("Invalid numeric TAP value"))
        case "boolean" => value.toLowerCase(java.util.Locale.ROOT) match
          case "1" | "true" | "t" => Json.Bool(true)
          case "0" | "false" | "f" => Json.Bool(false)
          case "?" => Json.Null
          case _ => invalid("Invalid boolean TAP value")
        case _ => Json.Str(value)
    if trimmed.isEmpty || nullValue.contains(trimmed) then Json.Null
    else if Set("char", "unicodechar").contains(datatype) then Json.Str(text)
    else if field.getAttribute("arraysize").nonEmpty && field.getAttribute("arraysize") != "1" then arr(trimmed.split("\\s+").toList.map(scalar))
    else scalar(trimmed)
