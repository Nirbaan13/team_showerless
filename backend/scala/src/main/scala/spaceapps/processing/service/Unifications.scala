package spaceapps.processing.service

import spaceapps.processing.service.model.*
import spaceapps.processing.service.core.BundleValidation
import spaceapps.processing.repository.UnificationRepository
import spaceapps.infra.model.ApiError
import spaceapps.downloads.model.{ArchiveFailure,AssetResource}
import spaceapps.downloads.repository.DownloadsRepository
import spaceapps.downloads.service.DownloadsService
import spaceapps.infra.service.FileCache
import spaceapps.irsa.service.{Jobs,Resource}
import zio.*
import zio.json.*
import zio.json.ast.Json
import java.nio.file.{Files,Path,LinkOption,StandardCopyOption}
import java.security.MessageDigest
import java.util.UUID
import scala.jdk.CollectionConverters.*

final class Unifications private(jobs:Jobs,archive:DownloadsService,archives:DownloadsRepository,cache:FileCache,
  data:Path,repository:UnificationRepository,invoke:Json=>Task[Json]):
  import Unifications.*
  private def directory(id:String)=data.resolve("unifications").resolve(id)
  private def target(id:String)=directory(id).resolve("dataset.npz")
  private def resolve(input:UnificationInput):ZIO[Scope,Throwable,Source]=
    if input.kind=="archive_asset" then
      for
        resource <- archive.resource(input.id).mapError(e=>ApiError(e.code,e.message,e.retryable))
        located <- resource match
          case AssetResource.Ready(path,stored)=>ZIO.succeed(path->stored)
          case AssetResource.Failed(error)=>ZIO.fail(ApiError(error.code,error.message,error.retryable))
          case AssetResource.Pending=>ZIO.fail(ApiError("invalid_input","Archive asset is not complete and available"))
        (path,stored)=located
        downloads <- archives.allDownloads
        outcome <- ZIO.fromOption(downloads.flatMap(_.assets).find(a=>a.status=="ready" && a.asset.exists(_.id==input.id))).orElseFail(ApiError("not_found","Completed archive asset metadata not found"))
        record <- archives.record(outcome.record_id)
        profile=if record.provider=="irsa-spherex" then "spherex" else "generic"
        physical=physicalIdentity(record.provider,record.collection,record.native)
        metadata=Json.Obj("provider"->Json.Str(record.provider),"observation_id"->physical.fold[Json](Json.Null)(Json.Str(_)),"product_id"->Json.Str(record.native_id),
          "collection"->Json.Str(record.collection),"mission"->record.mission.fold[Json](Json.Null)(Json.Str(_)),
          "instrument"->record.instrument.fold[Json](Json.Null)(Json.Str(_)),"brightness_unit"->record.brightness_unit.fold[Json](Json.Null)(Json.Str(_)),
          "wavelength_min_m"->record.wavelength_min_m.fold[Json](Json.Null)(n=>Json.Num(n)),"wavelength_max_m"->record.wavelength_max_m.fold[Json](Json.Null)(n=>Json.Num(n)),
          "analysisEligible"->Json.Bool(record.analysisEligible),
          "time_start_utc"->record.time.start_utc.fold[Json](Json.Null)(Json.Str(_)),"time_end_utc"->record.time.end_utc.fold[Json](Json.Null)(Json.Str(_)),
          "time_quality"->Json.Str(record.time.quality.toString),"band"->record.native.get("FILTER").orElse(record.native.get("filter")).fold[Json](Json.Null)(Json.Str(_)),
          "native"->Json.Obj(zio.Chunk.fromIterable(record.native.toList.filter((k,v)=> !k.toLowerCase.contains("url") && !v.contains("://") && k.length<=80 && v.length<=512).sortBy(_._1).take(12).map((k,v)=>k->Json.Str(v)))))
        source <- inspect(input,path,Some(stored.sha256),Some(stored.bytes),profile,metadata)
      yield source
    else
      for
        download <- jobs.get(input.downloadId.get)
        _ <- ZIO.fail(ApiError("invalid_input","Select a completed native download in default mode")).unless(download.mode=="default" && Set("completed","completed_with_errors")(download.status))
        chunk <- ZIO.fromOption(download.chunks.find(_.id==input.id)).orElseFail(ApiError("not_found","Chunk does not belong to the selected download"))
        observation <- ZIO.fromOption(download.observations.find(_.frame_id==chunk.frame_id)).orElseFail(ApiError("not_found","Native observation metadata not found"))
        resource <- jobs.leasedResource(input.id,false)
        path <- resource match
          case Resource.Ready(p)=>ZIO.succeed(p)
          case Resource.Failed(error)=>ZIO.fail(error)
          case _=>ZIO.fail(ApiError("invalid_input","Native chunk is not complete and available"))
        physical=physicalIdentity("irsa-spherex","",observation.header_metadata.collect {case (key,Json.Str(value))=>key->value}.updated("detector_array",observation.detector_array.toString))
        metadata=Json.Obj("provider"->Json.Str("irsa-spherex"),"observation_id"->physical.fold[Json](Json.Null)(Json.Str(_)),"product_id"->Json.Str(observation.frame_id),"release"->Json.Str(observation.release),
          "detector_array"->Json.Num(observation.detector_array),"channel_index"->observation.channel_index.fold[Json](Json.Null)(n=>Json.Num(n)),
          "wavelength_min_m"->observation.wavelength_min_um.fold[Json](Json.Null)(n=>Json.Num(n*1e-6)),"wavelength_max_m"->observation.wavelength_max_um.fold[Json](Json.Null)(n=>Json.Num(n*1e-6)))
        source <- inspect(input,path,None,None,"spherex",metadata)
      yield source
  private def inspect(input:UnificationInput,path:Path,expected:Option[String],bytes:Option[Long],profile:String,metadata:Json):Task[Source]=ZIO.attemptBlocking {
    secureFile(data,path)
    val size=Files.size(path)
    if size<=0 || size>MaxInput || bytes.exists(_!=size) then throw ApiError("invalid_input","Source size is invalid or changed")
    val hash=checksum(path)
    if expected.exists(_!=hash) then throw ApiError("source_changed","Source checksum differs from its persisted archive metadata")
    Source(input,path,size,hash,profile,metadata)
  }
  def submit(json:Json):Task[UnificationJob]=for
    request <- ZIO.fromEither(UnificationRequest.parse(json))
    _ <- ZIO.scoped(ZIO.foreach(request.inputs)(resolve).flatMap(s=>ZIO.fail(ApiError("input_limit","Selected input bytes exceed 256 MiB")).when(s.map(_.bytes).sum>MaxInput)))
    accepted <- repository.accept(json)
  yield accepted
  def get(id:String):Task[UnificationJob]=
    validId(id) *> repository.get(id).flatMap { job=>
      if job.status!="completed" then ZIO.succeed(job)
      else ZIO.attemptBlocking(Files.isRegularFile(target(id),LinkOption.NOFOLLOW_LINKS)).map { exists=>
        if exists then job else job.copy(artifact_url=None,error=Some(ApiError("artifact_unavailable","Unified artifact has been evicted or is unavailable",true)))
      }
    }
  /** Caller scope includes response streaming, so eviction cannot remove this artifact mid-read. */
  def artifact(id:String):ZIO[Scope,Throwable,Path]=for
    _ <- validId(id)
    job <- repository.get(id)
    _ <- ZIO.fail(ApiError("artifact_unavailable","Unified artifact is not completed and available",true)).unless(job.status=="completed" && job.artifact_url.isDefined)
    path=target(id)
    _ <- cache.protect(path)
    _ <- ZIO.attemptBlocking(secureFile(data,path)).mapError(_=>ApiError("artifact_unavailable","Unified artifact has been evicted or is unavailable",true))
    found <- cache.cached(path)
    _ <- ZIO.fail(ApiError("artifact_unavailable","Unified artifact has been evicted or is unavailable",true)).when(found.isEmpty)
  yield path
  private def snapshots(id:String,sources:List[Source]):Task[List[Json]]=ZIO.attemptBlocking {
    val inputs=directory(id).resolve("inputs")
    safeDirectory(data,inputs)
    sources.zipWithIndex.map { (source,index)=>
      secureFile(data,source.path)
      val destination=inputs.resolve(f"$index%03d.fits")
      // Hardlinks retain the selected inode across same-ID atomic source replacement.
      try Files.createLink(destination,source.path)
      catch case _:UnsupportedOperationException | _:java.nio.file.FileSystemException=>
        val in=Files.newInputStream(source.path,LinkOption.NOFOLLOW_LINKS)
        val out=Files.newOutputStream(destination,java.nio.file.StandardOpenOption.CREATE_NEW)
        try
          val buffer=new Array[Byte](65536);var total=0L;var n=in.read(buffer)
          while n>=0 do
            total+=n
            if total>source.bytes || total>MaxInput then throw ApiError("source_changed","Source changed while taking snapshot")
            out.write(buffer,0,n);n=in.read(buffer)
        finally {in.close();out.close()}
      secureFile(data,destination)
      if Files.size(destination)!=source.bytes || checksum(destination)!=source.sha then throw ApiError("source_changed","Source changed while taking snapshot")
      Json.Obj("id"->Json.Str(source.input.id),"path"->Json.Str(data.relativize(destination).toString),"sha256"->Json.Str(source.sha),
        "profile"->Json.Str(source.profile),"image_hdu"->source.input.imageHdu,"plane_indices"->source.input.planeIndices,"metadata"->source.metadata)
    }
  }
  private def validateOutput(id:String,request:UnificationRequest,sources:List[Source],result:Json):Task[Path]=ZIO.attemptBlocking {
    def invalid():Nothing=throw ApiError("invalid_output","Pipeline returned an invalid unified artifact")
    def fields(j:Json):Map[String,Json]=j match
      case Json.Obj(values) if values.map(_._1).distinct.size==values.size=>values.toMap
      case _=>invalid()
    def number(j:Json):Long=j match
      case Json.Num(n)=>scala.util.Try(n.longValueExact()).getOrElse(invalid())
      case _=>invalid()
    def string(j:Json):String=j match
      case Json.Str(s)=>s
      case _=>invalid()
    val root=fields(result)
    if root.get("schema_version")!=Some(Json.Num(1)) || root.get("job_id")!=Some(Json.Str(id)) || root.get("status")!=Some(Json.Str("completed")) ||
      root.get("frame_count")!=Some(Json.Num(request.inputs.size)) || root.get("width")!=Some(Json.Num(request.width)) || root.get("height")!=Some(Json.Num(request.height)) then invalid()
    if !root.get("detection_ready").exists(_.isInstanceOf[Json.Bool]) then invalid()
    root.get("warnings") match
      case Some(Json.Arr(xs)) if xs.size<=100 && xs.forall {case Json.Str(s)=>s.length<=4096;case _=>false}=>()
      case _=>invalid()
    def descriptor(key:String,max:Long):Path=
      val d=fields(root.getOrElse(key,Json.Null))
      if d.keySet!=Set("path","bytes","sha256") then invalid()
      val expected=s"unifications/$id/output/${if key=="bundle" then "dataset.npz" else "manifest.json"}"
      if string(d("path"))!=expected then invalid()
      val p=data.resolve(expected)
      secureFile(data,p)
      val size=number(d("bytes"));val hash=string(d("sha256"))
      if size<=0 || size>max || Files.size(p)!=size || !hash.matches("[0-9a-f]{64}") || checksum(p)!=hash then invalid()
      p
    val bundle=descriptor("bundle",MaxBundle)
    val manifest=descriptor("manifest",1024*1024)
    val metadata=fields(Files.readString(manifest).fromJson[Json].fold(_=>invalid(),identity))
    if metadata.get("schema_version")!=Some(Json.Num(1)) || metadata.get("job_id")!=Some(Json.Str(id)) then invalid()
    if metadata.get("grid")!=Some(request.grid) then invalid()
    val frames=metadata.get("frames") match
      case Some(Json.Arr(values)) if values.size==request.inputs.size=>values.toList
      case _=>invalid()
    val expected=sources.map(s=>s.input.id->s).toMap
    val ids=frames.map(f=>string(fields(f).getOrElse("frame_id",Json.Null)))
    if ids.distinct.size!=ids.size || ids.toSet!=expected.keySet then invalid()
    frames.foreach { frame=>
      val f=fields(frame);val source=expected(string(f("frame_id")))
      if f.get("source_sha256")!=Some(Json.Str(source.sha)) || f.get("profile")!=Some(Json.Str(source.profile)) ||
        f.get("provenance")!=Some(source.metadata) || f.get("analysis_eligible")!=Some(Json.Bool(false)) then invalid()
    }
    if metadata.get("options")!=Some(request.options) then invalid()
    BundleValidation.validate(bundle,request.inputs.size,request.height,request.width,Some(Files.readString(manifest)))
    bundle
  }.mapError {case e:ApiError if e.code=="invalid_output"=>e;case _=>ApiError("invalid_output","Pipeline returned an invalid unified artifact")}
  private def clean(id:String,finalOutput:Boolean=false):Task[Unit]=ZIO.attemptBlocking {
    List(directory(id).resolve("inputs"),directory(id).resolve("output")).foreach(removeTree)
    Files.deleteIfExists(directory(id).resolve("request.json"))
    if finalOutput then Files.deleteIfExists(target(id))
  }
  private def run(record:UnificationRecord):Task[Unit]=
    val id=record.job.id
    val work=ZIO.scoped {for
      request <- ZIO.fromEither(UnificationRequest.parse(record.request))
      sources <- ZIO.foreach(request.inputs)(resolve)
      bytes=sources.map(_.bytes).sum
      _ <- ZIO.fail(ApiError("input_limit","Selected input bytes exceed 256 MiB")).when(bytes>MaxInput)
      _ <- cache.protect(target(id))
      _ <- cache.withReservation(directory(id),bytes+MaxBundle+2*1024*1024) {
        for
          inputs <- snapshots(id,sources)
          payload=Json.Obj("schema_version"->Json.Num(1),"job_id"->Json.Str(id),"inputs"->Json.Arr(zio.Chunk.fromIterable(inputs)),"grid"->request.grid,"options"->request.options)
          // Transport bounds the call; retaining scope through completion retains immutable inputs.
          result <- invoke(payload).uninterruptible
          bundle <- validateOutput(id,request,sources,result)
          _ <- cache.adopt(target(id),bundle)
          _ <- clean(id)
          _ <- repository.update(record.job.copy(status="completed",artifact_url=Some(s"/api/image-unifications/$id/artifact")))
        yield ()
      }
    yield ()}
    work.catchAll { error=>
      val safe=error match
        case e:ApiError=>e
        case e:ArchiveFailure=>ApiError(e.code,e.message,e.retryable)
        case _=>ApiError("processing_failed","Image unification failed",true)
      clean(id,true).ignore *> repository.update(record.job.copy(status="failed",artifact_url=None,error=Some(safe)))
    }.onInterrupt(clean(id,true).ignore *> repository.update(record.job.copy(status="failed",error=Some(ApiError("interrupted","Image unification was interrupted; submit again",true)))).ignore).ensuring(clean(id).ignore)
  private[processing] val worker:UIO[Unit]=(repository.claim.flatMap {
    case Some(record)=>run(record)
    case None=>ZIO.sleep(100.millis)
  }.catchAll(e=>ZIO.logWarning("Unification worker could not access durable state") *> ZIO.sleep(250.millis))).forever

