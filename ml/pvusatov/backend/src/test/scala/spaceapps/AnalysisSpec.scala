package spaceapps

import spaceapps.domain.*
import spaceapps.service.*
import spaceapps.repository.{Repository,AnalysisRepository}
import spaceapps.controller.Api
import spaceapps.integrations.grpc.GrpcServer
import spaceapps.integrations.grpc.{v1 as pb}
import spaceapps.integrations.grpc.v1.ZioAnalysis.AnalysisServiceClient
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder
import scalapb.zio_grpc.ZManagedChannel
import zio.http.{Request,Body,Status}
import zio.*
import zio.json.*
import zio.json.ast.Json
import zio.test.*
import java.nio.file.{Files,Path}

object AnalysisSpec extends ZIOSpecDefault:
  private def temp = ZIO.acquireRelease(ZIO.attemptBlocking(Files.createTempDirectory("analysis-spec")))(p => ZIO.attemptBlocking {
    val paths=Files.walk(p)
    try paths.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally paths.close()
  }.orDie)
  private def write(p:Path,s:String)=ZIO.attemptBlocking {Files.createDirectories(p.getParent);Files.writeString(p,s);()}
  private val successfulChild="""import argparse,json,pathlib
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--output');a=p.parse_args()
r=json.load(open(a.request));o=pathlib.Path(a.output);o.mkdir(exist_ok=True)
(o/'frame-000.png').write_bytes(bytes([137,80,78,71,13,10,26,10]))
(o/'result.json').write_text(json.dumps(dict(schema_version=1,analysis_id=r['analysis_id'],model={'sha256':'abc','model_id':'test'},settings={},frames=[dict(frame_id=f'f{i}',observation_id=f'f{i}',image_url='frame-000.png',difference_url='frame-000.png',width=2,height=2,midpoint_utc=f'2026-01-01T00:00:0{i}Z') for i in range(3)],candidates=[],warnings=[],resources=[dict(name='frame-000.png',media_type='image/png',size_bytes=8)])))
"""
  private def setup(dir:Path,child:String="",timeout:zio.Duration=5.seconds,maxJobs:Int=8,source:Option[Archive]=None,processor:Processor=NoProcessing)=for
    _ <- write(dir.resolve("python/ml_inference/__init__.py"),"")
    _ <- write(dir.resolve("python/ml_inference/__main__.py"),if child.nonEmpty then child else successfulChild)
    _ <- write(dir.resolve("python/models/metadata.json"),"""{"model_id":"test","sha256":"abc","feature_names":[],"score_kind":"ranking_score"}""")
    _ <- write(dir.resolve("python/fixtures/comet-d6.npz"),"fixture bytes")
    native <- Repository.open(dir.resolve("jobs.db"))
    emptySource=new Archive:
      def search(q:Query)=ZIO.succeed(Nil)
      def fetch(i:ArchiveImage,p:Path)=ZIO.unit
    jobs <- Jobs.make(native,source.getOrElse(emptySource),processor,dir)
    repo <- AnalysisRepository.open(dir.resolve("jobs.db"))
    service <- Analyses.make(repo,jobs,dir,AnalysisConfig(dir.resolve("python"),wallTime=timeout,maxJobs=maxJobs))
  yield (service,repo,jobs)
  private def done(s:Analyses,id:String):Task[Analysis]=s.get(id).flatMap(a=>if a.terminal then ZIO.succeed(a) else ZIO.sleep(20.millis) *> done(s,id))
  private def untilFile(p:Path):Task[Unit]=ZIO.attempt(Files.exists(p)).flatMap(yes=>if yes then ZIO.unit else ZIO.sleep(20.millis) *> untilFile(p))
  private def untilStatus(s:Analyses,id:String,status:String):Task[Analysis]=s.get(id).flatMap(a=>if a.status==status then ZIO.succeed(a) else ZIO.sleep(20.millis) *> untilStatus(s,id,status))
  def spec=suite("Durable ML analyses")(
    test("preserves published analysis RPC and message wire names") {
      assertTrue(
        pb.AnalysisServiceGrpc.METHOD_SUBMIT_ANALYSIS.getFullMethodName=="spaceapps.retrieval.v1.AnalysisService/SubmitAnalysis",
        pb.AnalysisServiceGrpc.METHOD_WATCH_ANALYSIS.getFullMethodName=="spaceapps.retrieval.v1.AnalysisService/WatchAnalysis",
        pb.AnalysisJob.scalaDescriptor.fullName=="spaceapps.retrieval.v1.AnalysisJob",
        pb.SubmitAnalysisRequest.scalaDescriptor.fullName=="spaceapps.retrieval.v1.SubmitAnalysisRequest"
      )
    },
    test("rejects ambiguous sources, unknown settings, invalid numerical limits and oversized regions") {
      val bad=List("{}","""{"preset":"comet-d6","download_id":"x"}""","""{"preset":"comet-d6","options":{"max_peaks":10000000}}""","""{"preset":"comet-d6","options":{"typo":1}}""")
      val range=Query.fromParameters("range",Map("right_ascension_min_deg"->"1","right_ascension_max_deg"->"2","declination_min_deg"->"2","declination_max_deg"->"3")).toOption.get
      assertTrue(bad.forall(AnalysisRequest.parse(_).isLeft),AnalysisRegion.fromQuery(range,AnalysisOptions()).isLeft)
    },
    test("validates explicit native frame subsets without changing legacy source validation") {
      val valid="""{"download_id":"download","frame_ids":["f1","f2","f3"]}"""
      val invalid=List(
        """{"download_id":"download","frame_ids":[]}""",
        """{"download_id":"download","frame_ids":["f1","f1","f2"]}""",
        """{"preset":"comet-d6","frame_ids":["f1","f2","f3"]}""",
        s"""{"download_id":"download","frame_ids":${(1 to 33).map(i=>s"f$i").toList.toJson}}"""
      )
      assertTrue(AnalysisRequest.parse(valid).isRight,invalid.forall(AnalysisRequest.parse(_).isLeft))
    },
    test("explicit ready subset renders despite a failed sibling and rejects unowned or failed frames") {
      ZIO.scoped {for
        dir<-temp
        archive=new Archive:
          def search(q:Query)=ZIO.succeed((1 to 4).toList.map(i=>ArchiveImage(Observation(s"f$i",s"2026-01-01T00:00:0${i}Z",1,"dr1"),s"https://example.test/$i")))
          def fetch(image:ArchiveImage,path:Path)=if image.observation.frame_id=="f4" then ZIO.fail(ApiError("archive_http_error","Archive returned HTTP 503")) else write(path,"native test bytes")
        child="""import argparse,json
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--output');a=p.parse_args()
r=json.load(open(a.request))
assert [f['frame_id'] for f in r['source']['observations']]==['f1','f2','f3']
"""+successfulChild
        f<-setup(dir,child,source=Some(archive))
        (s,_,jobs)=f
        query=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get
        download<-jobs.submit(query,"default",None)
        _<-jobs.events(download.id).runDrain
        request<-ZIO.fromEither(AnalysisRequest.parse(s"""{"download_id":"${download.id}","frame_ids":["f1","f2","f3"]}"""))
        selected<-s.submit(request)
        result<-done(s,selected.id)
        unknown<-ZIO.fromEither(AnalysisRequest.parse(s"""{"download_id":"${download.id}","frame_ids":["f1","f2","unknown"]}""")).flatMap(s.submit).either
        failed<-ZIO.fromEither(AnalysisRequest.parse(s"""{"download_id":"${download.id}","frame_ids":["f1","f2","f4"]}""")).flatMap(s.submit).either
        strict<-s.submit(AnalysisRequest(download_id=Some(download.id)))
        strictResult<-done(s,strict.id)
        proof=result.result.flatMap(_.asObject).flatMap(_.get("provenance")).flatMap(_.asObject).flatMap(_.get("input_selection")).flatMap(_.asObject)
      yield assertTrue(result.status=="completed",unknown.isLeft,failed.isLeft,strictResult.status=="failed",strictResult.error.exists(_.code=="download_failed"),
          proof.flatMap(_.get("selected_frame_ids")).contains(Json.Arr(Json.Str("f1"),Json.Str("f2"),Json.Str("f3"))),
          proof.flatMap(_.get("total_frames")).contains(Json.Num(4)),proof.flatMap(_.get("ready_frames")).contains(Json.Num(3)),
          result.result.flatMap(_.asObject).flatMap(_.get("warnings")).exists {case Json.Arr(items)=>items.nonEmpty;case _=>false})}
    },
    test("a bounded selected subset is admitted from a download larger than the analysis limit") {
      ZIO.scoped {for
        dir<-temp
        archive=new Archive:
          def search(q:Query)=ZIO.succeed((1 to 37).toList.map(i=>ArchiveImage(Observation(s"f$i",s"2026-01-01T00:00:${f"$i%02d"}Z",1,"dr1"),s"https://example.test/$i")))
          def fetch(image:ArchiveImage,path:Path)=if image.observation.frame_id=="f37" then ZIO.fail(ApiError("archive_http_error","Archive returned HTTP 503")) else write(path,"native test bytes")
        child="""import argparse,json
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--output');a=p.parse_args()
r=json.load(open(a.request))
assert [f['frame_id'] for f in r['source']['observations']]==[f'f{i}' for i in range(1,33)]
"""+successfulChild
        f<-setup(dir,child,source=Some(archive))
        (s,_,jobs)=f
        query=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get
        download<-jobs.submit(query,"default",None)
        _<-jobs.events(download.id).runDrain
        strict<-s.submit(AnalysisRequest(download_id=Some(download.id))).either
        request<-ZIO.fromEither(AnalysisRequest.parse(s"""{"download_id":"${download.id}","frame_ids":${(1 to 32).map(i=>s"f$i").toList.toJson}}"""))
        selected<-s.submit(request)
        result<-done(s,selected.id)
        proof=result.result.flatMap(_.asObject).flatMap(_.get("provenance")).flatMap(_.asObject).flatMap(_.get("input_selection")).flatMap(_.asObject)
      yield assertTrue(strict.left.exists {case e:ApiError=>e.code=="analysis_too_large";case _=>false},result.status=="completed",
          proof.flatMap(_.get("total_frames")).contains(Json.Num(37)),proof.flatMap(_.get("ready_frames")).contains(Json.Num(36)),
          proof.flatMap(_.get("selected_frame_ids")).exists {case Json.Arr(items)=>items.size==32;case _=>false})}
    },
    test("uses projected TAN extents so wide regions contain requested pixel edges") {
      val options=AnalysisOptions(pixel_scale_arcsec=60)
      val center=Query.fromParameters("default",Map("right_ascension_deg"->"0","declination_deg"->"0","width_arcmin"->"480","height_arcmin"->"1")).toOption.get
      val range=Query.fromParameters("range",Map("right_ascension_min_deg"->"0","right_ascension_max_deg"->"8","declination_min_deg"->"-0.01","declination_max_deg"->"0.01")).toOption.get
      val polygon=Query.fromParameters("polygon",Map("verices_degrees"->"356,-0.01,4,-0.01,4,0.01,356,0.01")).toOption.get
      val widths=List(center,range,polygon).map(q=>AnalysisRegion.fromQuery(q,options).toOption.map(r=>math.ceil(r.width_arcmin)))
      val cornerX=widths.head.map(width=>(width-1)/2-math.toDegrees(math.tan(math.toRadians(4)))*60)
      val tooWide=Query.fromParameters("default",Map("right_ascension_deg"->"0","declination_deg"->"0","width_arcmin"->"512","height_arcmin"->"1")).toOption.get
      assertTrue(widths.forall(_.contains(481d)),cornerX.exists(x=>x>= -0.5 && x<=480.5),AnalysisRegion.fromQuery(tooWide,options).isLeft)
    },
    test("deduplicates, executes a real bounded child and publishes only registered safe resources") {
      ZIO.scoped {for
        dir<-temp
        f<-setup(dir)
        (s,_,_) = f
        submitted<-ZIO.foreachPar(1 to 8)(_=>s.submit(AnalysisRequest(preset=Some("comet-d6"))))
        result<-done(s,submitted.head.id)
        path<-s.resource(result.id,"frame-000.png")
        exists<-ZIO.attempt(Files.isRegularFile(path))
        unsafe<-s.resource(result.id,"../result.json").either
        unknown<-s.get("absent").either
        events<-s.events(result.id).runCollect
      yield assertTrue(submitted.map(_.id).distinct.size==1,result.status=="completed",result.result.exists(_.toJson.contains(s"/api/analyses/${result.id}/resources/frame-000.png")),exists,unsafe.isLeft,unknown.isLeft,events.last.name=="analysis.completed",!result.toJson.contains(dir.toString))}
    },
    test("persists completion and explicitly fails interrupted processing on restart") {
      ZIO.scoped {for
        dir<-temp
        f<-setup(dir)
        (s,repo,_) = f
        a<-s.submit(AnalysisRequest(preset=Some("comet-d6")))
        completed<-done(s,a.id)
        interrupted<-repo.accept(AnalysisRequest(preset=Some("comet-d6")),"different",8)
        _<-repo.update(interrupted.id)(_.copy(status="inferencing"))
        reopened<-AnalysisRepository.open(dir.resolve("jobs.db"))
        _<-reopened.recover
        old<-reopened.get(a.id)
        failed<-reopened.get(interrupted.id)
      yield assertTrue(completed.status=="completed",old.status=="completed",failed.status=="failed",failed.error.exists(e=>e.code=="analysis_interrupted" && e.retryable))}
    },
    test("bounds active queue and records waiting downloads without blocking other jobs") {
      ZIO.scoped {for
        dir<-temp
        repo<-AnalysisRepository.open(dir.resolve("jobs.db"))
        first<-repo.accept(AnalysisRequest(download_id=Some("download")),"one",1)
        again<-repo.accept(AnalysisRequest(download_id=Some("download")),"one",1)
        full<-repo.accept(AnalysisRequest(preset=Some("comet-d6")),"two",1).either
        _<-repo.update(first.id)(_.copy(status="waiting_for_download"))
        _<-repo.recover
        waiting<-repo.get(first.id)
      yield assertTrue(first.id==again.id,full.left.exists{case e:ApiError=>e.code=="capacity_exceeded";case _=>false},waiting.status=="waiting_for_download")}
    },
    test("waits for native downloads and snapshots preserve bytes after cache removal") {
      ZIO.scoped {for
        dir<-temp
        gate<-Promise.make[Nothing,Unit]
        archive=new Archive:
          def search(q:Query)=ZIO.succeed((1 to 3).toList.map(i=>ArchiveImage(Observation(s"f$i",s"2026-01-01T00:00:0${i}Z",1,"dr1",header_metadata=Map("access_url"->Json.Str(s"https://irsa.ipac.caltech.edu/data/SPHEREx/l2b-v27-2026-198/f$i.fits"))),s"https://example.test/$i")))
          def fetch(i:ArchiveImage,p:Path)=gate.await *> write(p,"immutable native bytes")
        child="""import argparse,json,pathlib,time
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--output');a=p.parse_args()
r=json.load(open(a.request));pathlib.Path('snapshot-ready').write_text('ready')
while not pathlib.Path('continue').exists(): time.sleep(.02)
assert all(pathlib.Path(f['path']).read_text()=='immutable native bytes' for f in r['source']['observations'])
assert all('observation_id' not in f and f['release']=='dr1' and f['processing_version']=='l2b-v27-2026-198' and f['access_url'].startswith('https://irsa.ipac.caltech.edu/') for f in r['source']['observations'])
"""+successfulChild
        f<-setup(dir,child,source=Some(archive))
        (s,_,jobs)=f
        q=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get
        download<-jobs.submit(q,"default",None)
        a<-s.submit(AnalysisRequest(download_id=Some(download.id)))
        waiting<-untilStatus(s,a.id,"waiting_for_download")
        _<-gate.succeed(())
        _<-untilFile(dir.resolve("python/snapshot-ready"))
        d<-jobs.get(download.id)
        _<-ZIO.foreachDiscard(d.chunks)(c=>jobs.resource(c.id,false).flatMap {
          case Resource.Ready(p)=>ZIO.attempt(Files.delete(p))
          case _=>ZIO.fail(new RuntimeException("Native file missing before test eviction"))
        })
        _<-write(dir.resolve("python/continue"),"continue")
        completed<-done(s,a.id)
      yield assertTrue(waiting.status=="waiting_for_download",completed.status=="completed")}
    },
    test("accepts preview-only download failures while rejecting any failed native FITS") {
      ZIO.scoped {ZIO.foreach(List(false,true)) { failNative=>for
        dir<-temp
        archive=new Archive:
          def search(q:Query)=ZIO.succeed((1 to 3).toList.map(i=>ArchiveImage(Observation(s"f$i",s"2026-01-01T00:00:0${i}Z",1,"dr1"),s"https://example.test/$i")))
          def fetch(image:ArchiveImage,path:Path)=if failNative && image.observation.frame_id=="f3" then ZIO.fail(ApiError("native_failed","Native retrieval failed")) else write(path,"immutable native bytes")
        previewFailure=new Processor:
          def prepare(in:Path,out:Path,mode:String,reference:Option[Path],q:Query)=ZIO.fail(ApiError("unexpected_prepare","Default downloads must remain native"))
          def preview(in:Path,out:Path)=ZIO.fail(ApiError("preview_failed","Preview generation failed"))
        f<-setup(dir,source=Some(archive),processor=previewFailure)
        (s,_,jobs)=f
        query=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get
        download<-jobs.submit(query,"default",None)
        _<-jobs.events(download.id).runDrain
        native<-jobs.get(download.id)
        submitted<-s.submit(AnalysisRequest(download_id=Some(download.id)))
        result<-done(s,submitted.id)
      yield native.status=="completed_with_errors" && (if failNative then native.chunks.exists(_.status=="failed") && result.status=="failed" && result.error.exists(_.code=="download_failed") else native.chunks.forall(_.status=="ready") && result.status=="completed")}.map(results=>assertTrue(results.forall(identity)))}
    },
    test("rejects processed downloads at admission and when recovering previously accepted work") {
      ZIO.scoped {for
        dir<-temp
        f<-setup(dir)
        (s,repo,jobs)=f
        query=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get
        download<-jobs.submit(query,"zodi-reference-subtracted",None)
        request=AnalysisRequest(download_id=Some(download.id))
        admission<-s.submit(request).either
        api<-Api.make(jobs,"test",Path.of("docs/openapi.yaml"),analyses=Some(s))
        http<-api.routes.runZIO(Request.post("http://localhost/api/analyses/motion",Body.fromString(request.toJson)))
        body<-http.body.asString
        legacy<-repo.accept(request,"legacy-processed-request",8)
        result<-done(s,legacy.id)
      yield assertTrue(admission.left.exists {case e:ApiError=>e.code=="unsupported_analysis_input";case _=>false},
        http.status==Status.UnprocessableEntity,body.fromJson[ApiError].exists(_.code=="unsupported_analysis_input"),
        result.status=="failed",result.error.exists(_.code=="unsupported_analysis_input"),result.result.isEmpty)}
    },
    test("HTTP and typed gRPC return the same durable analysis and structured errors") {
      ZIO.scoped {for
        dir<-temp
        f<-setup(dir)
        (s,_,jobs)=f
        api<-Api.make(jobs,"test",Path.of("docs/openapi.yaml"),analyses=Some(s))
        port<-GrpcServer.start(jobs,"test","127.0.0.1",0,analyses=Some(s))
        client<-AnalysisServiceClient.scoped(ZManagedChannel(NettyChannelBuilder.forAddress("127.0.0.1",port).usePlaintext()))
        accepted<-api.routes.runZIO(Request.post("http://localhost/api/analyses/motion",Body.fromString("{\"preset\":\"comet-d6\"}")))
        body<-accepted.body.asString
        a<-ZIO.fromEither(body.fromJson[Analysis]).mapError(new RuntimeException(_))
        same<-client.submitAnalysis(pb.SubmitAnalysisRequest(source=pb.SubmitAnalysisRequest.Source.Preset("comet-d6")))
        events<-client.watchAnalysis(pb.AnalysisRequest(a.id)).runCollect
        grpc<-client.getAnalysis(pb.AnalysisRequest(a.id))
        http<-api.routes.runZIO(Request.get(s"http://localhost/api/analyses/${a.id}"))
        finalBody<-http.body.asString
        image<-api.routes.runZIO(Request.get(s"http://localhost/api/analyses/${a.id}/resources/frame-000.png"))
        invalid<-api.routes.runZIO(Request.post("http://localhost/api/analyses/motion",Body.fromString("{}")))
        unknown<-client.getAnalysis(pb.AnalysisRequest("missing")).either
        models<-client.getModels(pb.ModelsRequest())
        presets<-api.routes.runZIO(Request.get("http://localhost/api/analyses/presets"))
        presetBody<-presets.body.asString
      yield assertTrue(accepted.status==Status.Accepted,a.id==same.id,grpc.status==pb.AnalysisState.COMPLETED,
        finalBody.fromJson[Analysis].exists(_.status=="completed"),events.last.getAnalysis.id==a.id,
        image.status==Status.Ok,invalid.status==Status.UnprocessableEntity,
        unknown.left.exists(_.getStatus.getCode==io.grpc.Status.Code.NOT_FOUND),models.models.size==1,presetBody.contains("comet-d6"))}
    },
    test("rejects a worker result from a model other than the admitted frozen hash") {
      ZIO.scoped {for
        dir<-temp
        f<-setup(dir,successfulChild.replace("model={'sha256':'abc','model_id':'test'}","model={'sha256':'wrong'}"))
        a<-f._1.submit(AnalysisRequest(preset=Some("comet-d6")))
        result<-done(f._1,a.id)
      yield assertTrue(result.status=="failed",result.error.exists(_.code=="model_mismatch"),result.result.isEmpty)}
    },
    test("rejects missing or mismatching model identifiers despite a matching model hash") {
      ZIO.scoped {ZIO.foreach(List("model={'sha256':'abc'}","model={'sha256':'abc','model_id':'wrong'}")) { model=>for
        dir<-temp
        child=successfulChild.replace("model={'sha256':'abc','model_id':'test'}",model)
        f<-setup(dir,child)
        a<-f._1.submit(AnalysisRequest(preset=Some("comet-d6")))
        result<-done(f._1,a.id)
      yield result.status=="failed" && result.error.exists(_.code=="model_mismatch")}.map(results=>assertTrue(results.forall(identity)))}
    },
    test("rejects invalid candidate coordinates, ranks, motion and off-frame detections") {
      val base=successfulChild+"""
r=json.loads((o/'result.json').read_text())
r['candidates']=[dict(id='candidate-000',rank=1,method='residual_track',score=.5,score_kind='random_forest_vote_fraction',baseline_score=1,baseline_rank=1,right_ascension_deg=0,declination_deg=0,speed_arcsec_per_hour=1,fit_rms_px=0,warnings=[],detections=[dict(frame_index=i,frame_id=f'f{i}',midpoint_utc=f'2026-01-01T00:00:0{i}Z',x=1,y=1,right_ascension_deg=0,declination_deg=0,residual_snr=5) for i in range(3)])]
"""
      val mutations=List(
        "", "r['candidates'][0]['score']=None",
        "r['candidates'][0]['score']=-.1", "r['candidates'][0]['score']=1.1",
        "r['candidates'][0]['baseline_rank']=0",
        "r['candidates'][0]['rank']=0", "r['candidates'][0]['rank']=1.5",
        "r['candidates'].append(dict(r['candidates'][0]))",
        "r['candidates'][0]['right_ascension_deg']=360", "r['candidates'][0]['declination_deg']=-91",
        "r['candidates'][0]['speed_arcsec_per_hour']=-1", "r['candidates'][0]['fit_rms_px']=-1",
        "r['candidates'][0]['detections'][0]['x']=-.6", "r['candidates'][0]['detections'][0]['y']=1.6",
        "r['candidates'][0]['detections'][0]['right_ascension_deg']=-1", "r['candidates'][0]['detections'][0]['declination_deg']=91",
        "r['candidates'][0]['detections'][0]['frame_index']=.5")
      ZIO.scoped {ZIO.foreach(mutations) { mutation=>for
        dir<-temp
        f<-setup(dir,base+mutation+"\n(o/'result.json').write_text(json.dumps(r))\n")
        a<-f._1.submit(AnalysisRequest(preset=Some("comet-d6")))
        result<-done(f._1,a.id)
      yield (if mutation.isEmpty || mutation=="r['candidates'][0]['score']=None" then result.status=="completed" else result.status=="failed" && result.result.isEmpty)}.map(results=>assertTrue(results.forall(identity)))}
    },
    test("rejects unregistered, escaping, nonfinite and path leaking worker output") {
      val mutations=List(
        "r['resources'][0]['name']='../escape.png'",
        "(o/'unexpected.txt').write_text('unexpected')",
        "r['warnings']=[float('nan')]",
        "r['warnings']=['/secret/internal/path']")
      ZIO.scoped {ZIO.foreach(mutations) { mutation=>for
        dir<-temp
        child=successfulChild+"\nr=json.loads((o/'result.json').read_text())\n"+mutation+"\n(o/'result.json').write_text(json.dumps(r))\n"
        f<-setup(dir,child)
        a<-f._1.submit(AnalysisRequest(preset=Some("comet-d6")))
        result<-done(f._1,a.id)
        hidden<-f._1.resource(a.id,"frame-000.png").either
      yield result.status=="failed" && result.result.isEmpty && hidden.isLeft}.map(results=>assertTrue(results.forall(identity)))}
    },
    test("tolerates scratch files atomically renamed and removed while a real child publishes") {
      val child="""import argparse,pathlib,threading,time
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--output');a=p.parse_args()
out=pathlib.Path(a.output);stop=threading.Event()
def churn(index):
    first=out/f'scratch-{index}.tmp';second=out/f'scratch-{index}.renamed'
    while not stop.is_set():
        first.write_bytes(b'scratch')
        first.replace(second)
        second.unlink()
threads=[threading.Thread(target=churn,args=(i,)) for i in range(8)]
for thread in threads: thread.start()
time.sleep(2)
stop.set()
for thread in threads: thread.join()
"""+successfulChild
      ZIO.scoped {for
        dir<-temp
        f<-setup(dir,child)
        results<-ZIO.foreach(1 to 3) { i=>for
          a<-f._1.submit(AnalysisRequest(preset=Some("comet-d6"),options=AnalysisOptions(min_snr=4+i)))
          result<-done(f._1,a.id)
        yield result.status }
      yield assertTrue(results.forall(_=="completed"))}
    },
    test("times out a child and rejects invalid output rather than publishing it") {
      ZIO.scoped {for
        dir<-temp
        f<-setup(dir,"import time;time.sleep(60)",100.millis)
        a<-f._1.submit(AnalysisRequest(preset=Some("comet-d6")))
        timed<-done(f._1,a.id)
        dir2<-temp
        f2<-setup(dir2,"import argparse,pathlib;p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--output');a=p.parse_args();pathlib.Path(a.output,'result.json').write_text('{}')")
        b<-f2._1.submit(AnalysisRequest(preset=Some("comet-d6")))
        invalid<-done(f2._1,b.id)
      yield assertTrue(timed.status=="failed",timed.error.exists(_.code=="analysis_timeout"),invalid.status=="failed",invalid.result.isEmpty)}
    }
  ) @@ TestAspect.withLiveClock @@ TestAspect.timeout(30.seconds) @@ TestAspect.sequential
