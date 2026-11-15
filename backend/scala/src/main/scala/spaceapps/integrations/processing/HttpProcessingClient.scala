package spaceapps.integrations.processing

import spaceapps.domain.{ApiError,Query}
import spaceapps.service.{Processor,SpectrumProcessor,SpectrumResult}
import zio.*
import zio.json.*
import zio.json.ast.Json
import java.net.URI
import java.net.http.{HttpClient,HttpRequest,HttpResponse,HttpTimeoutException}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Path}

/** Calls the team pipeline over the private Docker network; files share /app/data. */
final class HttpProcessingClient private(base:URI,client:HttpClient,slots:Semaphore,deadline:Duration) extends Processor with SpectrumProcessor:
  override val supportedModes=Set("zodi_reference_subtracted")
  private def property(value:Json,key:String):Option[Json]=value.asObject.flatMap(_.get(key))
  private def string(value:Json,key:String):Option[String]=property(value,key).flatMap(_.asString)
  private def request(operation:String,image:Option[Path]=None,output:Option[Path]=None,extra:List[(String,Json)]=Nil):Task[Json]=slots.withPermit {
    val body=Json.Obj(Chunk.fromIterable(List("operation"->Json.Str(operation)) ++
      image.map(p=>"image_path"->Json.Str(p.toAbsolutePath.normalize.toString)) ++
      output.map(p=>"output_path"->Json.Str(p.toAbsolutePath.normalize.toString)) ++ extra)).toJson
    // Defer caller cancellation until the bounded remote operation completes.
    // Its input/output leases belong to the surrounding Jobs/Spectrum scope.
    ZIO.attemptBlocking {
      if body.getBytes(UTF_8).length>65536 then throw ApiError("processing_request_limit","Processing request exceeds 64 KiB")
      val request=HttpRequest.newBuilder(base.resolve("/internal/processing"))
        .timeout(java.time.Duration.ofMillis(deadline.toMillis)).header("Content-Type","application/json")
        .POST(HttpRequest.BodyPublishers.ofString(body,UTF_8)).build()
      val pending=client.sendAsync(request,(_:HttpResponse.ResponseInfo)=>new LimitedResponseBody())
      val response=try pending.get(deadline.toMillis,java.util.concurrent.TimeUnit.MILLISECONDS)
        catch case e:java.util.concurrent.ExecutionException=>throw e.getCause
        finally pending.cancel(true)
      val bytes=response.body()
      val document=new String(bytes,UTF_8).fromJson[Json].fold(_=>throw ApiError("processing_protocol","Invalid pipeline response"),identity)
      if response.statusCode()!=200 || !string(document,"status").contains("ok") then
        val error=property(document,"error").getOrElse(Json.Obj())
        val code=if response.statusCode()==504 then "timeout" else string(error,"code").filter(_.matches("[a-z_]{1,64}")).getOrElse(if response.statusCode()==503 then "unavailable" else "failed")
        throw ApiError("processing_"+code,if code=="no_measurements" then "No usable complete aperture with spectral coordinates was found" else "The pipeline could not complete image processing",response.statusCode()>=500)
      document
    }.mapError {
      case e:ApiError=>e
      case _:HttpTimeoutException=>ApiError("processing_timeout","The pipeline HTTP request timed out",true)
      case _:java.util.concurrent.TimeoutException=>ApiError("processing_timeout","The pipeline HTTP response timed out",true)
      case _=>ApiError("processing_unavailable","The pipeline HTTP service is unavailable",true)
    }.uninterruptible
  }
  private def produce(operation:String,image:Path,output:Path):Task[Unit]=
    request(operation,Some(image),Some(output)).flatMap { result=>
      ZIO.attemptBlocking {
        if !string(result,"operation").contains(operation) ||
          !string(result,"output_path").contains(output.toAbsolutePath.normalize().toString) ||
          !Files.isRegularFile(output) || Files.size(output)==0 || Files.size(output)>256L*1024*1024 then
          throw ApiError("processing_protocol","Python did not produce the requested output file")
        val input=Files.newInputStream(output)
        val signature=try input.readNBytes(30) finally input.close()
        val valid=if operation=="preview" then signature.take(8).toList==List[Byte](-119,80,78,71,13,10,26,10)
          else new String(signature,UTF_8).startsWith("SIMPLE  =") && Files.size(output)%2880==0
        if !valid then throw ApiError("processing_protocol","Python produced an invalid resource format")
      }
    }
  def prepare(image:Path,output:Path,mode:String,reference:Option[Path],query:Query):Task[Unit]=
    if mode!="zodi_reference_subtracted" || reference.nonEmpty then ZIO.fail(ApiError("unsupported_processing","The requested scientific mode is not validated"))
    else produce("zodi",image,output)
  def preview(image:Path,output:Path):Task[Unit]=produce("preview",image,output)
  def measure(inputs:List[(String,Path)],output:Path,ra:Double,dec:Double,radius:Double,subtraction:String):Task[SpectrumResult]=
    val observations=Json.Arr(Chunk.fromIterable(inputs.map((id,path)=>Json.Obj("frame_id"->Json.Str(id),"image_path"->Json.Str(path.toAbsolutePath.normalize.toString)))))
    request("spectrum_preview",output=Some(output),extra=List("observations"->observations,"ra_deg"->Json.Num(ra),
      "dec_deg"->Json.Num(dec),"radius_pix"->Json.Num(radius),"subtraction"->Json.Str(subtraction))).flatMap { response=>
      ZIO.attemptBlocking {
        if !string(response,"operation").contains("spectrum_preview") ||
          !string(response,"output_path").contains(output.toAbsolutePath.normalize.toString) ||
          !Files.isRegularFile(output,java.nio.file.LinkOption.NOFOLLOW_LINKS) || Files.size(output)>1048576 then
          throw ApiError("processing_protocol","The worker did not produce a bounded spectrum result")
        val value=Files.readString(output).fromJson[SpectrumResult].fold(_=>throw ApiError("processing_protocol","Invalid spectrum result"),identity)
        val ids=inputs.map(_._1).toSet
        val valid=value.spectrum.nonEmpty && value.spectrum.size<=inputs.size && value.total_channels==value.spectrum.size &&
          value.quality=="experimental_visualization_photometry" && !value.scientifically_calibrated && value.molecular_detections.isEmpty &&
          value.ra==ra && value.dec==dec && value.subtraction_mode==subtraction && value.aperture_radius_pix==radius &&
          value.spectrum.zipWithIndex.forall { (p,i)=>
            ids.contains(p.frame_id) && p.channel==i+1 && p.detector_array>=1 && p.detector_array<=6 &&
            p.detector==s"D${p.detector_array}" && !p.flagged &&
            List(p.flux_mjy,p.uncertainty_mjy,p.wavelength_um,p.bandwidth_um,p.snr,p.mjd).forall(_.isFinite) &&
            p.uncertainty_mjy>0 && p.wavelength_um>0 && p.bandwidth_um>0
          }
        if !valid then throw ApiError("processing_protocol","Spectrum measurements failed output validation")
        value
      }
    }

object HttpProcessingClient:
  def make(url:String,concurrency:Int=2,timeout:Duration=135.seconds):Task[HttpProcessingClient]=
    for
      uri<-ZIO.attempt {
        val u=URI.create(url)
        if !Set("http","https").contains(u.getScheme) || u.getHost==null || u.getUserInfo!=null ||
          u.getQuery!=null || u.getFragment!=null || !Set("","/").contains(Option(u.getPath).getOrElse("")) ||
          concurrency<1 || concurrency>4 || timeout<=Duration.Zero then
          throw ApiError("invalid_configuration","Invalid PROCESSING_URL, concurrency or timeout")
        u
      }
      slots<-Semaphore.make(concurrency)
      client<-ZIO.attempt(HttpClient.newBuilder().connectTimeout(java.time.Duration.ofSeconds(5)).followRedirects(HttpClient.Redirect.NEVER).build())
    yield new HttpProcessingClient(uri,client,slots,timeout)
