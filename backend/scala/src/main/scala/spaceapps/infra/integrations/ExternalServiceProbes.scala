package spaceapps.infra.integrations

import spaceapps.infra.model.ApiError
import zio.*
import zio.http.{Client, Request}
import java.io.ByteArrayInputStream
import java.net.URLEncoder
import java.nio.charset.StandardCharsets.UTF_8
import javax.xml.XMLConstants
import javax.xml.parsers.DocumentBuilderFactory
import org.w3c.dom.Element
import org.xml.sax.{ErrorHandler, SAXParseException}

/** Small data-plane probes: capability documents and HTTP status alone never establish health. */
object ExternalServiceProbes:
  private val byteLimit = 512L * 1024

  def irsa(
    client: Client,
    siaEndpoint: String = "https://irsa.ipac.caltech.edu/SIA",
    tapEndpoint: String = "https://irsa.ipac.caltech.edu/TAP/sync"
  ): Map[String, Task[Unit]] =
    Map(
      "irsa_sia" -> request(client, siaEndpoint,
        List("POS" -> "CIRCLE 0 0 0.0001", "COLLECTION" -> "spherex_dr1", "CALIB" -> "2", "DPTYPE" -> "image", "MAXREC" -> "1", "RESPONSEFORMAT" -> "VOTABLE"),
        Set("obs_publisher_did", "access_url", "obs_collection", "energy_bandpassname", "t_min"), allowOverflow = true),
      "irsa_tap" -> request(client, tapEndpoint,
        List("REQUEST" -> "doQuery", "LANG" -> "ADQL", "FORMAT" -> "votable", "MAXREC" -> "1", "QUERY" -> "SELECT TOP 1 table_name FROM TAP_SCHEMA.tables"),
        Set("table_name"), allowOverflow = false)
    )

  private def request(client: Client, endpoint: String, parameters: List[(String, String)], fields: Set[String], allowOverflow: Boolean): Task[Unit] =
    val url = endpoint + (if endpoint.contains("?") then "&" else "?") + parameters.map((key, value) => key + "=" + URLEncoder.encode(value, UTF_8)).mkString("&")
    ZIO.scoped {
      for
        response <- client.request(Request.get(url))
        _ <- ZIO.fail(ApiError("external_probe_http_error", s"External service probe returned HTTP ${response.status.code}", true)).unless(response.status.isSuccess)
        count <- Ref.make(0L)
        bytes <- response.body.asStream.mapChunksZIO { chunk =>
          count.updateAndGet(_ + chunk.size.toLong).flatMap { total =>
            if total > byteLimit then ZIO.fail(ApiError("external_probe_size_limit", "External probe response exceeds 512 KiB"))
            else ZIO.succeed(chunk)
          }
        }.runCollect
        _ <- ZIO.attemptBlocking(validate(bytes.toArray, fields, allowOverflow))
      yield ()
    }.timeoutFail(ApiError("external_probe_timeout", "External data-plane probe timed out", true))(30.seconds)

  private def invalid(): Nothing = throw ApiError("external_probe_invalid_response", "External service did not return a valid one-record results VOTable")
  private def name(element: Element): String = Option(element.getLocalName).getOrElse(element.getNodeName)
  private def children(node: Element, tag: String): List[Element] =
    val nodes = node.getChildNodes
    (0 until nodes.getLength).flatMap { index => nodes.item(index) match
      case element: Element if name(element) == tag => Some(element)
      case _ => None
    }.toList
  private def elements(node: Element, tag: String): List[Element] =
    val nodes = node.getElementsByTagNameNS("*", tag)
    (0 until nodes.getLength).map(index => nodes.item(index).asInstanceOf[Element]).toList

  private def validate(bytes: Array[Byte], expectedFields: Set[String], allowOverflow: Boolean): Unit =
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
      def warning(error: SAXParseException): Unit = ()
      def error(error: SAXParseException): Unit = throw error
      def fatalError(error: SAXParseException): Unit = throw error
    )
    val root = try parser.parse(new ByteArrayInputStream(bytes)).getDocumentElement catch
      case _: org.xml.sax.SAXException => invalid()
    if name(root) != "VOTABLE" then invalid()
    val statuses = elements(root, "INFO").filter(_.getAttribute("name").equalsIgnoreCase("QUERY_STATUS"))
      .map(_.getAttribute("value").toUpperCase(java.util.Locale.ROOT))
    val allowed = if allowOverflow then Set("OK", "OVERFLOW") else Set("OK")
    if statuses.isEmpty || statuses.exists(value => !allowed.contains(value)) then invalid()
    val tables = elements(root, "TABLE")
    if tables.size != 1 then invalid()
    val table = tables.head
    val fields = children(table, "FIELD")
    val names = fields.map(_.getAttribute("name").toLowerCase(java.util.Locale.ROOT))
    if fields.isEmpty || fields.size > 128 || names.exists(_.isEmpty) || names.distinct.size != names.size ||
      !expectedFields.subsetOf(names.toSet) || fields.exists(_.getAttribute("datatype").isEmpty) then invalid()
    val data = children(table, "DATA")
    if data.size != 1 || children(data.head, "TABLEDATA").size != 1 ||
      List("BINARY", "BINARY2", "FITS").exists(tag => elements(data.head, tag).nonEmpty) then invalid()
    val rows = children(children(data.head, "TABLEDATA").head, "TR")
    if rows.size > 1 || (!allowOverflow && rows.isEmpty) then invalid()
    rows.foreach { row =>
      val cells = children(row, "TD")
      if cells.size != fields.size || (!allowOverflow && cells.head.getTextContent.trim.isEmpty) then invalid()
    }
