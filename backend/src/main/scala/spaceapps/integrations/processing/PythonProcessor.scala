package spaceapps.integrations.processing

import spaceapps.domain.{ApiError,Query}
import spaceapps.service.Processor
import zio.*
import zio.json.*
import zio.json.ast.Json
import java.io.InputStream
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Path}
import java.util.concurrent.TimeUnit
import scala.jdk.CollectionConverters.*

/** Runs only the bounded offline worker against server-owned native/cache paths. */
final class PythonProcessor private(python:String,worker:Path,pipeline:Path,slots:Semaphore,deadline:Duration) extends Processor:
  override val supportedModes=Set("zodi_reference_subtracted")
  private def property(value:Json,key:String):Option[Json]=value.asObject.flatMap(_.get(key))
  private def string(value:Json,key:String):Option[String]=property(value,key).flatMap(_.asString)
  private def bounded(input:InputStream):Task[String]=ZIO.attemptBlockingInterrupt {
    try
      val bytes=input.readNBytes(65537)
      if bytes.length>65536 then throw ApiError("processing_protocol","Python output exceeded its diagnostic limit")
      new String(bytes,UTF_8)
    finally input.close()
  }
  private def stop(process:Process):UIO[Unit]=ZIO.attemptBlocking {
    val children=process.descendants()
    try children.iterator().asScala.foreach(_.destroyForcibly()) finally children.close()
    process.destroy()
    if !process.waitFor(2,TimeUnit.SECONDS) then
      process.destroyForcibly()
      process.waitFor(2,TimeUnit.SECONDS)
    ()
  }.ignore
  private def request(operation:String,image:Option[Path]=None,output:Option[Path]=None):Task[Json]=slots.withPermit {
    val body=Json.Obj(Chunk.fromIterable(List("operation"->Json.Str(operation)) ++
      image.map(p=>"image_path"->Json.Str(p.toAbsolutePath.normalize().toString)) ++
      output.map(p=>"output_path"->Json.Str(p.toAbsolutePath.normalize().toString)))).toJson
    ZIO.scoped {
      ZIO.acquireRelease(ZIO.attemptBlocking {
        val builder=new ProcessBuilder(python,worker.toString)
        val environment=builder.environment()
        val previous=Option(environment.get("PYTHONPATH")).filter(_.nonEmpty)
        environment.put("PYTHONPATH",pipeline.toString+previous.fold("")(java.io.File.pathSeparator+_))
        environment.put("PYTHONUNBUFFERED","1")
        environment.put("PYTHONDONTWRITEBYTECODE","1")
        environment.put("OMP_NUM_THREADS","1")
        environment.put("OPENBLAS_NUM_THREADS","1")
        builder.start()
      })(stop).flatMap { process=>
        (for
          stdout <- bounded(process.getInputStream).forkScoped
          stderr <- bounded(process.getErrorStream).forkScoped
          _ <- ZIO.attemptBlockingInterrupt {
            val input=process.getOutputStream
            try { input.write(body.getBytes(UTF_8));input.flush() } finally input.close()
          }
          exit <- ZIO.attemptBlockingInterrupt(process.waitFor())
          result <- stdout.join
          diagnostics <- stderr.join
          document <- ZIO.fromEither(result.fromJson[Json]).mapError(_=>ApiError("processing_protocol","Python returned an invalid processing result"))
          _ <- if exit==0 && string(document,"status").contains("ok") then ZIO.unit else
            val error=property(document,"error").getOrElse(Json.Obj())
            val code=string(error,"code").getOrElse("failed")
            ZIO.logWarning(s"Python $operation failed: $code; ${diagnostics.take(4096)}") *>
              ZIO.fail(ApiError("processing_"+code,"Scientific image processing could not complete"))
        yield document).ensuring(stop(process))
      }
    }.timeoutFail(ApiError("processing_timeout","Scientific image processing timed out",true))(deadline)
      .mapError {
        case error:ApiError=>error
        case _=>ApiError("processing_unavailable","The scientific processing worker could not run",true)
      }
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
  private[processing] def ready:Task[Unit]=request("capabilities").flatMap { document=>
    val operations=property(document,"operations").flatMap(_.asArray).toList.flatten.flatMap(_.asString).toSet
    ZIO.fail(ApiError("processing_unavailable","The worker does not advertise verified preview and ZODI processing"))
      .unless(Set("preview","zodi").subsetOf(operations)).unit
  }

object PythonProcessor:
  def make(python:String,worker:Path,pipeline:Path,concurrency:Int=2,timeout:Duration=120.seconds):Task[PythonProcessor]=
    for
      _ <- ZIO.fail(ApiError("invalid_configuration","Processing concurrency must be1 to4 and timeout must be positive"))
        .when(concurrency<1 || concurrency>4 || timeout<=Duration.Zero)
      workerPath=worker.toAbsolutePath.normalize()
      pipelinePath=pipeline.toAbsolutePath.normalize()
      _ <- ZIO.fail(ApiError("processing_unavailable","Scientific worker or team cleaning module is missing"))
        .unless(Files.isRegularFile(workerPath) && Files.isRegularFile(pipelinePath.resolve("spherex/cleaning.py")))
      slots <- Semaphore.make(concurrency.toLong)
      processor=new PythonProcessor(python,workerPath,pipelinePath,slots,timeout)
      _ <- processor.ready
    yield processor
