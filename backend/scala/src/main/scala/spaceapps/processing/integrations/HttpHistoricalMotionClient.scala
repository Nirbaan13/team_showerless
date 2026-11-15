package spaceapps.processing.integrations

import spaceapps.infra.model.ApiError
import zio.*
import zio.json.*
import zio.json.ast.Json
import java.net.URI
import java.net.http.{HttpClient,HttpRequest,HttpResponse,HttpTimeoutException}
import java.nio.file.{Files,Path,LinkOption}
import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest
import java.io.{InputStream,FilterInputStream}

/** The only acquisition input is a leased, managed artifact; redirects are forbidden. */
final class HttpHistoricalMotionClient private(base:URI,client:HttpClient,slots:Semaphore,timeout:Duration):
  private def send(request:HttpRequest):Task[HttpResponse[Array[Byte]]]=ZIO.attemptBlockingInterrupt {
    val future=client.sendAsync(request,(_:HttpResponse.ResponseInfo)=>new LimitedResponseBody(4*1024*1024))
    try future.get(timeout.toMillis,java.util.concurrent.TimeUnit.MILLISECONDS)
    catch case e:java.util.concurrent.ExecutionException=>throw e.getCause
    finally future.cancel(true)
  }.mapError {
    case e:ApiError if e.code=="pipeline_protocol"=>ApiError("motion_protocol","Ivan service response exceeds the supported size")
    case e:ApiError=>e
    case _:HttpTimeoutException | _:java.util.concurrent.TimeoutException=>ApiError("motion_timeout","Ivan's service exceeded its time budget",true)
    case _=>ApiError("motion_unavailable","Ivan's service is unavailable",true)
  }
  def healthy:UIO[Boolean]=send(HttpRequest.newBuilder(base.resolve("/health")).timeout(java.time.Duration.ofSeconds(2)).GET().build())
    .map { response=>
      val document=new String(response.body(),UTF_8).fromJson[Json].toOption.flatMap(_.asObject)
      val historical=document.flatMap(_.get("historical_motion")).flatMap(_.asObject)
      response.statusCode()==200 && document.flatMap(_.get("status")).contains(Json.Str("ok")) &&
        historical.flatMap(_.get("profile")).contains(Json.Str("stellar_proper_motion")) && historical.flatMap(_.get("available")).contains(Json.Bool(true))
    }
    .timeout(3.seconds).map(_.getOrElse(false)).orElseSucceed(false)
  def prepared(id:String,path:Path):Task[Json]=slots.withPermit {
    for
      request <- ZIO.attemptBlocking {
        if !id.matches("[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}") then throw ApiError("invalid_request","Invalid unification ID")
        val bytes=Files.size(path)
        if !Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS) || bytes<=0 || bytes>HttpHistoricalMotionClient.MaxBytes then throw ApiError("invalid_input","Prepared artifact exceeds the 192 MiB transfer limit")
        val digest=MessageDigest.getInstance("SHA-256")
        val input=Files.newInputStream(path,LinkOption.NOFOLLOW_LINKS)
        var count=0L
        try
          val buffer=new Array[Byte](65536);var n=input.read(buffer)
          while n>=0 do
            count+=n
            if count>bytes then throw ApiError("source_changed","Prepared artifact changed before transfer")
            digest.update(buffer,0,n);n=input.read(buffer)
        finally input.close()
        if count!=bytes then throw ApiError("source_changed","Prepared artifact changed before transfer")
        val hash=digest.digest().map(b=>f"${b & 255}%02x").mkString
        val publisher=HttpRequest.BodyPublishers.ofInputStream(()=>new FilterInputStream(Files.newInputStream(path,LinkOption.NOFOLLOW_LINKS)) {
          private var transferred=0L
          override def read(buffer:Array[Byte],offset:Int,length:Int):Int=
            val n=super.read(buffer,offset,math.min(length,math.min(bytes-transferred+1,65536L).toInt))
            if n>0 then transferred+=n
            if transferred>bytes || (n<0 && transferred!=bytes) then throw new java.io.IOException("Prepared artifact changed during transfer")
            n
          override def read():Int=
            val n=super.read()
            if n>=0 then transferred+=1
            if transferred>bytes || (n<0 && transferred!=bytes) then throw new java.io.IOException("Prepared artifact changed during transfer")
            n
        })
        HttpRequest.newBuilder(base.resolve("/internal/motion/prepared")).timeout(java.time.Duration.ofMillis(timeout.toMillis))
          .header("Content-Type","application/octet-stream").header("X-Unification-Id",id).header("X-Artifact-Sha256",hash).POST(publisher).build()
      }
      response <- send(request)
      _ <- ZIO.fail(response.statusCode() match {
        case 400 | 422=>ApiError("motion_invalid_input","Ivan's service could not qualify this historical artifact")
        case 409=>ApiError("motion_artifact_mismatch","Ivan's service rejected artifact identity or checksum")
        case 429 | 503=>ApiError("motion_unavailable","Ivan's service is busy or unavailable",true)
        case _=>ApiError("motion_upstream_error",s"Ivan's service returned HTTP ${response.statusCode()}",true)
      }).unless(response.statusCode()==200)
      _ <- ZIO.fail(ApiError("motion_protocol","Ivan's service did not return JSON")).unless(response.headers().firstValue("Content-Type").orElse("").takeWhile(_!=';').trim=="application/json")
      json <- ZIO.fromEither(new String(response.body(),UTF_8).fromJson[Json]).mapError(_=>ApiError("motion_protocol","Ivan's service returned invalid JSON"))
      _ <- ZIO.fail(ApiError("motion_protocol","Ivan's service returned an invalid review")).when(json.asObject.isEmpty)
    yield json
  }

object HttpHistoricalMotionClient:
  private val MaxBytes=192L*1024*1024
  def make(url:String,concurrency:Int=2,timeout:Duration=180.seconds):Task[HttpHistoricalMotionClient]=for
    uri <- ZIO.attempt {
      val u=URI.create(url)
      if !Set("http","https").contains(u.getScheme) || u.getHost==null || u.getUserInfo!=null || u.getQuery!=null || u.getFragment!=null ||
        !Set("","/").contains(Option(u.getPath).getOrElse("")) || concurrency<1 || concurrency>4 || timeout<=Duration.Zero then
        throw ApiError("invalid_configuration","IVAN_ML_BASE_URL must be a fixed HTTP service origin")
      u
    }
    slots <- Semaphore.make(concurrency)
    client <- ZIO.attempt(HttpClient.newBuilder().connectTimeout(java.time.Duration.ofSeconds(5)).followRedirects(HttpClient.Redirect.NEVER).build())
  yield new HttpHistoricalMotionClient(uri,client,slots,timeout)
