package spaceapps.equipment.integrations

import spaceapps.infra.model.{ApiError, Hash}
import zio.*
import zio.http.{Client, Request, Response}
import zio.json.*
import zio.stream.ZStream
import java.io.ByteArrayInputStream
import java.net.{URI, URLEncoder}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files, Path, StandardOpenOption}
import javax.xml.XMLConstants
import javax.xml.parsers.DocumentBuilderFactory
import org.w3c.dom.Element
import org.xml.sax.{ErrorHandler, SAXParseException}

final case class CalibrationLimits(maxFileBytes: Long = 128L * 1024 * 1024, cacheBytes: Long = 512L * 1024 * 1024, minFreeBytes: Long = 512L * 1024 * 1024)

final case class CalibrationProduct(id: String, product_type: String, version: String, detector_array: Option[Int], release: String,
  source_url: String, download_url: String, file_name: String, size_bytes: Long, detector_relevance: String) derives JsonCodec

/** Anonymous, bounded traversal of the calibration prefixes in IRSA's official public mirror. */
final class CalibrationArchive(client: Client, val baseUrl: String, limits: CalibrationLimits):
  private val base = URI.create(baseUrl)
  private val kinds = Set("abs_gain_matrix", "aurora_template", "dark", "dichroic", "epsf", "gain_factors", "he_template", "l3_flux_corrections",
    "nonfunc_v2", "nonlinear_pars", "readnoise_pars", "shuttle_glow_template", "sip", "solid_angle_pixel_map", "spectral_channels", "spectral_wcs", "xtalk_class1", "xtalk_class2", "xtalk_class3", "zodi_scaling_v1", "zodi_scaling_v2")
  def productTypes: Set[String] = kinds
  private val textLimit = 2L * 1024 * 1024
  private def invalid(message: String): Nothing = throw ApiError("calibration_invalid_response", message)
  private def safeKey(key: String): Boolean = key.length <= 1024 && key.split("/", -1).forall(p => p.nonEmpty && p != "." && p != ".." && p.matches("[A-Za-z0-9_.-]+"))
  def validateConfiguration(): Unit =
    val local = Set("localhost", "127.0.0.1", "[::1]", "::1").contains(base.getHost)
    val official = Set("nasa-irsa-spherex.s3.amazonaws.com", "nasa-irsa-spherex.s3.us-east-1.amazonaws.com").contains(base.getHost)
    if !(official && base.getScheme == "https" || local && base.getScheme == "http") || base.getUserInfo != null || base.getQuery != null || base.getFragment != null || !baseUrl.endsWith("/") then
      throw ApiError("calibration_configuration", "Calibration archive must be the official IRSA mirror or a local fixture")
    if limits.maxFileBytes < 1 || limits.maxFileBytes > 128L * 1024 * 1024 || limits.cacheBytes < 1 || limits.cacheBytes > 512L * 1024 * 1024 || limits.minFreeBytes < 0 then
      throw ApiError("calibration_configuration", "Calibration storage limits are invalid")
  def validate(product: CalibrationProduct): Unit =
    val uri = URI.create(product.source_url)
    val relative = base.relativize(uri).toString
    val parts = relative.split("/")
    if !safeKey(relative) || uri.getScheme != base.getScheme || uri.getRawAuthority != base.getRawAuthority || !uri.getPath.startsWith(base.getPath) ||
      parts.length < 4 || parts(0) != product.release.toLowerCase(java.util.Locale.ROOT) || !Set("dr1", "qr3").contains(parts(0)) || !kinds.contains(parts(1)) ||
      product.id != Hash.sha256(product.release + "|" + product.source_url) || product.file_name != parts.last || product.product_type != parts(1) || product.version != parts(2) || product.size_bytes < 1 then
      invalid("Stored calibration identity is outside the configured archive")
  private def check(response: Response): Task[Unit] =
    if response.status.code == 200 then ZIO.unit
    else ZIO.fail(ApiError("calibration_unavailable", s"Calibration archive returned HTTP ${response.status.code}", true))
  private def bounded(response: Response, max: Long): ZStream[Any, Throwable, Byte] = ZStream.unwrap {
    Ref.make(0L).map { count => response.body.asStream.mapChunksZIO { bytes =>
      count.updateAndGet(_ + bytes.size).flatMap(n => if n > max then ZIO.fail(ApiError("calibration_size_limit", "Calibration response exceeded its byte limit")) else ZIO.succeed(bytes))
    } }
  }
  private def transport(error: Throwable): Throwable = error match
    case e: ApiError => e
    case _ => ApiError("calibration_unavailable", "Calibration archive transfer failed", true)
  private def text(url: String): Task[String] = ZIO.scoped {
    for
      response <- client.request(Request.get(url))
      _ <- check(response)
      bytes <- bounded(response, textLimit).runCollect
    yield new String(bytes.toArray, UTF_8)
  }.timeoutFail(ApiError("calibration_timeout", "Calibration directory request timed out", true))(30.seconds).mapError(transport)
  private def elements(node: Element, tag: String): List[Element] =
    val nodes = node.getElementsByTagNameNS("*", tag)
    (0 until nodes.getLength).map(i => nodes.item(i).asInstanceOf[Element]).toList
  private def value(node: Element, tag: String): String = elements(node, tag).headOption.map(_.getTextContent.trim).getOrElse(invalid(s"Calibration listing is missing $tag"))
  private final case class Page(prefixes: List[String], files: List[(String, Long)], next: Option[String])
  private def parse(body: String): Page =
    val factory = DocumentBuilderFactory.newInstance()
    factory.setNamespaceAware(true)
    factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING,true)
    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl",true)
    factory.setFeature("http://xml.org/sax/features/external-general-entities",false)
    factory.setFeature("http://xml.org/sax/features/external-parameter-entities",false)
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
    val root = try parser.parse(new ByteArrayInputStream(body.getBytes(UTF_8))).getDocumentElement catch
      case _: org.xml.sax.SAXException => invalid("Malformed or unsafe calibration listing XML")
    if root.getLocalName != "ListBucketResult" then invalid("Expected an IRSA mirror directory listing")
    val truncated = value(root, "IsTruncated") match
      case "true" => true
      case "false" => false
      case _ => invalid("Invalid listing truncation flag")
    val token = Option.when(truncated)(value(root, "NextContinuationToken"))
    if token.exists(t => t.isEmpty || t.length > 4096) then invalid("Invalid listing continuation token")
    val files = elements(root, "Contents").map(e => value(e,"Key") -> value(e,"Size").toLongOption.getOrElse(invalid("Invalid calibration file size")))
    val prefixes = elements(root,"CommonPrefixes").map(value(_,"Prefix"))
    if files.size + prefixes.size > 1000 then invalid("Oversized calibration directory page")
    Page(prefixes,files,token)
  private def listing(prefix: String, shallow: Boolean, token: Option[String] = None, page: Int = 0): Task[Page] =
    if page >= 4 then ZIO.fail(ApiError("calibration_catalog_limit", "Calibration directory exceeds the bounded pagination limit"))
    else
      val params = List("list-type" -> "2", "max-keys" -> "1000", "prefix" -> prefix) ++ Option.when(shallow)("delimiter" -> "/") ++ token.map("continuation-token" -> _)
      val url = baseUrl + "?" + params.map((k,v) => k + "=" + URLEncoder.encode(v,UTF_8)).mkString("&")
      for
        body <- text(url)
        current <- ZIO.attemptBlocking(parse(body))
        following <- current.next match
          case Some(next) if !token.contains(next) => listing(prefix,shallow,Some(next),page+1)
          case Some(_) => ZIO.fail(ApiError("calibration_invalid_response", "Repeated calibration continuation token"))
          case None => ZIO.succeed(Page(Nil,Nil,None))
      yield Page(current.prefixes ++ following.prefixes,current.files ++ following.files,None)
  def discover(release: String): Task[List[CalibrationProduct]] =
    val prefix = release.toLowerCase(java.util.Locale.ROOT) + "/"
    for
      root <- listing(prefix,true)
      names <- ZIO.attempt {
        if root.prefixes.size > 64 || root.files.nonEmpty then invalid("Unexpected release directory structure")
        root.prefixes.foreach { p => if !p.startsWith(prefix) || !safeKey(p.stripSuffix("/")) || p.stripSuffix("/").split("/").length != 2 then invalid("Unsafe calibration directory prefix") }
        root.prefixes.filter(p => kinds.contains(p.stripSuffix("/").split("/").last)).distinct
      }
      groups <- ZIO.foreachPar(names) { path => listing(path,false).flatMap { page => ZIO.attempt {
        if page.prefixes.nonEmpty then invalid("Unexpected nested calibration listing")
        page.files.map { (key,size) =>
          if !key.startsWith(path) || !safeKey(key) || size < 1 then invalid("Unsafe calibration file key or size")
          val parts = key.split("/")
          if parts.length < 4 then invalid("Calibration file is missing version provenance")
          val name = parts.last
          if !name.matches("(?i).+\\.(fits|fit|fts|ecsv|yaml|yml|csv)(\\.gz)?") then invalid("Unsupported calibration file type")
          val detector = "(?i)(?:^|_)D([1-6])(?:_|\\.)".r.findFirstMatchIn(name).map(_.group(1).toInt)
          val pathDetector = parts.drop(3).dropRight(1).find(_.matches("[1-6]")).map(_.toInt)
          if pathDetector.nonEmpty && pathDetector != detector then invalid("Calibration detector identities disagree")
          val url = base.resolve(key).toString
          val id = Hash.sha256(release + "|" + url)
          CalibrationProduct(id,parts(1),parts(2),detector,release,url,s"/api/equipment/calibrations/$id",name,size,if detector.isDefined then "single_detector" else "all_detectors")
        }
      } } }.withParallelism(4)
      products = groups.flatten.distinctBy(_.id).sortBy(_.source_url)
      _ <- ZIO.fail(ApiError("calibration_unavailable", "No calibration files were discovered in the release directory",true)).when(products.isEmpty)
      _ <- ZIO.fail(ApiError("calibration_catalog_limit", "Calibration catalogue exceeds 4096 files")).when(products.size > 4096)
    yield products
  def fetch(product: CalibrationProduct, destination: Path): Task[Unit] =
    (ZIO.attempt(validate(product)) *> ZIO.scoped {
      for
        response <- client.request(Request.get(product.source_url))
        _ <- check(response)
        _ <- ZIO.fail(ApiError("calibration_invalid_response", "Calibration archive returned an HTML document")).when(response.headers.get("Content-Type").exists(_.toLowerCase.contains("text/html")))
        out <- ZIO.acquireRelease(ZIO.attemptBlocking(Files.newOutputStream(destination,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)))(o => ZIO.attemptBlocking(o.close()).orDie)
        _ <- bounded(response, math.min(limits.maxFileBytes,product.size_bytes)).chunks.runForeach(c => ZIO.attemptBlocking(out.write(c.toArray)))
      yield ()
    } *> ZIO.attemptBlocking {
      if Files.size(destination) != product.size_bytes then invalid("Calibration transfer size differs from directory metadata")
    }).timeoutFail(ApiError("calibration_timeout", "Calibration file transfer timed out",true))(3.minutes).mapError(transport)
