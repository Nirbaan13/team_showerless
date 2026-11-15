package spaceapps.processing

import spaceapps.processing.service.model.UnificationRequest
import spaceapps.processing.service.Unifications
import spaceapps.processing.repository.UnificationRepository

import zio.*
import zio.json.*
import zio.json.ast.Json
import zio.test.*
import java.nio.file.Files
import spaceapps.infra.service.FileCache

object UnificationSpec extends ZIOSpecDefault:
  private def parse(s:String)=s.fromJson[Json].toOption.get
  private val request=parse("""{"inputs":[{"kind":"archive_asset","id":"known"}],"grid":{"kind":"pixel","width":8,"height":8}}""")
  private def temp=ZIO.acquireRelease(ZIO.attemptBlocking(Files.createTempDirectory("unification-spec")))(p=>ZIO.attemptBlocking {
    val stream=Files.walk(p)
    try stream.sorted(java.util.Comparator.reverseOrder()).forEach(Files.deleteIfExists(_)) finally stream.close()
  }.orDie)
  def spec=suite("unification")(
    test("strict nested request rejects unknown fields, wrong integer types and arbitrary paths") {
      val bad=List(
        """{"inputs":[{"kind":"archive_asset","id":"known","path":"/etc/passwd"}],"grid":{"kind":"pixel","width":8,"height":8}}""",
        """{"inputs":[{"kind":"native_chunk","id":"known"}],"grid":{"kind":"pixel","width":8,"height":8}}""",
        """{"inputs":[{"kind":"archive_asset","id":"known"}],"grid":{"kind":"pixel","width":8.5,"height":8}}""",
        """{"inputs":[{"kind":"archive_asset","id":"known"}],"grid":{"kind":"pixel","width":8,"height":8,"rotation":0}}""")
      assertTrue(UnificationRequest.parse(request).isRight,bad.forall(s=>UnificationRequest.parse(parse(s)).isLeft))
    },
    test("physical identity remains unknown without provider-qualified exposure metadata") {
      val eso=Unifications.physicalIdentity("eso","science",Map("obs_id"->"exposure-7"))
      val otherCollection=Unifications.physicalIdentity("eso","different",Map("obs_id"->"exposure-7"))
      val native=Unifications.physicalIdentity("irsa-spherex","",Map("OBSID"->"exposure-7","detector_array"->"2"))
      val unknown=Unifications.physicalIdentity("irsa-spherex","",Map("frame_id"->"product-7","detector_array"->"2"))
      val foreign=Unifications.physicalIdentity("unqualified","science",Map("obs_id"->"exposure-7"))
      assertTrue(eso.contains("[\"science\",\"exposure-7\"]"),eso!=otherCollection,native.contains("exposure-7:D2"),unknown.isEmpty,foreign.isEmpty)
    },
    test("integral decimal selections are canonical integers in the private worker request") {
      val parsed=UnificationRequest.parse(parse("""{"inputs":[{"kind":"archive_asset","id":"known","image_hdu":2.0,"plane_indices":[1.0]}],"grid":{"kind":"pixel","width":8.0,"height":2.0}}""")).toOption.get
      val grid=parsed.grid.asInstanceOf[Json.Obj].fields.toMap
      val width=grid("width").asInstanceOf[Json.Num].value
      val hdu=parsed.inputs.head.imageHdu.asInstanceOf[Json.Num].value
      val plane=parsed.inputs.head.planeIndices.asInstanceOf[Json.Arr].elements.head.asInstanceOf[Json.Num].value
      assertTrue(width.scale==0,hdu.scale==0,plane.scale==0,parsed.grid.toJson.contains("\"height\":2"))
    },
    test("SQLite admission bounds active jobs and restart persists interrupted failure") {
      ZIO.scoped { for
        dir <- temp
        repo <- UnificationRepository.open(dir.resolve("state.sqlite"))
        first <- repo.accept(request,1)
        rejected <- repo.accept(request,1).either
        claimed <- repo.claim
        reopened <- UnificationRepository.open(dir.resolve("state.sqlite"))
        interrupted <- reopened.recover
        recovered <- reopened.get(first.id)
        next <- reopened.claim
      yield assertTrue(first.status=="queued",rejected.isLeft,claimed.exists(_.job.status=="running"),interrupted==List(first.id),recovered.status=="failed",recovered.error.exists(_.code=="interrupted"),next.isEmpty) }
    },
    test("cache owns and evicts only canonical final unification outputs") {
      ZIO.scoped { for
        dir <- temp
        cache <- FileCache.open(dir,dir.resolve("state.sqlite"),100,60,0)
        id="12345678-1234-1234-1234-123456789abc"
        finalPath=dir.resolve(s"unifications/$id/dataset.npz")
        unrelated=dir.resolve(s"unifications/$id/output/user.npz")
        _ <- cache.publish(finalPath)(p=>ZIO.attemptBlocking(Files.write(p,Array.fill[Byte](60)(1))).unit)
        _ <- ZIO.attemptBlocking {Files.createDirectories(unrelated.getParent);Files.write(unrelated,Array[Byte](2))}
        raw=dir.resolve("raw").resolve("a"*64+".fits")
        _ <- cache.publish(raw)(p=>ZIO.attemptBlocking(Files.write(p,Array.fill[Byte](20)(2))).unit)
        disk <- ZIO.attemptBlocking(List(finalPath,raw,unrelated).map(Files.exists(_)))
      yield assertTrue(disk==List(false,true,true)) }
    }
  ) @@ TestAspect.withLiveClock @@ TestAspect.timeout(30.seconds)
