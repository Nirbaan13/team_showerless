package spaceapps.service

import spaceapps.domain.*
import spaceapps.repository.AnalysisRepository
import zio.{Chunk as _,*}
import zio.json.*
import zio.json.ast.Json
import zio.stream.*
import java.nio.file.{Files,Path,LinkOption,NoSuchFileException,StandardCopyOption}
import java.nio.file.attribute.BasicFileAttributes
import java.util.concurrent.TimeUnit
import scala.jdk.CollectionConverters.*

final case class AnalysisConfig(root:Path,python:String="python3",wallTime:Duration=900.seconds,maxJobs:Int=8,
  maxOutputBytes:Long=64L*1024*1024,maxResultBytes:Long=4L*1024*1024)

final class Analyses private(repo:AnalysisRepository,jobs:Jobs,data:Path,config:AnalysisConfig):
  private val root=config.root.toAbsolutePath.normalize()
  private val storage=data.toAbsolutePath.normalize().resolve("analyses")
  private def folder(id:String)=storage.resolve(id)
  private def fail(code:String,message:String,retryable:Boolean=false)=ApiError(code,message,retryable)
  private def objectFields(j:Json):Map[String,Json]=j match
    case Json.Obj(fs) if fs.map(_._1).distinct.size==fs.size=>fs.toMap
    case _=>throw fail("invalid_analysis_output","Inference output contains an invalid object")
  private def readJson(path:Path,limit:Long):Task[Json]=ZIO.attemptBlocking {
    if !Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS) || Files.size(path)>limit then throw fail("invalid_analysis_output","Inference JSON output is missing or oversized")
    Files.readString(path).fromJson[Json].fold(_=>throw fail("invalid_analysis_output","Inference output is not valid finite JSON"),identity)
  }
  def models:Task[Json]=readJson(root.resolve("models/metadata.json"),65536).map { m=>
    val f=objectFields(m)
    val publicFields=Set("schema_version","model_id","sha256","feature_names","score_kind","class_labels","positive_class","limitations","status","score_description","training_manifest_sha256","model_family","detector_profile","algorithm_version_proposal")
    Json.Obj("models"->Json.Arr(Json.Obj(zio.Chunk.fromIterable(f.filter((k,_)=>publicFields.contains(k))))))
  }
  def presetList:Task[List[AnalysisPreset]]=
    if Files.isRegularFile(root.resolve("fixtures/presets.json")) then readJson(root.resolve("fixtures/presets.json"),65536).flatMap(j=>ZIO.fromEither(j.toJson.fromJson[List[AnalysisPreset]]).mapError(_=>fail("preset_unavailable","Installed preset metadata is invalid")))
    else ZIO.succeed(AnalysisPreset.all)
  def presets:Task[Json]=presetList.map(ps=>Json.Obj("presets"->Json.Arr(zio.Chunk.fromIterable(ps.map(p=>p.toJson.fromJson[Json].toOption.get)))))
  def submit(request:AnalysisRequest):Task[Analysis]=for
    validated<-ZIO.fromEither(request.validate)
    _<-ZIO.foreachDiscard(validated.download_id)(id=>jobs.get(id).flatMap { d=>
      requireNativeDownload(d) *> ZIO.fromEither(AnalysisRegion.fromQuery(Query(d.query,""),validated.options)) *>
        ZIO.fail(fail("analysis_too_large","Motion analysis supports at most 32 input frames")).when(d.chunks.size>32)
    })
    metadata<-readJson(root.resolve("models/metadata.json"),65536)
    hash<-ZIO.attempt(objectFields(metadata).get("sha256").collect{case Json.Str(s)=>s}.getOrElse(throw fail("model_unavailable","Installed model manifest is invalid")))
    modelId<-ZIO.attempt(objectFields(metadata).get("model_id").collect{case Json.Str(s) if s.nonEmpty && s.length<=128=>s}.getOrElse(throw fail("model_unavailable","Installed model identity is invalid")))
    _<-ZIO.foreachDiscard(validated.preset)(id=>ZIO.fail(fail("preset_unavailable","The registered real-data fixture is not installed",true)).unless(Files.isRegularFile(root.resolve(s"fixtures/$id.npz"))))
    inputIdentity<-ZIO.foreach(validated.preset) { id=>ZIO.attemptBlocking {
      val digest=java.security.MessageDigest.getInstance("SHA-256")
      val in=Files.newInputStream(root.resolve(s"fixtures/$id.npz"))
      val bytes=new Array[Byte](65536)
      try
        var n=in.read(bytes)
        while n>=0 do
          digest.update(bytes,0,n);n=in.read(bytes)
      finally in.close()
      digest.digest().map(b=>f"${b & 255}%02x").mkString
    }}
    a<-repo.accept(validated,Hash.sha256(s"motion-v2|$modelId|$hash|${inputIdentity.getOrElse(validated.download_id.getOrElse(""))}|${validated.toJson}"),config.maxJobs,Some(hash),Some(modelId))
  yield a
  def get(id:String):Task[Analysis]=repo.get(id)
  def events(id:String):Stream[Throwable,Event]=ZStream.unwrap {
    repo.snapshot(id).map { (a,cursor)=>
      val snapshot=ZStream.succeed(Event(cursor,if a.terminal then "analysis.completed" else "analysis.updated",a.toJson))
      if a.terminal then snapshot else snapshot ++ ZStream.unfoldChunkZIO(cursor) { c=>
        repo.events(id,c).flatMap(es=>if es.isEmpty then ZIO.sleep(100.millis).as(Some((zio.Chunk.empty[Event],c))) else ZIO.succeed(Some((zio.Chunk.fromIterable(es),es.last.sequence))))
      }.takeUntil(_.name=="analysis.completed")
    }
  }
  private def names(result:Json):Set[String]=objectFields(result).get("resources") match
    case Some(Json.Arr(rs))=>rs.map(r=>objectFields(r).get("name").collect{case Json.Str(s)=>s}.getOrElse("")).toSet
    case _=>Set.empty
  private def safeName(name:String)=name.matches("(?:(?:frame|difference|bloom)-[0-9]{3}|candidate-[0-9]{3}-(?:moving|stationary))[.]png")
  def resource(id:String,name:String):Task[Path]=for
    a<-repo.get(id)
    _<-ZIO.fail(fail("not_found","Analysis resource not found")).unless(safeName(name) && a.status=="completed" && a.result.exists(r=>names(r).contains(name)))
    path=folder(id).resolve("output").resolve(name)
    _<-ZIO.attemptBlocking {
      if !Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS) || !path.toRealPath().startsWith(storage.toRealPath()) then throw fail("not_found","Analysis resource not found")
    }
  yield path
  private def cleanupInputs(id:String):UIO[Unit]=removeTree(folder(id).resolve("inputs")).ignore
  private def removeTree(p:Path):Task[Unit]=ZIO.attemptBlocking {
    if Files.exists(p,LinkOption.NOFOLLOW_LINKS) then
      val stream=Files.walk(p)
      try stream.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally stream.close()
  }
  private def requireNativeDownload(download:Download):Task[Unit]=
    ZIO.fail(fail("unsupported_analysis_input","Motion analysis requires an unprocessed default download; processed FITS products are unsupported")).unless(download.mode=="default").unit
  private def sourceEvidence(download:Download,frameId:String):List[(String,Json)]=
    val observation=download.observations.find(_.frame_id==frameId).getOrElse(throw fail("invalid_input","Native frame metadata is missing"))
    val release=observation.release
    if !release.matches("[A-Za-z0-9._-]{1,64}") then throw fail("invalid_input","Native release metadata is invalid")
    val access=observation.header_metadata.get("access_url").collect { case Json.Str(s)=>
      val uri=try java.net.URI.create(s) catch case _:IllegalArgumentException=>throw fail("invalid_input","Native provenance URL is invalid")
      val host=Option(uri.getHost).getOrElse("")
      val local=Set("localhost","127.0.0.1","::1","[::1]").contains(host)
      if s.length>4096 || host.isEmpty || uri.getUserInfo!=null || uri.getFragment!=null || !(uri.getScheme=="https" || (uri.getScheme=="http" && local)) then
        throw fail("invalid_input","Native provenance URL is invalid")
      uri
    }
    val processing=access.flatMap(uri=>"(?:^|/)(l2b-v[0-9]{1,4}-[0-9]{4}-[0-9]{3})(?:/|$)".r.findFirstMatchIn(uri.getPath).map(_.group(1)))
    List("release"->Json.Str(release)) ++ access.map(u=>"access_url"->Json.Str(u.toString)) ++ processing.map(v=>"processing_version"->Json.Str(v))
  private def prepare(r:AnalysisRecord):Task[Option[Json]]=r.request.preset match
    case Some(id)=>ZIO.succeed(Some(Json.Obj("kind"->Json.Str("preset"),"preset_id"->Json.Str(id),"path"->Json.Str(root.resolve(s"fixtures/$id.npz").toString))))
    case None =>
      for
        d<-jobs.get(r.request.download_id.get)
        _<-requireNativeDownload(d)
        result<-if !d.terminal then (if r.analysis.status=="waiting_for_download" then ZIO.unit else repo.update(r.analysis.id)(_.copy(status="waiting_for_download")).unit).as(None)
          else if !Set("completed","completed_with_errors").contains(d.status) || d.chunks.exists(_.status!="ready") then ZIO.fail(fail("download_failed","The download did not publish every requested native frame; inspect the download errors",true))
          else if d.chunks.size<3 then ZIO.fail(fail("insufficient_frames","Motion analysis requires at least three independent frames"))
          else if d.chunks.size>32 then ZIO.fail(fail("analysis_too_large","Motion analysis supports at most 32 input frames"))
          else for
            region<-ZIO.fromEither(AnalysisRegion.fromQuery(Query(d.query,""),r.request.options))
            _<-repo.update(r.analysis.id)(_.copy(status="preparing"))
            input=folder(r.analysis.id).resolve("inputs")
            _<-ZIO.attemptBlocking(Files.createDirectories(input))
            frames<-ZIO.foreach(d.chunks.zipWithIndex) { (c,i)=>ZIO.scoped {
              // Pin the cache entry until this input owns an independent hardlink or copy.
              jobs.leasedResource(c.id,false).flatMap {
                case Resource.Ready(source)=>ZIO.attemptBlocking {
                  val real=source.toRealPath()
                  if !real.startsWith(data.toRealPath()) || Files.isSymbolicLink(source) then throw fail("invalid_input","Native input escaped managed storage")
                  val target=input.resolve(f"frame-$i%03d.fits")
                  Files.deleteIfExists(target)
                  try Files.createLink(target,real) catch case _:UnsupportedOperationException | _:java.nio.file.FileSystemException=>Files.copy(real,target)
                  Json.Obj(zio.Chunk.fromIterable(List("frame_id"->Json.Str(c.frame_id),"path"->Json.Str(target.toString)) ++ sourceEvidence(d,c.frame_id)))
                }
                case _=>ZIO.fail(fail("cache_missing","Native input disappeared before snapshot; submit download again",true))
              }
            } }
          yield Some(Json.Obj("kind"->Json.Str("fits"),"observations"->Json.Arr(zio.Chunk.fromIterable(frames)),"region"->region.toJson.fromJson[Json].toOption.get))
      yield result
  private def checkDisk(output:Path,allowTransientEntries:Boolean=false):Task[Unit]=ZIO.attemptBlocking {
    // Output is flat. Files.walk also reads attributes while traversing, before our error handling.
    val entries=Files.list(output)
    try
      var size=0L;var count=0
      entries.iterator().asScala.foreach { path=>
        val attributes=try Some(Files.readAttributes(path,classOf[BasicFileAttributes],LinkOption.NOFOLLOW_LINKS))
          catch case _:NoSuchFileException if allowTransientEntries=>None
        attributes.foreach { attrs=>
          if attrs.isSymbolicLink || !attrs.isRegularFile then throw fail("invalid_analysis_output","Inference produced an unexpected filesystem entry")
          count+=1;size+=attrs.size
          if count>298 || size>config.maxOutputBytes then throw fail("analysis_output_limit","Inference output exceeded the resource budget")
        }
      }
    finally entries.close()
  }
  // Discard both pipes at the OS boundary: child output cannot grow buffers or block shutdown.
  private def supervise(request:Path,output:Path):Task[Int]=ZIO.scoped {
    for
      child<-ZIO.acquireRelease(ZIO.attemptBlocking {
        val b=new ProcessBuilder(config.python,"-m","ml_inference","--request",request.toString,"--output",output.toString)
        b.directory(root.toFile)
        b.redirectOutput(ProcessBuilder.Redirect.DISCARD);b.redirectError(ProcessBuilder.Redirect.DISCARD)
        val env=b.environment();env.put("PYTHONPATH",root.toString)
        List("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS","VECLIB_MAXIMUM_THREADS").foreach(env.put(_,"1"))
        b.start()
      })(p=>ZIO.attemptBlocking {
        p.descendants().forEach(_.destroyForcibly());p.destroyForcibly();p.waitFor(2,TimeUnit.SECONDS);()
      }.ignore)
      code<-(for
        _<-(checkDisk(output,allowTransientEntries=true) *> ZIO.sleep(100.millis)).repeatWhileZIO(_=>ZIO.succeed(child.isAlive))
        exit<-ZIO.attemptBlocking(child.waitFor())
      yield exit).timeoutFail(fail("analysis_timeout","Inference exceeded its wall-clock budget",true))(config.wallTime)
    yield code
  }
  private def validateOutput(id:String,output:Path,exit:Int,options:AnalysisOptions,modelHash:Option[String],modelId:Option[String]):Task[Json]=for
    _<-checkDisk(output)
    j<-readJson(output.resolve("result.json"),config.maxResultBytes)
    result<-ZIO.attemptBlocking {
      val f=objectFields(j)
      if f.get("schema_version")!=Some(Json.Num(1)) || f.get("analysis_id")!=Some(Json.Str(id)) then throw fail("invalid_analysis_output","Inference output has an invalid schema or identity")
      f.get("error").foreach { err=>
        val e=objectFields(err)
        val code=e.get("code").collect{case Json.Str(s) if s.matches("[a-z][a-z0-9_]{0,63}")=>s}.getOrElse("analysis_failed")
        val retry=e.get("retryable").contains(Json.Bool(true))
        // Child text can contain native paths and exception details. Public errors use stable codes.
        throw fail(code,"Scientific inference failed; inspect the input coverage and analysis settings",retry)
      }
      if exit!=0 then throw fail("analysis_process_failed","Inference process exited unsuccessfully",true)
      modelHash.foreach { expected=>
        val actual=f.get("model").map(objectFields).flatMap(_.get("sha256"))
        if actual!=Some(Json.Str(expected)) then throw fail("model_mismatch","Inference used a different model than the admitted frozen artifact; resubmit to retry",true)
      }
      modelId.foreach { expected=>
        val actual=f.get("model").map(objectFields).flatMap(_.get("model_id"))
        if actual!=Some(Json.Str(expected)) then throw fail("model_mismatch","Inference model identity does not match the admitted frozen model; resubmit to retry",true)
      }
      def array(k:String)=f.get(k) match
        case Some(Json.Arr(a))=>a
        case _=>throw fail("invalid_analysis_output",s"Inference output is missing $k")
      val frames=array("frames");val candidates=array("candidates");val resources=array("resources");array("warnings")
      if frames.size<3 || frames.size>32 || candidates.size>options.max_candidates || resources.size>296 || !f.contains("model") || !f.contains("settings") then throw fail("invalid_analysis_output","Inference result dimensions exceed supported limits")
      def finite(value:Json):Unit=value match
        case Json.Num(n) if !n.doubleValue.isFinite=>throw fail("invalid_analysis_output","Inference output contains a non-finite number")
        case Json.Str(s) if s.startsWith("/") || s.startsWith("\\") || s.matches("^[A-Za-z]:.*") || s.startsWith("file:")=>throw fail("invalid_analysis_output","Inference output exposed an internal path")
        case Json.Obj(fs)=>fs.foreach((_,v)=>finite(v))
        case Json.Arr(vs)=>vs.foreach(finite)
        case _=>()
      finite(j)
      val allowed=resources.map { r=>
        val rf=objectFields(r)
        val name=rf.get("name").collect{case Json.Str(s) if safeName(s)=>s}.getOrElse(throw fail("invalid_analysis_output","Inference output has an unsafe resource name"))
        val path=output.resolve(name)
        val size=Files.size(path)
        if !Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS) || size>2L*1024*1024 || rf.get("size_bytes")!=Some(Json.Num(BigDecimal(size))) || rf.get("media_type")!=Some(Json.Str("image/png")) then throw fail("invalid_analysis_output","Inference resource metadata is invalid")
        val in=Files.newInputStream(path);val header=try in.readNBytes(8) finally in.close()
        if !header.sameElements(Array[Byte](-119,80,78,71,13,10,26,10)) then throw fail("invalid_analysis_output","Inference resource is not a PNG")
        name
      }.toSet
      if allowed.size!=resources.size then throw fail("invalid_analysis_output","Inference resources are duplicated")
      val files=Files.list(output)
      try if files.iterator().asScala.map(_.getFileName.toString).toSet != allowed+"result.json" then throw fail("invalid_analysis_output","Inference produced unregistered output files") finally files.close()
      frames.foreach { frame=>
        val ff=objectFields(frame)
        List("width","height").foreach(k=>ff.get(k) match
          case Some(Json.Num(n)) if n.intValue>=1 && n.intValue<=512 && n.doubleValue==n.intValue.toDouble=>()
          case _=>throw fail("invalid_analysis_output","Inference frame has invalid dimensions"))
      }
      val frameFields=frames.map(objectFields)
      val frameIds=frameFields.map(_.get("frame_id"))
      if frameIds.distinct.size!=frames.size || frameIds.exists(!_.exists { case Json.Str(s)=>s.nonEmpty && s.length<=256; case _=>false }) then throw fail("invalid_analysis_output","Inference frame identities are invalid")
      val times=frameFields.map(_.get("midpoint_utc") match
        case Some(Json.Str(s))=>java.time.Instant.parse(s)
        case _=>throw fail("invalid_analysis_output","Inference frame timestamps are missing"))
      if times.sliding(2).exists(pair=>pair.size==2 && !pair(0).isBefore(pair(1))) then throw fail("invalid_analysis_output","Inference frame timestamps must increase strictly")
      def number(fields:Map[String,Json],key:String):Double=fields.get(key) match
        case Some(Json.Num(n))=>n.doubleValue
        case _=>throw fail("invalid_analysis_output","Inference evidence is missing a numerical field")
      def positiveInteger(fields:Map[String,Json],key:String):Int=
        val n=number(fields,key)
        if n<1 || n>Int.MaxValue || n!=math.floor(n) then throw fail("invalid_analysis_output","Inference ranks must be positive integers")
        n.toInt
      def coordinates(fields:Map[String,Json]):Unit=
        val ra=number(fields,"right_ascension_deg");val dec=number(fields,"declination_deg")
        if ra<0 || ra>=360 || dec< -90 || dec>90 then throw fail("invalid_analysis_output","Inference sky coordinates are outside ICRS bounds")
      val ranks=candidates.map { candidate=>
        val cf=objectFields(candidate)
        val rank=positiveInteger(cf,"rank");positiveInteger(cf,"baseline_rank")
        coordinates(cf)
        if number(cf,"speed_arcsec_per_hour")<0 || number(cf,"fit_rms_px")<0 then throw fail("invalid_analysis_output","Inference motion and residuals must be nonnegative")
        cf.get("score") match
          case Some(Json.Null)=>()
          case Some(Json.Num(n)) if n.doubleValue>=0 && n.doubleValue<=1=>()
          case _=>throw fail("invalid_analysis_output","Inference vote score must be null or between zero and one")
        cf.get("detections") match
          case Some(Json.Arr(ds)) if ds.size>=options.min_epochs && ds.size<=frames.size=>
            val indices=ds.map { detection=>
              val df=objectFields(detection)
              val index=df.get("frame_index") match
                case Some(Json.Num(n)) if n.doubleValue==n.intValue.toDouble && n.intValue>=0 && n.intValue<frames.size=>n.intValue
                case _=>throw fail("invalid_analysis_output","Inference detection references an invalid frame")
              if df.get("frame_id")!=frameIds(index) || df.get("midpoint_utc")!=frameFields(index).get("midpoint_utc") then throw fail("invalid_analysis_output","Inference detection frame identity is inconsistent")
              coordinates(df)
              val x=number(df,"x");val y=number(df,"y")
              val width=number(frameFields(index),"width");val height=number(frameFields(index),"height")
              if x<0 || x>width-1 || y<0 || y>height-1 then throw fail("invalid_analysis_output","Inference detection lies outside the referenced frame pixel centers")
              index
            }
            if indices.distinct.size!=indices.size then throw fail("invalid_analysis_output","Inference detections duplicate an epoch")
          case _=>throw fail("invalid_analysis_output","Inference candidate has insufficient evidence")
        rank
      }
      if ranks.distinct.size!=ranks.size then throw fail("invalid_analysis_output","Inference ranks are duplicated")
      val urlKeys=Set("image_url","difference_url","bloom_url","moving_stack_url","stationary_stack_url")
      def rewrite(value:Json):Json=value match
        case Json.Obj(fs)=>Json.Obj(fs.map { (key,v)=>
          if urlKeys.contains(key) then v match
            case Json.Str(name) if allowed.contains(name)=>key->Json.Str(s"/api/analyses/$id/resources/$name")
            case _=>throw fail("invalid_analysis_output","Inference references an unregistered resource")
          else key->rewrite(v)
        })
        case Json.Arr(vs)=>Json.Arr(vs.map(rewrite))
        case other=>other
      rewrite(j)
    }
  yield result
  private def run(r:AnalysisRecord):Task[Unit]=
    val id=r.analysis.id
    (for
      source<-prepare(r)
      _<-ZIO.foreachDiscard(source) { src=>for
        _<-repo.update(id)(_.copy(status="preparing"))
        output=folder(id).resolve("output")
        _<-removeTree(output)
        _<-ZIO.attemptBlocking(Files.createDirectories(output))
        request=folder(id).resolve("request.json")
        body=Json.Obj("schema_version"->Json.Num(1),"analysis_id"->Json.Str(id),"source"->src,"options"->r.request.options.toJson.fromJson[Json].toOption.get,"model_dir"->Json.Str(root.resolve("models").toString))
        _<-ZIO.attemptBlocking(Files.writeString(request,body.toJson))
        _<-repo.update(id)(_.copy(status="inferencing"))
        exit<-supervise(request,output)
        result<-validateOutput(id,output,exit,r.request.options,r.model_hash,r.model_id)
        _<-repo.update(id)(_.copy(status="completed",result=Some(result),error=None))
      yield () }
    yield ()).catchAll { e=>
      val publicError=e match
        case a:ApiError=>a
        case _=>fail("analysis_failed","Inference could not complete; inspect service logs",true)
      repo.update(id)(_.copy(status="failed",result=None,error=Some(publicError))).unit *> removeTree(folder(id).resolve("output")).ignore
    }.ensuring(repo.get(id).flatMap(a=>if a.terminal then cleanupInputs(id) *> ZIO.attemptBlocking(Files.deleteIfExists(folder(id).resolve("request.json"))).ignore else ZIO.unit).ignore)
  private[service] def worker:UIO[Unit]=(repo.pending.flatMap { records=>
    ZIO.foreachDiscard(records)(run) *> ZIO.sleep(200.millis)
  }.catchAll(e=>ZIO.logWarningCause("Analysis worker iteration failed",Cause.fail(e)) *> ZIO.sleep(500.millis))).forever
  private[service] def initialize:Task[Unit]=for
    _<-ZIO.attemptBlocking(Files.createDirectories(storage))
    _<-repo.recover
    // Terminal snapshots left by an interrupted finalizer are safe to remove on startup.
    _<-ZIO.attemptBlocking {
      val dirs=Files.list(storage)
      try dirs.iterator().asScala.filter(p=>p.getFileName.toString.matches("[0-9a-f-]{36}")).map(_.getFileName.toString).toList finally dirs.close()
    }.flatMap(ids=>ZIO.foreachDiscard(ids)(id=>repo.get(id).flatMap(a=>if a.terminal then cleanupInputs(id) *> (if a.status=="failed" then removeTree(folder(id).resolve("output")) else ZIO.unit) *> ZIO.attemptBlocking(Files.deleteIfExists(folder(id).resolve("request.json"))).ignore else ZIO.unit).ignore))
  yield ()
object Analyses:
  def make(repo:AnalysisRepository,jobs:Jobs,data:Path,config:AnalysisConfig):ZIO[Scope,Throwable,Analyses]=for
    _<-ZIO.fail(ApiError("invalid_configuration","Analysis limits must be positive")).when(config.maxJobs<1 || config.wallTime<=Duration.Zero)
    s=new Analyses(repo,jobs,data.toAbsolutePath.normalize(),config)
    _<-s.initialize
    _<-s.worker.forkScoped
  yield s
