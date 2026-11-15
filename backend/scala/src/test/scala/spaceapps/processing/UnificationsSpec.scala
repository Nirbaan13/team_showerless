package spaceapps.processing

import spaceapps.processing.controller.{UnificationApi,HistoricalMotionApi}
import spaceapps.processing.integrations.HttpHistoricalMotionClient
import spaceapps.processing.service.Unifications
import spaceapps.processing.service.model.*
import spaceapps.processing.repository.UnificationRepository

import spaceapps.irsa.model.*
import spaceapps.infra.model.ApiError
import spaceapps.irsa.service.*
import spaceapps.infra.service.FileCache
import spaceapps.irsa.repository.Repository
import spaceapps.downloads.repository.DownloadsRepository
import spaceapps.downloads.service.*
import spaceapps.downloads.integrations.protocol.*
import zio.*
import zio.json.*
import zio.json.ast.Json
import zio.test.*
import zio.http.*
import java.nio.file.{Files,Path,StandardCopyOption}
import java.security.MessageDigest
import java.util.zip.{ZipEntry,ZipOutputStream}
import scala.jdk.CollectionConverters.*

object UnificationsSpec extends ZIOSpecDefault:
  private val query=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get
  private val image=ArchiveImage(Observation("native-1","2026-01-01T00:00:00Z",1,"DR1"),"https://example.test/one.fits")
  private def temp=ZIO.acquireRelease(ZIO.attemptBlocking(Files.createTempDirectory("unifications-service")))(p=>ZIO.attemptBlocking {
    val stream=Files.walk(p);try stream.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally stream.close()
  }.orDie)
  private def write(p:Path,s:String)=ZIO.attemptBlocking {Files.createDirectories(p.getParent);Files.writeString(p,s);()}
  private def done(jobs:Jobs,id:String):Task[Download]=jobs.get(id).flatMap(d=>if d.terminal then ZIO.succeed(d) else ZIO.sleep(10.millis) *> done(jobs,id))
  private def terminal(s:Unifications,id:String):Task[UnificationJob]=s.get(id).flatMap(j=>if Set("failed","completed")(j.status) then ZIO.succeed(j) else ZIO.sleep(10.millis) *> terminal(s,id))
  private def fixture(dir:Path,budget:Long=1024L*1024*1024)=for
    repo <- Repository.open(dir.resolve("state.sqlite"))
    cache <- FileCache.open(dir,dir.resolve("state.sqlite"),budget,64L*1024*1024,0)
    source=new Archive:
      def search(q:Query)=ZIO.succeed(List(image))
      def fetch(i:ArchiveImage,p:Path)=write(p,"original native bytes")
    bounded <- CapacityArchive.make(source,dir,budget,64L*1024*1024,0,Some(cache))
    jobs <- Jobs.make(repo,bounded,NoProcessing,dir)
    download <- jobs.submit(query,"default",None)
    completed <- done(jobs,download.id)
    native <- jobs.resource(completed.chunks.head.id,false)
    _ <- ZIO.fail(new Exception(s"Native fixture did not publish: ${completed.toJson}; $native")).unless(completed.status=="completed" && native.isInstanceOf[Resource.Ready])
    ar <- DownloadsRepository.open(dir.resolve("state.sqlite"))
    registry=new ProviderRegistry(Nil)
    discovery <- FederatedDiscovery.make(registry,ar)
    client <- ZIO.service[Client]
    downloads <- DownloadJobs.make(registry,ar,new StreamingDownloader(new ArchiveTransport(client),dir.resolve("archive-assets"),capacity=Some(cache)))
    service=new DownloadsService(registry,ar,discovery,downloads)
  yield (jobs,cache,ar,service,completed)
  private def selection(d:Download):Json=Json.Obj("inputs"->Json.Arr(Json.Obj("kind"->Json.Str("native_chunk"),"id"->Json.Str(d.chunks.head.id),"download_id"->Json.Str(d.id))),"grid"->Json.Obj("kind"->Json.Str("pixel"),"width"->Json.Num(2),"height"->Json.Num(2)))
  private def obj(j:Json)=j.asInstanceOf[Json.Obj].fields.toMap
  private def text(j:Json)=j.asInstanceOf[Json.Str].value
  private def sha(p:Path)=MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(p)).map(b=>f"${b & 255}%02x").mkString
  private def npy(shape:String):Array[Byte]=
    val base=s"{'descr': '<f4', 'fortran_order': False, 'shape': ($shape), }"
    val header=base+" "*((16-(10+base.length+1)%16)%16)+"\n"
    Array[Byte](0x93.toByte,78,85,77,80,89,1,0,(header.length & 255).toByte,(header.length >> 8).toByte)++header.getBytes(java.nio.charset.StandardCharsets.US_ASCII)++Array.fill[Byte](if shape=="1, 2, 2" then 16 else 4)(0)
  private def output(dir:Path,request:Json,wrongIdentity:Boolean=false,reverse:Boolean=false,wrongAuxiliary:Boolean=false):Task[Json]=ZIO.attemptBlocking {
    val id=text(obj(request)("job_id"));val base=s"unifications/$id/output";val npz=dir.resolve(base+"/dataset.npz");val manifest=dir.resolve(base+"/manifest.json")
    Files.createDirectories(npz.getParent)
    val inputs=obj(request)("inputs").asInstanceOf[Json.Arr].elements.toList
    val ordered=if reverse then inputs.reverse else inputs
    val frames=ordered.map { value=>
      val input=obj(value)
      val frame=Json.Obj("frame_id"->input("id"),"source_sha256"->input("sha256"),"profile"->input("profile"),"provenance"->input("metadata"),"analysis_eligible"->Json.Bool(false))
      input.get("auxiliaries") match
        case Some(auxiliaries)=>
          val assets=Json.Obj(zio.Chunk.fromIterable(obj(auxiliaries).toList.map { (name,descriptor)=>
            val values=obj(descriptor)
            val fields=List("id","sha256","bytes").map(key=>key->(if wrongAuxiliary && key=="sha256" then Json.Str("0"*64) else values(key)))
            name->Json.Obj(zio.Chunk.fromIterable(fields))
          }))
          Json.Obj(frame.fields ++ zio.Chunk("auxiliary_assets"->assets,"historical_motion_qualification"->Json.Obj("auxiliary_sources"->assets)))
        case _=>frame
    }
    val manifestText=Json.Obj("schema_version"->Json.Num(1),"job_id"->Json.Str(id),"grid"->obj(request)("grid"),"frames"->Json.Arr(zio.Chunk.fromIterable(frames)),"options"->obj(request)("options")).toJson
    val manifestBytes=manifestText.getBytes(java.nio.charset.StandardCharsets.UTF_8)
    BundleFixture.write(npz,BundleFixture.withFrames(inputs.size).updated("manifest",BundleFixture.npy("|u1",List(manifestBytes.length),Some(manifestBytes))))
    Files.writeString(manifest,manifestText)
    def descriptor(p:Path)=Json.Obj("path"->Json.Str(dir.relativize(p).toString),"bytes"->Json.Num(Files.size(p)),"sha256"->Json.Str(sha(p)))
    Json.Obj("schema_version"->Json.Num(1),"job_id"->Json.Str(if wrongIdentity then "wrong" else id),"status"->Json.Str("completed"),"bundle"->descriptor(npz),"manifest"->descriptor(manifest),"frame_count"->Json.Num(inputs.size),"width"->Json.Num(2),"height"->Json.Num(2),"detection_ready"->Json.Bool(false),"warnings"->Json.Arr())
  }
  private def python(python:String,script:String,args:String*):Task[String]=ZIO.attemptBlocking {
    val builder=new ProcessBuilder((List(python,"-c",script)++args).asJava)
    builder.environment().put("PYTHONPATH",Path.of("../pipeline").toAbsolutePath.normalize().toString)
    builder.redirectErrorStream(true)
    val process=builder.start()
    if !process.waitFor(30,java.util.concurrent.TimeUnit.SECONDS) then {process.destroyForcibly();throw new Exception("Python integration command timed out")}
    val output=new String(process.getInputStream.readAllBytes(),java.nio.charset.StandardCharsets.UTF_8)
    if process.exitValue()!=0 then throw new Exception(output.take(4096))
    output
  }
  def spec=suite("unification lifecycle")(
    test("completed native IDs are snapshotted before callback, source replacement preserves bytes, artifact is durable and eviction explicit") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        original <- jobs.resource(d.chunks.head.id,false).map {case Resource.Ready(p)=>p;case _=>throw new Exception("missing fixture")}
        snapshot <- Promise.make[Nothing,String]
        callback=(request:Json)=>for
          value <- ZIO.attemptBlocking {
            val input=obj(obj(request)("inputs").asInstanceOf[Json.Arr].elements.head)
            val p=dir.resolve(text(input("path")))
            val replacement=original.resolveSibling("replacement")
            Files.writeString(replacement,"replacement bytes");Files.move(replacement,original,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE)
            Files.readString(p)
          }
          _ <- snapshot.succeed(value)
          result <- output(dir,request)
        yield result
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),callback)
        accepted <- s.submit(selection(d))
        completed <- terminal(s,accepted.id)
        _ <- ZIO.fail(new Exception(completed.toJson)).unless(completed.status=="completed")
        seen <- snapshot.await
        artifact <- ZIO.scoped(s.artifact(accepted.id))
        bytes <- ZIO.attemptBlocking(Files.size(artifact))
        _ <- ZIO.attemptBlocking(Files.delete(artifact))
        missing <- ZIO.scoped(s.artifact(accepted.id)).either
        status <- s.get(accepted.id)
        cleaned <- ZIO.attemptBlocking(!Files.exists(dir.resolve(s"unifications/${accepted.id}/inputs")) && !Files.exists(dir.resolve(s"unifications/${accepted.id}/output")))
      yield assertTrue(completed.status=="completed",completed.artifact_url.contains(s"/api/image-unifications/${accepted.id}/artifact"),seen=="original native bytes",bytes>0,missing.left.exists {case e:ApiError=>e.code=="artifact_unavailable";case _=>false},status.artifact_url.isEmpty,cleaned) }
    },
    test("unknown native IDs reject before acceptance and mismatched callback identity never publishes") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),r=>output(dir,r,true))
        bad=selection(d.copy(chunks=List(d.chunks.head.copy(id="unknown"))))
        rejected <- s.submit(bad).either
        accepted <- s.submit(selection(d))
        failed <- terminal(s,accepted.id)
        unavailable <- ZIO.scoped(s.artifact(accepted.id)).either
        unpublished <- ZIO.attemptBlocking(!Files.exists(dir.resolve(s"unifications/${accepted.id}/dataset.npz")))
      yield assertTrue(rejected.isLeft,failed.status=="failed",failed.error.exists(_.code=="invalid_output"),unavailable.isLeft,unpublished) }
    },
    test("archive IDs use persisted checksums and reject changed or symlinked source bytes") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        record=spaceapps.downloads.model.ArchiveRecord.create("eso","science","observation-real",spaceapps.downloads.model.ProductKind.image)
        _ <- ar.saveSearch(spaceapps.downloads.model.SearchSnapshot("search",spaceapps.downloads.model.ArchiveQuery(spaceapps.downloads.model.Circle(1,2,1),List("eso")),status="completed",records=List(record)))
        id="a"*64
        path=dir.resolve("archive-assets").resolve(id)
        _ <- write(path,"persisted archive bytes")
        stored=spaceapps.downloads.model.StoredAsset(id,23,sha(path),"native")
        _ <- ar.saveDownload(spaceapps.downloads.model.DownloadSnapshot("archive-download",spaceapps.downloads.model.DownloadSelection(List(record.id)),status="completed",assets=List(spaceapps.downloads.model.AssetOutcome(record.id,"ready",Some(stored)))))
        request=Json.Obj("inputs"->Json.Arr(Json.Obj("kind"->Json.Str("archive_asset"),"id"->Json.Str(id))),"grid"->obj(selection(d))("grid"))
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),r=>output(dir,r))
        accepted <- s.submit(request)
        completed <- terminal(s,accepted.id)
        _ <- write(path,"changed! archive bytes!")
        changed <- s.submit(request).either
        _ <- ZIO.attemptBlocking {Files.delete(path);Files.createSymbolicLink(path,dir.resolve("raw").resolve("missing.fits"))}
        symlink <- s.submit(request).either
      yield assertTrue(completed.status=="completed",changed.left.exists {case e:ApiError=>e.code=="source_changed";case _=>false},symlink.isLeft) }
    },
    test("multiple archive products from one physical observation preserve the same collection-scoped identity") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        records=List("product-v1","product-v2").map(product=>spaceapps.downloads.model.ArchiveRecord.create("eso","science",product,spaceapps.downloads.model.ProductKind.image,native=Map("obs_id"->"physical-exposure-7")))
        _ <- ar.saveSearch(spaceapps.downloads.model.SearchSnapshot("identity-search",spaceapps.downloads.model.ArchiveQuery(spaceapps.downloads.model.Circle(1,2,1),List("eso")),status="completed",records=records))
        ids=List("a"*64,"b"*64)
        _ <- ZIO.foreachDiscard(ids)(id=>write(dir.resolve("archive-assets").resolve(id),"persisted archive bytes"))
        assets=ids.zip(records).map { (id,r)=>spaceapps.downloads.model.AssetOutcome(r.id,"ready",Some(spaceapps.downloads.model.StoredAsset(id,23,sha(dir.resolve("archive-assets").resolve(id)),"native"))) }
        _ <- ar.saveDownload(spaceapps.downloads.model.DownloadSnapshot("identity-download",spaceapps.downloads.model.DownloadSelection(records.map(_.id)),status="completed",assets=assets))
        captured <- Promise.make[Nothing,List[Json]]
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),r=> {
          val metadata=obj(r)("inputs").asInstanceOf[Json.Arr].elements.toList.map(i=>obj(i)("metadata"))
          captured.succeed(metadata) *> output(dir,r)
        })
        request=Json.Obj("inputs"->Json.Arr(zio.Chunk.fromIterable(ids.map(id=>Json.Obj("kind"->Json.Str("archive_asset"),"id"->Json.Str(id))))),"grid"->obj(selection(d))("grid"))
        accepted <- s.submit(request)
        completed <- terminal(s,accepted.id)
        metadata <- captured.await
        physical=metadata.map(m=>obj(m)("observation_id"))
        products=metadata.map(m=>obj(m).get("product_id"))
      yield assertTrue(completed.status=="completed",physical.distinct.size==1,physical.head!=Json.Null,products.flatten.distinct.size==2) }
    },
    test("unWISE science resolves completed same-record companions and preserves physical identity") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        record=spaceapps.downloads.model.ArchiveRecord.create("unwise-neo11","neo11","tile-w2-e001",spaceapps.downloads.model.ProductKind.image,native=Map("coadd_id"->"0857m076","band"->"W2","epoch"->"001")).copy(analysisEligible=true)
        _ <- ar.saveSearch(spaceapps.downloads.model.SearchSnapshot("unwise-search",spaceapps.downloads.model.ArchiveQuery(spaceapps.downloads.model.Circle(1,2,1),List("unwise-neo11")),status="completed",records=List(record)))
        ids=List("a"*64,"b"*64,"c"*64,"d"*64)
        roles=List("#this","#inverse-variance","#coverage","#contributors")
        _ <- ZIO.foreachDiscard(ids)(id=>write(dir.resolve("archive-assets").resolve(id),"persisted archive bytes"))
        assets=ids.zip(roles).map { (id,role)=>spaceapps.downloads.model.AssetOutcome(record.id,"ready",Some(spaceapps.downloads.model.StoredAsset(id,23,sha(dir.resolve("archive-assets").resolve(id)),"native")),provenance=Map("asset_role"->role)) }
        _ <- ar.saveDownload(spaceapps.downloads.model.DownloadSnapshot("unwise-download",spaceapps.downloads.model.DownloadSelection(List(record.id)),status="completed",assets=assets))
        captured <- Promise.make[Nothing,(Json,Boolean)]
        corrupt <- Ref.make(false)
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),r=> {
          val input=obj(r)("inputs").asInstanceOf[Json.Arr].elements.head
          val companions=obj(obj(input)("auxiliaries"))
          val intact=companions.values.forall { descriptor=>
            val fields=obj(descriptor);val relative=text(fields("path"));val file=dir.resolve(relative)
            relative.split("/").length==4 && Files.readString(file)=="persisted archive bytes" && fields("bytes")==Json.Num(23) && fields("sha256")==Json.Str(sha(file))
          }
          captured.succeed(input->intact) *> corrupt.get.flatMap(bad=>output(dir,r,wrongAuxiliary=bad))
        })
        request=Json.Obj("inputs"->Json.Arr(Json.Obj("kind"->Json.Str("archive_asset"),"id"->Json.Str(ids.head))),"grid"->obj(selection(d))("grid"))
        accepted <- s.submit(request)
        completed <- terminal(s,accepted.id)
        (input,intact) <- captured.await
        _ <- ar.updateDownload("unwise-download")(_.copy(assets=assets.take(2)))
        missing <- s.submit(request).either
        _ <- ar.updateDownload("unwise-download")(_.copy(assets=assets))
        auxiliaryRequest=Json.Obj("inputs"->Json.Arr(Json.Obj("kind"->Json.Str("archive_asset"),"id"->Json.Str(ids(1)))),"grid"->obj(selection(d))("grid"))
        wrongRole <- s.submit(auxiliaryRequest).either
        _ <- ar.updateDownload("unwise-download")(_.copy(assets=assets.map(a=>if a.provenance.get("asset_role").contains("#coverage") then a.copy(record_id="another-observation") else a)))
        wrongRecord <- s.submit(request).either
        _ <- ar.updateDownload("unwise-download")(_.copy(assets=assets))
        _ <- corrupt.set(true)
        corruptAccepted <- s.submit(request)
        corruptJob <- terminal(s,corruptAccepted.id)
        _ <- write(dir.resolve("archive-assets").resolve(ids(2)),"persisted archive byteX")
        changed <- s.submit(request).either
      yield assertTrue(completed.status=="completed",obj(input)("profile")==Json.Str("unwise"),
        obj(obj(input)("metadata"))("observation_id")==Json.Str("unwise:neo11:0857m076:W2:e001"),
        obj(input).get("auxiliaries").exists(j=>obj(j).keySet==Set("inverse_variance","coverage","contributors")),missing.isLeft,wrongRole.isLeft,wrongRecord.isLeft,intact,corruptJob.error.exists(_.code=="invalid_output"),changed.left.exists {case e:ApiError=>e.code=="source_changed";case _=>false}) }
    },
    test("validated frame identities allow chronological output order different from selection order") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        next <- jobs.submit(Query.fromParameters("default",Map("right_ascension_deg"->"3","declination_deg"->"2")).toOption.get,"default",None)
        second <- done(jobs,next.id)
        firstInput=obj(selection(d))("inputs").asInstanceOf[Json.Arr].elements.head
        secondInput=obj(selection(second))("inputs").asInstanceOf[Json.Arr].elements.head
        request=Json.Obj("inputs"->Json.Arr(firstInput,secondInput),"grid"->obj(selection(d))("grid"))
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),r=>output(dir,r,reverse=true))
        accepted <- s.submit(request)
        completed <- terminal(s,accepted.id)
      yield assertTrue(completed.status=="completed") }
    },
    test("restart fails abandoned queued work and cleans only owned snapshots and staging") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        repo <- UnificationRepository.open(dir.resolve("state.sqlite"))
        accepted <- repo.accept(selection(d))
        base=dir.resolve(s"unifications/${accepted.id}")
        _ <- write(base.resolve("inputs/000.fits"),"orphan") *> write(base.resolve("output/dataset.npz"),"partial") *> write(base.resolve("request.json"),"orphan request") *> write(base.resolve("dataset.npz"),"unregistered output") *> write(base.resolve("user.txt"),"keep")
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),_=>ZIO.fail(new Exception("must not resume")))
        recovered <- s.get(accepted.id)
        files <- ZIO.attemptBlocking(List("inputs","output","request.json","dataset.npz","user.txt").map(p=>Files.exists(base.resolve(p))))
      yield assertTrue(recovered.status=="failed",recovered.error.exists(_.code=="interrupted"),files==List(false,false,false,false,true)) }
    },
    test("tight admitted capacity publishes from its existing reservation without a second output charge") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir,200L*1024*1024)
        (jobs,cache,ar,archive,d)=f
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),r=>output(dir,r))
        accepted <- s.submit(selection(d))
        completed <- terminal(s,accepted.id)
      yield assertTrue(completed.status=="completed",completed.artifact_url.nonEmpty) }
    },
    test("capacity is reserved before snapshots or private work starts") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir,64L*1024*1024)
        (jobs,cache,ar,archive,d)=f
        invoked <- Ref.make(false)
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),r=>invoked.set(true) *> output(dir,r))
        accepted <- s.submit(selection(d))
        failed <- terminal(s,accepted.id)
        called <- invoked.get
        staged <- ZIO.attemptBlocking(Files.exists(dir.resolve(s"unifications/${accepted.id}/inputs")))
      yield assertTrue(failed.status=="failed",failed.error.exists(_.code=="cache_capacity"),!called,!staged) }
    },
    test("shutdown retains immutable inputs until the bounded callback terminates") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        entered <- Promise.make[Nothing,Path]
        finish <- Promise.make[Nothing,Unit]
        scope <- ZIO.acquireRelease(Scope.make)(scope=>finish.succeed(()) *> scope.close(Exit.unit))
        s <- scope.extend(Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),r=> {
          val input=obj(obj(r)("inputs").asInstanceOf[Json.Arr].elements.head)
          entered.succeed(dir.resolve(text(input("path")))) *> finish.await *> output(dir,r)
        }))
        accepted <- s.submit(selection(d))
        input <- entered.await
        closing <- scope.close(Exit.unit).fork
        _ <- ZIO.sleep(30.millis)
        stillClosing <- closing.poll
        kept <- ZIO.attemptBlocking(Files.exists(input))
        _ <- finish.succeed(())
        _ <- closing.join
        status <- s.get(accepted.id)
        removed <- ZIO.attemptBlocking(!Files.exists(input))
      yield assertTrue(stillClosing.isEmpty,kept,status.status=="failed",removed) }
    },
    test("streaming response pins a registered NPZ through cache pressure until response scope closes") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),r=>output(dir,r))
        accepted <- s.submit(selection(d))
        _ <- terminal(s,accepted.id)
        scope <- ZIO.acquireRelease(Scope.make)(_.close(Exit.unit))
        response <- scope.extend(new UnificationApi(s).routes.runZIO(Request.get(s"http://localhost/api/image-unifications/${accepted.id}/artifact")))
        blocked <- cache.withReservation(1024L*1024*1024-1)(ZIO.unit).either
        bytes <- response.body.asChunk
        _ <- scope.close(Exit.unit)
        released <- cache.withReservation(1024L*1024*1024-1)(ZIO.unit).either
        unavailable <- s.get(accepted.id)
      yield assertTrue(response.status==Status.Ok,bytes.size>0,blocked.isLeft,released.isRight,unavailable.artifact_url.isEmpty) }
    },
    test("real Scala HTTP operation publishes an artifact that the Python ML loader reloads") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        executable=sys.env("UNIFICATION_PYTHON")
        original <- jobs.resource(d.chunks.head.id,false).map {case Resource.Ready(p)=>p;case _=>throw new Exception("missing fixture")}
        _ <- python(executable,"import sys,numpy as np; from astropy.io import fits; h=fits.PrimaryHDU(np.arange(4,dtype=np.float32).reshape(2,2)); h.header['BUNIT']='MJy/sr'; h.writeto(sys.argv[1],overwrite=True)",original.toString)
        port <- ZIO.attemptBlocking {val socket=new java.net.ServerSocket(0);try socket.getLocalPort finally socket.close()}
        process <- ZIO.acquireRelease(ZIO.attemptBlocking {
          val b=new ProcessBuilder(executable,"-m","uvicorn","unification.app:app","--host","127.0.0.1","--port",port.toString,"--log-level","warning")
          b.environment().put("PYTHONPATH",Path.of("../pipeline").toAbsolutePath.normalize().toString)
          b.environment().put("UNIFICATION_DATA_ROOT",dir.toString)
          b.redirectErrorStream(true);b.redirectOutput(dir.resolve("python-http.log").toFile);b.start()
        })(p=>ZIO.attemptBlocking {p.destroy();if !p.waitFor(10,java.util.concurrent.TimeUnit.SECONDS) then {p.destroyForcibly();p.waitFor()};()}.orDie)
        _ <- ZIO.attemptBlocking {val socket=new java.net.Socket("127.0.0.1",port);socket.close()}.retry(Schedule.spaced(100.millis) && Schedule.recurs(150))
        client <- spaceapps.processing.integrations.HttpPipelineClient.make(s"http://127.0.0.1:$port")
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),client.unify)
        accepted <- s.submit(selection(d))
        completed <- terminal(s,accepted.id)
        _ <- ZIO.fail(new Exception(completed.toJson)).unless(completed.status=="completed")
        artifact <- s.artifact(accepted.id)
        loaded <- python(executable,"import sys,numpy as np; from unification.ml import load_bundle; b=load_bundle(sys.argv[1]); assert b.images.shape==(1,2,2); assert np.isfinite(b.tensor).all(); assert np.allclose(b.images[0],[[0,1],[2,3]]); print('loaded real unified ML data')",artifact.toString)
      yield assertTrue(loaded.contains("loaded real unified ML data")) }
    } @@ TestAspect.ifEnv("UNIFICATION_PYTHON")(_.nonEmpty),
    test("motion route retains its managed artifact lease throughout the upstream request") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),r=>output(dir,r))
        accepted <- s.submit(selection(d))
        _ <- terminal(s,accepted.id)
        entered <- Promise.make[Nothing,Unit]
        runtime <- ZIO.runtime[Any]
        release=new java.util.concurrent.CountDownLatch(1)
        server <- ZIO.acquireRelease(ZIO.attempt {
          val server=com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1",0),0)
          server.createContext("/internal/motion/prepared",exchange=> {
            exchange.getRequestBody.readAllBytes()
            Unsafe.unsafe {implicit unsafe=>runtime.unsafe.run(entered.succeed(())).getOrThrowFiberFailure()}
            release.await(10,java.util.concurrent.TimeUnit.SECONDS)
            val body="{\"candidates\":[]}".getBytes(java.nio.charset.StandardCharsets.UTF_8)
            exchange.getResponseHeaders.add("Content-Type","application/json");exchange.sendResponseHeaders(200,body.length)
            try exchange.getResponseBody.write(body) finally exchange.close()
          });server.start();server
        })(server=>ZIO.succeed {release.countDown();server.stop(0)})
        client <- HttpHistoricalMotionClient.make(s"http://127.0.0.1:${server.getAddress.getPort}")
        api=new HistoricalMotionApi(s,client)
        request=Json.Obj("unification_id"->Json.Str(accepted.id),"profile"->Json.Str("stellar_proper_motion"))
        result <- ZIO.scoped(api.routes.runZIO(Request.post("http://localhost/api/motion/search",Body.fromString(request.toJson)))).fork
        _ <- entered.await
        blocked <- cache.withReservation(1024L*1024*1024-1)(ZIO.unit).either
        _ <- ZIO.succeed(release.countDown())
        response <- result.join
        body <- response.body.asString
        released <- cache.withReservation(1024L*1024*1024-1)(ZIO.unit).either
        legacy <- api.routes.runZIO(Request.post("http://localhost/api/motion/search",Body.fromString("{\"ra\":1,\"dec\":2}")))
      yield assertTrue(blocked.isLeft,released.isRight,response.status==Status.Ok,body.contains("candidates"),legacy.status==Status.NotImplemented) }
    },
    test("public routes accept ID selection and stream only completed NPZ artifacts") {
      ZIO.scoped {for
        dir <- temp
        f <- fixture(dir)
        (jobs,cache,ar,archive,d)=f
        s <- Unifications.make(jobs,archive,ar,cache,dir,dir.resolve("state.sqlite"),r=>output(dir,r))
        api=new UnificationApi(s)
        accepted <- api.routes.runZIO(Request.post("http://localhost/api/image-unifications",Body.fromString(selection(d).toJson)))
        body <- accepted.body.asString
        job <- ZIO.fromEither(body.fromJson[UnificationJob]).mapError(new Exception(_))
        _ <- terminal(s,job.id)
        response <- api.routes.runZIO(Request.get(s"http://localhost/api/image-unifications/${job.id}/artifact"))
        bytes <- response.body.asChunk
      yield assertTrue(accepted.status==Status.Accepted,response.status==Status.Ok,bytes.take(2).toList==List[Byte](80,75)) }
    }
  ).provideLayer(Client.default) @@ TestAspect.withLiveClock @@ TestAspect.timeout(30.seconds)
