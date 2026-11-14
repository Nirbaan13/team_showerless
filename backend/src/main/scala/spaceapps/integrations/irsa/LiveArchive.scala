package spaceapps.integrations.irsa

import spaceapps.domain.*
import spaceapps.service.Archive

import zio.*
import zio.http.{Client, Request, Response}
import zio.stream.ZStream
import zio.json.ast.Json
import java.io.{ByteArrayInputStream, IOException}
import java.net.{URI, URLEncoder}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files, Path, StandardOpenOption}
import java.time.Instant
import java.util.concurrent.TimeoutException
import javax.xml.XMLConstants
import javax.xml.parsers.DocumentBuilderFactory
import org.w3c.dom.Element
import org.xml.sax.{ErrorHandler, SAXParseException}

/** Retrieves native SPHEREx products; metadata discovery never requests image bytes. */
final class LiveArchive(
  client: Client,
  endpoint: String = "https://irsa.ipac.caltech.edu/SIA",
  maxRecords: Int = 256,
  maxBytes: Long = 268435456L,
  channelBands: Map[Int, (Double, Double)] = Map.empty
) extends Archive:
  private val metadataLimit = 8L * 1024 * 1024
  private def invalid(message: String): Nothing = throw ApiError("archive_invalid_response", message)
  private def checkedConfiguration(): Unit =
    if maxRecords < 1 || maxBytes < 2880 then throw ApiError("archive_configuration", "Archive record and byte limits must be positive and support a FITS record")
    channelBands.foreach { case (channel, (lo, hi)) =>
      if channel < 1 || channel > 102 || !lo.isFinite || !hi.isFinite || lo <= 0 || hi < lo then
        throw ApiError("archive_configuration", "Channel wavelength intervals must be finite, positive metre values")
    }
  private def trustedUrl(value: String): URI =
    val uri = try URI.create(value) catch case _: IllegalArgumentException => invalid("Malformed product access URL")
    val configured = URI.create(endpoint)
    val host = Option(uri.getHost).getOrElse("").toLowerCase(java.util.Locale.ROOT)
    val configuredHost = Option(configured.getHost).getOrElse("").toLowerCase(java.util.Locale.ROOT)
    val official = Set("irsa.ipac.caltech.edu", "nasa-irsa-spherex.s3.amazonaws.com", "nasa-irsa-spherex.s3.us-east-1.amazonaws.com").contains(host)
    val local = Set("localhost", "127.0.0.1", "::1", "[::1]").contains(configuredHost)
    val secure = uri.getScheme == "https"
    val localHttp = local && configured.getScheme == "http" && uri.getScheme == "http" && uri.getRawAuthority == configured.getRawAuthority
    if host.isEmpty || uri.getUserInfo != null || uri.getFragment != null || !(official || host == configuredHost) || !(secure || localHttp) then
      throw ApiError("archive_untrusted_url", "Product access URL is outside the configured archive")
    uri
  private def mjd(value: String): String =
    val instant = Instant.parse(value)
    (40587d + (instant.getEpochSecond.toDouble + instant.getNano.toDouble / 1e9) / 86400d).toString
  private def searchUrl(query: Query): String =
    checkedConfiguration()
    trustedUrl(endpoint)
    val band = query.channel.map { channel =>
      val (lo, hi) = channelBands.getOrElse(channel, throw ApiError("unsupported_channel", "No authoritative wavelength calibration is configured for this channel"))
      "BAND" -> s"$lo $hi"
    }
    val time = Option.when(query.after.nonEmpty || query.before.nonEmpty)("TIME" -> s"${query.after.fold("-Inf")(mjd)} ${query.before.fold("+Inf")(mjd)}")
    val params = List("POS" -> query.position, "COLLECTION" -> "spherex_dr1", "COLLECTION" -> "spherex_qr3", "CALIB" -> "2", "DPTYPE" -> "image", "MAXREC" -> maxRecords.toString, "RESPONSEFORMAT" -> "VOTABLE") ++ band ++ time
    endpoint + (if endpoint.contains("?") then "&" else "?") + params.map((key, value) => key + "=" + URLEncoder.encode(value, UTF_8)).mkString("&")
  private def transportError(error: Throwable): ApiError = error match
    case e: ApiError => e
    case _ => ApiError("archive_unavailable", "The archive connection could not complete the transfer", true)
  private def request(url: String): ZIO[Scope, Throwable, Response] =
    client.request(Request.get(url))
      .tapError(error => ZIO.logWarningCause("Archive connection failed", Cause.fail(error)))
      .mapError(transportError)
  private def bounded(response: Response, limit: Long): ZStream[Any, Throwable, Byte] =
    ZStream.unwrap {
      Ref.make(0L).map { count =>
        response.body.asStream.tapError(error => ZIO.logWarningCause("Archive response stream failed", Cause.fail(error))).mapError(transportError).mapChunksZIO { bytes =>
          count.updateAndGet(_ + bytes.size.toLong).flatMap { size =>
            if size > limit then ZIO.fail(ApiError("archive_size_limit", "Archive response exceeds the configured byte limit")) else ZIO.succeed(bytes)
          }
        }
      }
    }
  private def checkStatus(response: Response): Task[Unit] =
    val status = response.status.code
    if status >= 200 && status < 300 then ZIO.unit
    else ZIO.fail(ApiError("archive_http_error", s"Archive returned HTTP $status", Set(408, 429, 500, 502, 503, 504).contains(status)))
  private def retryable(error: Throwable): Boolean = error match
    case e: ApiError => e.retryable
    case _: IOException | _: TimeoutException => true
    case _ => false
  private def retry[A](effect: => Task[A], attempts: Int = 0): Task[A] =
    effect.catchAll { error =>
      if attempts < 2 && retryable(error) then ZIO.sleep(Duration.fromMillis(200L << attempts)) *> retry(effect, attempts + 1)
      else ZIO.fail(error)
    }
  def search(query: Query): Task[List[ArchiveImage]] =
    ZIO.attempt(searchUrl(query)).flatMap { url =>
      retry {
        ZIO.scoped {
          for
            response <- request(url)
            _ <- checkStatus(response)
            bytes <- bounded(response, metadataLimit).runCollect
            images <- ZIO.attemptBlocking(decode(bytes.toArray, query))
          yield images
        }.timeoutFail(ApiError("archive_timeout", "Archive metadata request timed out", true))(30.seconds)
      }
    }
  def fetch(image: ArchiveImage, destination: Path): Task[Unit] =
    ZIO.attempt { checkedConfiguration(); trustedUrl(image.accessUrl) }.flatMap { uri =>
      retry {
        (ZIO.scoped {
          for
            response <- request(uri.toString)
            _ <- checkStatus(response)
            output <- ZIO.acquireRelease(ZIO.attemptBlocking(Files.newOutputStream(destination, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE)))(out => ZIO.attemptBlocking(out.close()).orDie)
            _ <- bounded(response, maxBytes).chunks.runForeach(bytes => ZIO.attemptBlocking(output.write(bytes.toArray)))
          yield ()
        } *> ZIO.attemptBlocking {
          val length = Files.size(destination)
          val input = Files.newInputStream(destination)
          val signature = try new String(input.readNBytes(30), UTF_8) finally input.close()
          if length < 2880 || length % 2880 != 0 || !signature.startsWith("SIMPLE  =") || signature.drop(10).trim != "T" then
            throw ApiError("archive_invalid_fits", "Native product is not a complete FITS file")
        })
          .timeoutFail(ApiError("archive_timeout", "Archive product transfer timed out", true))(5.minutes)
          .onExit(exit => if exit.isSuccess then ZIO.unit else ZIO.attemptBlocking(Files.deleteIfExists(destination)).ignore)
      }
    }
  private def elements(node: Element, name: String): List[Element] =
    val list = node.getElementsByTagNameNS("*", name)
    (0 until list.getLength).map(i => list.item(i).asInstanceOf[Element]).toList
  private def children(node: Element, name: String): List[Element] =
    val list = node.getChildNodes
    (0 until list.getLength).flatMap { i => list.item(i) match
      case element: Element if element.getLocalName == name => Some(element)
      case _ => None
    }.toList
  private def decode(bytes: Array[Byte], query: Query): List[ArchiveImage] =
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
      case _: org.xml.sax.SAXException => invalid("Archive returned malformed or unsafe VOTable XML")
    if root.getLocalName != "VOTABLE" then invalid("Expected an archive VOTable")
    val statuses = elements(root, "INFO").filter(_.getAttribute("name").equalsIgnoreCase("QUERY_STATUS")).map(_.getAttribute("value").toUpperCase(java.util.Locale.ROOT))
    if statuses.contains("ERROR") then throw ApiError("archive_query_error", "Archive rejected the metadata query")
    if statuses.contains("OVERFLOW") then throw ApiError("archive_overflow", "Archive result exceeds the configured record limit; narrow the search region or time range")
    if statuses.isEmpty || statuses.exists(_ != "OK") then invalid("Archive response is missing a successful query status")
    val tables = elements(root, "TABLE")
    if tables.size != 1 then invalid("Expected one archive results table")
    val table = tables.head
    val fields = children(table, "FIELD").map(_.getAttribute("name").toLowerCase(java.util.Locale.ROOT))
    if fields.distinct.size != fields.size then invalid("Duplicate archive table fields")
    if !Set("obs_publisher_did", "obs_collection", "energy_bandpassname", "t_min", "access_url").subsetOf(fields.toSet) then
      invalid("Archive table is missing required product metadata fields")
    val data = elements(table, "DATA")
    if data.size != 1 || children(data.head, "TABLEDATA").size != 1 || List("BINARY", "BINARY2", "FITS").exists(name => elements(data.head, name).nonEmpty) then
      invalid("Only TABLEDATA archive serialization is supported")
    val rows = elements(data.head, "TR")
    if rows.size > maxRecords then throw ApiError("archive_overflow", "Archive returned more records than requested")
    rows.flatMap { row =>
      val values = children(row, "TD").map(_.getTextContent.trim)
      if values.size != fields.size then invalid("Archive table row has an inconsistent field count")
      val metadata = fields.zip(values).filter(_._2.nonEmpty).toMap
      def required(name: String): String = metadata.getOrElse(name, invalid(s"Archive result is missing $name"))
      def number(name: String): Option[Double] = metadata.get(name).map { value =>
        val n = value.toDoubleOption.getOrElse(invalid(s"Invalid archive $name"))
        if !n.isFinite then invalid(s"Non-finite archive $name")
        n
      }
      val collection = required("obs_collection")
      val release = collection match
        case "spherex_dr1" => "DR1"
        case "spherex_qr3" => "QR3"
        case _ => invalid("Archive returned an unexpected release")
      val detector = "(?i)^SPHEREx-D([1-6])$".r.findFirstMatchIn(required("energy_bandpassname")).map(_.group(1).toInt).getOrElse(invalid("Missing SPHEREx detector identity"))
      if query.detector.exists(_ != detector) then Nil
      else
        val access = trustedUrl(required("access_url")).toString
        val did = required("obs_publisher_did")
        val time = number("t_min").getOrElse(invalid("Archive result is missing observation time"))
        val seconds = (time - 40587d) * 86400d
        val whole = math.floor(seconds).toLong
        val date = Instant.ofEpochSecond(whole, math.round((seconds - whole) * 1e9)).toString
        val observation = Observation(s"$release-D$detector-${Hash.sha256(collection + "|" + detector + "|" + did)}", date, detector, release,
          wavelength_min_um = number("em_min").map(_ * 1e6), wavelength_max_um = number("em_max").map(_ * 1e6),
          header_metadata = metadata.map((key, value) => key -> Json.Str(value)))
        List(ArchiveImage(observation, access))
    }.distinctBy(_.observation.frame_id)
