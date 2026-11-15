package spaceapps

import spaceapps.irsa.integrations.MirrorTransfer
import spaceapps.irsa.model.*
import spaceapps.irsa.service.Archive
import java.nio.file.{Files,Path}
import zio.*
import zio.json.ast.Json
import zio.test.*

object MirrorTransferSpec extends ZIOSpecDefault:
  private val parent="https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/dr1/level2/period/version/1/native.fits"
  private val selected=ArchiveImage(Observation("native","2025-05-06T00:00:00Z",1,"DR1",
    header_metadata=Map("discovery_source"->Json.Str("s3_mirror"))),
    "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/period/version/1/native.fits?center=10%2C20deg&size=0.05deg",Some(parent))
  private val unavailable=new Archive:
    def search(query:Query)=ZIO.succeed(Nil)
    def fetch(image:ArchiveImage,path:Path)=ZIO.fail(ApiError("test_primary_called","Primary must remain unused"))
  private def helper[A](body:String)(run:(MirrorTransfer,Path)=>Task[A]):Task[A]=ZIO.scoped {for
    dir<-ZIO.acquireRelease(ZIO.attempt(Files.createTempDirectory("mirror-cutout-spec")))(p=>ZIO.attempt{
      val paths=Files.walk(p)
      try paths.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally paths.close()
    }.ignore)
    file=dir.resolve("helper.py")
    _<-ZIO.attempt(Files.writeString(file,body))
    result<-run(new MirrorTransfer(unavailable,"python3",file),dir.resolve("result.fits"))
  yield result}
  def spec=suite("MirrorTransferSpec")(
    test("subset helper receives literal source and cutout arguments and writes validated FITS") {
      helper("""import argparse,json,pathlib
p=argparse.ArgumentParser()
p.add_argument('--source');p.add_argument('--cutout');p.add_argument('--output');p.add_argument('--max-bytes',type=int)
a=p.parse_args()
assert a.source=='"""+parent+"""'
assert 'center=10%2C20deg&size=0.05deg' in a.cutout
assert a.max_bytes==67108864
cards=['SIMPLE  =                    T','BITPIX  =                    8','NAXIS   =                    0','END']
pathlib.Path(a.output).write_bytes(''.join(c.ljust(80) for c in cards).ljust(2880).encode())
print(json.dumps({'ok':True}))
""") { (transfer,path)=>transfer.fetch(selected,path)*>ZIO.attempt(Files.size(path)).map(n=>assertTrue(n==2880)) }
    },
    test("structured S3 range failure survives boundary and partial output is removed") {
      helper("""import sys,json,pathlib
pathlib.Path(sys.argv[sys.argv.index('--output')+1]).write_bytes(b'partial')
print(json.dumps({'error':{'code':'archive_mirror_object_changed','message':'ETag changed'}}))
sys.exit(1)
""") { (transfer,path)=>for
        result<-transfer.fetch(selected,path).either
        present<-ZIO.attempt(Files.exists(path))
      yield assertTrue(!present,result.left.toOption.exists{case e:ApiError=>e.code=="archive_mirror_object_changed";case _=>false}) }
    },
    test("successful process without a FITS product cannot populate cache") {
      helper("import json\nprint(json.dumps({'ok':True}))") { (transfer,path)=>
        transfer.fetch(selected,path).either.map(result=>assertTrue(result.isLeft)) }
    },
    test("block-aligned SIMPLE prefix without a complete FITS header is rejected") {
      helper("""import sys,pathlib,json
pathlib.Path(sys.argv[sys.argv.index('--output')+1]).write_bytes(b'SIMPLE  =                    T'+b' '*2850)
print(json.dumps({'ok':True}))
""") { (transfer,path)=>for
        result<-transfer.fetch(selected,path).either
        present<-ZIO.attempt(Files.exists(path))
      yield assertTrue(!present,result.left.toOption.exists{case e:ApiError=>e.code=="archive_invalid_fits";case _=>false}) }
    },
    test("cancellation terminates the helper and removes its exact temporary product") {
      helper("""import sys,pathlib,time
p=pathlib.Path(sys.argv[sys.argv.index('--output')+1]+'.mirror-part')
p.write_bytes(b'partial')
time.sleep(30)
""") { (transfer,path)=>ZIO.scoped {for
        fiber<-transfer.fetch(selected,path).forkScoped
        temporary=Path.of(path.toString+".mirror-part")
        started<-(ZIO.attempt(Files.exists(temporary)) <* ZIO.sleep(10.millis)).repeatUntil(identity).timeout(3.seconds)
        _<-fiber.interrupt
        outputPresent<-ZIO.attempt(Files.exists(path))
        temporaryPresent<-ZIO.attempt(Files.exists(temporary))
      yield assertTrue(started.contains(true),!outputPresent,!temporaryPresent)} }
    }
  ) @@ TestAspect.withLiveClock @@ TestAspect.timeout(20.seconds)
