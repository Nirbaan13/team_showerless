package spaceapps.downloads.integrations.protocol
import spaceapps.downloads.model.*
import zio.*
import zio.http.*
import zio.stream.ZStream
import java.net.{URI,URLEncoder}
import java.nio.charset.StandardCharsets.UTF_8

final case class OriginPolicy(hosts: Set[String],localOrigins: Set[String] = Set.empty):
  def validate(value: String): URI =
    val uri=try URI.create(value) catch case _: Exception=>throw ArchiveFailure("untrusted_origin","Malformed archive URL")
    val host=Option(uri.getHost).getOrElse("").toLowerCase(java.util.Locale.ROOT)
    val origin=s"${uri.getScheme}://${uri.getRawAuthority}"
    if uri.getUserInfo!=null || uri.getFragment!=null || !(uri.getScheme=="https" && hosts(host) && (uri.getPort == -1 || uri.getPort==443) || localOrigins(origin)) then
      throw ArchiveFailure("untrusted_origin","Archive URL is outside provider origins")
    uri
object OriginPolicy:
  val eso=OriginPolicy(Set("archive.eso.org","dataportal.eso.org"))
  val cadc=OriginPolicy(Set("ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca","www.cadc-ccda.hia-iha.nrc-cnrc.gc.ca","cadc.cadc-ccda.hia-iha.nrc-cnrc.gc.ca","cadc-west-01.canfar.net","cadc-west-02.canfar.net","ws-cadc.canfar.net","ws-uv.canfar.net","ws-sf.canfar.net"))
  val gaia=OriginPolicy(Set("gea.esac.esa.int"))
  val bass=OriginPolicy(Set("nadc.china-vo.org","das101.china-vo.org"))
  val artxc=OriginPolicy(Set("heaiki.ru"))
  val lamost=OriginPolicy(Set("www.lamost.org","dr11.lamost.org"))
  val irsa=OriginPolicy(Set("irsa.ipac.caltech.edu","nasa-irsa-spherex.s3.amazonaws.com","nasa-irsa-spherex.s3.us-east-1.amazonaws.com"))
  def forProvider(id: String): OriginPolicy = id match
    case "eso"=>eso
    case "cadc"=>cadc
    case "esa-gaia"=>gaia
    case "nadc-bass"=>bass
    case "iki-artxc" | "iki-artxc-catalog"=>artxc
    case "lamost"=>lamost
    case "irsa-spherex"=>irsa
    case _=>OriginPolicy(Set.empty)

final class ArchiveTransport(client: Client,val metadataBytes: Long = 8L*1024*1024,val requestTimeout: Duration = 30.seconds):
  def response[A](url: String,policy: OriginPolicy,method: String = "GET",body: String = "",contentType: String = "",redirects: Int = 0)(use: Response=>Task[A]): IO[ArchiveFailure,A] =
    ZIO.scoped {
      for
        _ <- ZIO.attempt(policy.validate(url))
        request=if method=="POST" then Request.post(url,Body.fromString(body)).addHeader(Header.Custom("Content-Type",contentType)) else Request.get(url)
        response <- client.request(request)
        result <- if Set(301,302,303,307,308)(response.status.code) then
          if redirects>=5 then ZIO.fail(ArchiveFailure("redirect_limit","Too many archive redirects"))
          else
            val location=response.headers.get("Location").getOrElse("")
            val target=URI.create(url).resolve(location).toString
            if Set(307,308)(response.status.code) then this.response(target,policy,method,body,contentType,redirects+1)(use)
            else this.response(target,policy,redirects=redirects+1)(use)
        else if response.status.code==204 then ZIO.fail(ArchiveFailure("no_content","Requested subset contains no product"))
        else if response.status.code==401 || response.status.code==403 then ZIO.fail(ArchiveFailure("requires_auth","Archive product requires authorization"))
        else if response.status.code<200 || response.status.code>=300 then
          ZIO.fail(ArchiveFailure("http_error",s"Archive returned HTTP ${response.status.code}",Set(408,429,500,502,503,504)(response.status.code),response.headers.get("Retry-After").flatMap(s=>ArchiveTransport.retryAfter(s))))
        else use(response)
      yield result
    }.mapError(ArchiveFailure.from)
  def bounded(response: Response,limit: Long): ZStream[Any,Throwable,Byte] = ZStream.unwrap {
    Ref.make(0L).map(ref=>response.body.asStream.mapChunksZIO { c=>ref.updateAndGet(_+c.size).flatMap(n=>if n>limit then ZIO.fail(ArchiveFailure("byte_limit","Archive response exceeds byte budget")) else ZIO.succeed(c)) })
  }
  def metadata(url: String,policy: OriginPolicy,method: String = "GET",body: String = "",contentType: String = ""): IO[ArchiveFailure,Array[Byte]] =
    response(url,policy,method,body,contentType)(r=>bounded(r,metadataBytes).runCollect.map(_.toArray))
      .timeoutFail(ArchiveFailure("timeout","Archive metadata request timed out",true))(requestTimeout)
object ArchiveTransport:
  def retryAfter(value: String,now: java.time.Instant = java.time.Instant.now()): Option[Long] =
    value.toLongOption.filter(_>=0).orElse(scala.util.Try(java.time.ZonedDateTime.parse(value,java.time.format.DateTimeFormatter.RFC_1123_DATE_TIME).toInstant).toOption.map(t=>math.max(0L,java.time.Duration.between(now,t).getSeconds)))
  def params(base: String,values: List[(String,String)]): String = base+(if base.contains("?") then "&" else "?")+values.map((k,v)=>URLEncoder.encode(k,UTF_8)+"="+URLEncoder.encode(v,UTF_8)).mkString("&")
