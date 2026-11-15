package spaceapps.irsa.integrations

import spaceapps.irsa.model.*
import spaceapps.irsa.service.Archive
import spaceapps.infra.integrations.fits.FitsHeaders
import zio.*
import zio.json.*
import zio.json.ast.Json
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Path}

/** Reads native pixel subsets from S3 without depending on IRSA's cutout server. */
final class MirrorTransfer(primary:Archive,python:String,script:Path,maxBytes:Long=67108864L) extends Archive:
  def search(query:Query):Task[List[ArchiveImage]]=primary.search(query)
  def fetch(image:ArchiveImage,destination:Path):Task[Unit]=image.sourceUrl match
    case None=>primary.fetch(image,destination)
    case Some(source)=>fetchSubset(source,image.accessUrl,destination)
  def fetchSubset(source:String,selection:String,destination:Path):Task[Unit]=
    ZIO.scoped {
      for
        output<-ZIO.acquireRelease(ZIO.attemptBlocking(Files.createTempFile("irsa-cutout-",".json")))(p=>ZIO.attemptBlocking(Files.deleteIfExists(p)).ignore)
        process<-ZIO.acquireRelease(ZIO.attemptBlocking {
          new ProcessBuilder(python,script.toAbsolutePath.toString,"--source",source,"--cutout",selection,"--output",destination.toAbsolutePath.toString,"--max-bytes",maxBytes.toString)
            .redirectOutput(output.toFile).redirectError(ProcessBuilder.Redirect.DISCARD).start()
        })(p=>ZIO.attemptBlocking {if p.isAlive then p.destroyForcibly();p.waitFor(5,java.util.concurrent.TimeUnit.SECONDS);()}.ignore)
        _<-ZIO.attemptBlocking(process.getOutputStream.close())
        _<-(ZIO.attemptBlocking {
          if Files.size(output)>65536 then throw ApiError("archive_mirror_size_limit","Cutout helper response exceeds 64 KiB")
          if Files.exists(destination) && Files.size(destination)>maxBytes then throw ApiError("archive_size_limit","Mirror subset exceeds the product byte limit")
          process.isAlive
        }.flatMap(running=>if running then ZIO.sleep(50.millis).as(true) else ZIO.succeed(false))).repeatUntil(!_)
        body<-ZIO.attemptBlocking {
          if Files.size(output)>65536 then throw ApiError("archive_mirror_size_limit","Cutout helper response exceeds 64 KiB")
          Files.readString(output)
        }
        json<-ZIO.fromEither(body.fromJson[Json]).mapError(_=>ApiError("archive_mirror_invalid_response","Cutout helper returned invalid JSON"))
        _<-json match
          case Json.Obj(fields) if fields.exists(_._1=="error")=>
            val error=fields.toMap.apply("error").asObject
            def text(key:String,default:String)=error.flatMap(_.get(key)).collect{case Json.Str(value)=>value}.getOrElse(default)
            val code=text("code","archive_mirror_transfer_failed")
            ZIO.fail(ApiError(code,text("message","Mirror subset could not be retrieved"),
              Set("archive_cutout_transport","archive_cutout_identity","archive_mirror_timeout","archive_mirror_object_changed").contains(code)))
          case Json.Obj(fields) if process.exitValue()==0 && fields.toMap.get("ok").contains(Json.Bool(true))=>ZIO.unit
          case _=>ZIO.fail(ApiError("archive_mirror_transfer_failed","Mirror subset helper failed"))
        _<-ZIO.attemptBlocking {
          val size=Files.size(destination)
          val stream=Files.newInputStream(destination)
          val signature=try new String(stream.readNBytes(30),UTF_8) finally stream.close()
          if size<2880 || size>maxBytes || size%2880!=0 || !signature.startsWith("SIMPLE  =") || signature.drop(10).trim!="T" then
            throw ApiError("archive_invalid_fits","Mirror subset is not a complete bounded FITS product")
        }
        _<-FitsHeaders.read(destination).mapError(_=>ApiError("archive_invalid_fits","Mirror subset has invalid or truncated FITS structure"))
      yield ()
    }.timeoutFail(ApiError("archive_mirror_timeout","Mirror pixel subset exceeded the transfer deadline",true))(2.minutes)
      .onExit(exit=>if exit.isSuccess then ZIO.unit else ZIO.attemptBlocking(Files.deleteIfExists(destination)).ignore)
      .ensuring(ZIO.attemptBlocking(Files.deleteIfExists(Path.of(destination.toString+".mirror-part"))).ignore)
