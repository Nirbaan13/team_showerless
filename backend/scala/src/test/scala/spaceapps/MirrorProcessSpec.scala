package spaceapps
import spaceapps.irsa.integrations.MirrorProcess
import spaceapps.irsa.model.ApiError
import zio.*
import zio.json.ast.Json
import zio.test.*
import java.nio.file.Files
object MirrorProcessSpec extends ZIOSpecDefault:
  private def script[A](body:String)(use:MirrorProcess=>Task[A]):Task[A]=ZIO.scoped {for
    dir<-ZIO.acquireRelease(ZIO.attempt(Files.createTempDirectory("mirror-process-spec")))(p=>ZIO.attempt{val s=Files.walk(p);try s.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally s.close()}.ignore)
    file=dir.resolve("helper.py")
    _<-ZIO.attempt(Files.writeString(file,body))
    result<-use(new MirrorProcess("python3",file,dir.resolve("index.sqlite"),"https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/","qr2"))
  yield result}
  def spec=suite("MirrorProcessSpec")(
    test("JSON stdin survives the subprocess boundary and configured arguments remain literal") {
      script("import sys,json\nx=json.load(sys.stdin)\nprint(json.dumps({'received':x,'argv':sys.argv[1:]}))") { p=>for
        result<-p.run(List("search"),Some("{\"position\":\"CIRCLE 250 5.79 0.025\"}"))
      yield assertTrue(result.toString.contains("CIRCLE 250 5.79 0.025"),result.toString.contains("search")) }
    },
    test("mirror warming errors preserve their machine-readable code") {
      script("import json,sys\nprint(json.dumps({'error':{'code':'archive_mirror_index_warming','message':'indexing'}}))\nsys.exit(2)") { p=>p.run(List("search")).either.map(r=>assertTrue(r.left.toOption.exists{case e:ApiError=>e.code=="archive_mirror_index_warming";case _=>false})) }
    },
    test("a crashed helper cannot become a successful empty observation list") {
      script("import sys\nsys.exit(1)") { p=>p.run(List("search")).either.map(r=>assertTrue(r.isLeft)) }
    }
  ) @@ TestAspect.withLiveClock @@ TestAspect.timeout(20.seconds)