object Unifications:
  private val MaxInput=256L*1024*1024
  private val MaxBundle=192L*1024*1024
  private final case class Source(input:UnificationInput,path:Path,bytes:Long,sha:String,profile:String,metadata:Json)
  /** Product/reduction identifiers are provenance, never evidence of a distinct exposure. */
  private[processing] def physicalIdentity(provider:String,collection:String,native:Map[String,String]):Option[String]=
    val fields=native.map((key,value)=>key.toUpperCase(java.util.Locale.ROOT)->value.trim)
    val identity=provider match
      case "eso" | "cadc"=>fields.get("OBS_ID").filter(_.nonEmpty).map(id=>Json.Arr(Json.Str(collection),Json.Str(id)).toJson)
      case "irsa-spherex"=>
        for
          id <- fields.get("OBSID").orElse(fields.get("OBS_ID")).filter(_.nonEmpty)
          detector <- fields.get("DETECTOR_ARRAY").flatMap(_.toIntOption).filter(n=>n>=1 && n<=6)
        yield s"$id:D$detector"
      case _=>None
    identity.filter(_.length<=512)
  private def validId(id:String):Task[Unit]=ZIO.fail(ApiError("not_found","Image unification job not found")).unless(id.matches("[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")).unit
  private def checksum(path:Path):String=
    val digest=MessageDigest.getInstance("SHA-256");val in=Files.newInputStream(path,LinkOption.NOFOLLOW_LINKS)
    try
      val buffer=new Array[Byte](65536);var n=in.read(buffer)
      var total=0L
      while n>=0 do
        total+=n
        if total>MaxInput then throw ApiError("input_limit","Managed file exceeds byte budget")
        digest.update(buffer,0,n);n=in.read(buffer)
    finally in.close()
    digest.digest().map(b=>f"${b & 255}%02x").mkString
  private def noSymlinks(root:Path,path:Path):Unit=
    val absolute=path.toAbsolutePath.normalize()
    if !absolute.startsWith(root) || absolute==root then throw ApiError("invalid_input","Source path is outside managed storage")
    var current=root
    if Files.isSymbolicLink(root) then throw ApiError("invalid_input","Symlinks are not supported")
    root.relativize(absolute).iterator().asScala.foreach { part=>current=current.resolve(part);if Files.isSymbolicLink(current) then throw ApiError("invalid_input","Symlinks are not supported") }
  private def secureFile(root:Path,path:Path):Unit=
    noSymlinks(root,path)
    if !Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS) then throw ApiError("invalid_input","Source file is unavailable")
  private def safeDirectory(root:Path,path:Path):Unit=
    noSymlinks(root,path);Files.createDirectories(path);noSymlinks(root,path)
  private def removeTree(path:Path):Unit=
    if Files.exists(path,LinkOption.NOFOLLOW_LINKS) then
      val stream=Files.walk(path)
      try stream.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally stream.close()
  def make(jobs:Jobs,archiveService:DownloadsService,archiveRepository:DownloadsRepository,cache:FileCache,data:Path,database:Path,invoke:Json=>Task[Json]):ZIO[Scope,Throwable,Unifications]=for
    repository <- UnificationRepository.open(database)
    interrupted <- repository.recover
    root=data.toAbsolutePath.normalize()
    _ <- ZIO.attemptBlocking {
      safeDirectory(root,root.resolve("unifications"))
      val dirs=Files.list(root.resolve("unifications"))
      try dirs.iterator().asScala.filter(p=>p.getFileName.toString.matches("[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}") && !Files.isSymbolicLink(p)).foreach { dir=>
        removeTree(dir.resolve("inputs"));removeTree(dir.resolve("output"));Files.deleteIfExists(dir.resolve("request.json"))
        if interrupted.contains(dir.getFileName.toString) then Files.deleteIfExists(dir.resolve("dataset.npz"))
        val children=Files.list(dir)
        try children.iterator().asScala.filter(p=>p.getFileName.toString.matches("dataset[.]npz[.][0-9a-f-]{36}[.]part")).foreach(Files.deleteIfExists(_)) finally children.close()
      } finally dirs.close()
    }
    service=new Unifications(jobs,archiveService,archiveRepository,cache,root,repository,invoke)
    _ <- service.worker.forkScoped
  yield service
