package spaceapps.processing.integrations

import spaceapps.infra.model.ApiError
import zio.*
import zio.json.*
import zio.json.ast.Json
import java.net.URI
import java.net.http.{HttpClient,HttpRequest,HttpResponse,HttpTimeoutException}
import java.nio.charset.StandardCharsets.UTF_8

final case class PipelineResponse(bytes:Array[Byte],contentType:String)

/** Bounded transport to the team pipeline and its independent unification module. */
final class HttpPipelineClient private(base:URI,client:HttpClient,slots:Semaphore,timeout:Duration):
  private val routes=Set("/api/cutout/search","/api/cutout/render","/api/spectrum","/api/spectrum/measure","/internal/image-unifications")
  def unify(body:Json):Task[Json]=
    request("POST","/internal/image-unifications",body=Some(body)).flatMap { response=>
      ZIO.fromEither(new String(response.bytes,UTF_8).fromJson[Json])
        .mapError(_=>ApiError("pipeline_protocol","The unification pipeline returned invalid JSON"))
    }
  def request(method:String,path:String,query:String="",body:Option[Json]=None):Task[PipelineResponse]=slots.withPermit {
    ZIO.attemptBlockingInterrupt {
      if !routes.contains(path) || !Set("GET","POST").contains(method) then throw ApiError("invalid_request","Unsupported pipeline operation")
      val destination=base.resolve(path+(if query.isEmpty then "" else "?"+query))
      val builder=HttpRequest.newBuilder(destination).timeout(java.time.Duration.ofMillis(timeout.toMillis))
      val request=if method=="GET" then builder.GET().build()
        else builder.header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(body.getOrElse(Json.Obj()).toJson,UTF_8)).build()
      val limit=if path=="/api/cutout/render" then 32*1024*1024 else 4*1024*1024
      val future=client.sendAsync(request,(_:HttpResponse.ResponseInfo)=>new LimitedResponseBody(limit))
      val response=try future.get(timeout.toMillis,java.util.concurrent.TimeUnit.MILLISECONDS)
        catch case e:java.util.concurrent.ExecutionException=>throw e.getCause
        finally future.cancel(true)
      response.statusCode() match
        case 200=>()
        case 404=>throw ApiError("pipeline_not_found","The pipeline found no usable data for this request")
        case 400 | 422=>throw ApiError("pipeline_invalid_request","The pipeline rejected the request")
        case 429 | 503=>throw ApiError("pipeline_unavailable","The pipeline is busy or unavailable",true)
        case 504=>throw ApiError("pipeline_timeout","The pipeline exceeded its time budget",true)
        case _=>throw ApiError("pipeline_upstream_error","The Python pipeline returned an error; inspect its service logs",true)
      val bytes=response.body()
      val media=response.headers().firstValue("Content-Type").orElse("").takeWhile(_!=';').trim
      if path=="/api/cutout/render" then
        if media!="image/png" || bytes.take(8).toList!=List[Byte](-119,80,78,71,13,10,26,10) then
          throw ApiError("pipeline_protocol","The pipeline did not return a valid PNG")
      else
        if media!="application/json" then throw ApiError("pipeline_protocol","The pipeline did not return JSON")
        val document=new String(bytes,UTF_8).fromJson[Json].fold(_=>throw ApiError("pipeline_protocol","The pipeline returned invalid JSON"),identity)
        if document.asObject.isEmpty then throw ApiError("pipeline_protocol","The pipeline returned an invalid JSON object")
        if document.asObject.flatMap(_.get("error")).exists(v=>v!=Json.Null && v!=Json.Str("")) then
          throw ApiError("pipeline_upstream_error","The pipeline reported an archive or processing failure",true)
      PipelineResponse(bytes,media)
    }.mapError {
      case e:ApiError=>e
      case _:HttpTimeoutException | _:java.util.concurrent.TimeoutException=>ApiError("pipeline_timeout","The pipeline HTTP request timed out",true)
      case _=>ApiError("pipeline_unavailable","The pipeline HTTP service is unavailable",true)
    }
  }

object HttpPipelineClient:
  def make(url:String,concurrency:Int=2,timeout:Duration=180.seconds):Task[HttpPipelineClient]=
    for
      uri<-ZIO.attempt {
        val u=URI.create(url)
        if !Set("http","https").contains(u.getScheme) || u.getHost==null || u.getUserInfo!=null ||
          u.getQuery!=null || u.getFragment!=null || !Set("","/").contains(Option(u.getPath).getOrElse("")) ||
          concurrency<1 || concurrency>4 || timeout<=Duration.Zero then throw ApiError("invalid_configuration","Invalid PROCESSING_URL or processing limits")
        u
      }
      slots<-Semaphore.make(concurrency)
      client<-ZIO.attempt(HttpClient.newBuilder().connectTimeout(java.time.Duration.ofSeconds(5)).followRedirects(HttpClient.Redirect.NEVER).build())
    yield new HttpPipelineClient(uri,client,slots,timeout)
