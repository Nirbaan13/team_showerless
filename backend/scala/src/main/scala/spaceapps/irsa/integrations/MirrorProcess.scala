package spaceapps.irsa.integrations

import spaceapps.irsa.model.ApiError
import zio.*
import zio.json.*
import zio.json.ast.Json
import java.nio.file.{Files,Path}
import java.nio.charset.StandardCharsets.UTF_8

/** A bounded subprocess protocol; pixel data never crosses stdout. */
final class MirrorProcess(python:String,script:Path,database:Path,root:String,releases:String):
  private val outputLimit=8L*1024*1024
  def run(arguments:List[String],input:Option[String]=None):Task[Json]=ZIO.scoped {
    for
      output<-ZIO.acquireRelease(ZIO.attemptBlocking(Files.createTempFile("irsa-mirror-",".json")))(p=>ZIO.attemptBlocking(Files.deleteIfExists(p)).ignore)
      process<-ZIO.acquireRelease(ZIO.attemptBlocking {
        val args=List(python,script.toAbsolutePath.toString,"--db",database.toAbsolutePath.toString,"--root",root,"--releases",releases)++arguments
        new ProcessBuilder(args*).redirectOutput(output.toFile).redirectError(ProcessBuilder.Redirect.DISCARD).start()
      })(p=>ZIO.attemptBlocking {if p.isAlive then p.destroyForcibly();p.waitFor(5,java.util.concurrent.TimeUnit.SECONDS);()}.ignore)
      _<-ZIO.attemptBlocking {
        val stream=process.getOutputStream
        try input.foreach(value=>stream.write(value.getBytes(UTF_8))) finally stream.close()
      }
      _<-(ZIO.attemptBlocking {
        if Files.size(output)>outputLimit then throw ApiError("archive_mirror_size_limit","Mirror metadata exceeds the 8 MiB limit")
        process.isAlive
      }.flatMap(running=>if running then ZIO.sleep(50.millis).as(true) else ZIO.succeed(false))).repeatUntil(!_)
      bytes<-ZIO.attemptBlocking {
        if Files.size(output)>outputLimit then throw ApiError("archive_mirror_size_limit","Mirror metadata exceeds the 8 MiB limit")
        Files.readString(output)
      }
      json<-ZIO.fromEither(bytes.fromJson[Json]).mapError(_=>ApiError("archive_mirror_invalid_response","Mirror index returned invalid metadata"))
      result<-json match
        case Json.Obj(fields) if fields.exists(_._1=="error")=>
          val error=fields.toMap.apply("error") match
            case Json.Obj(es)=>es.toMap
            case _=>Map.empty[String,Json]
          def string(key:String,default:String)=error.get(key).collect{case Json.Str(s)=>s}.getOrElse(default)
          ZIO.fail(ApiError(string("code","archive_mirror_unavailable"),string("message","Mirror index is unavailable"),true))
        case value if process.exitValue()==0=>ZIO.succeed(value)
        case _=>ZIO.fail(ApiError("archive_mirror_unavailable","Mirror index process failed",true))
    yield result
  }.timeoutFail(ApiError("archive_mirror_timeout","Mirror index operation timed out",true))(10.minutes)
