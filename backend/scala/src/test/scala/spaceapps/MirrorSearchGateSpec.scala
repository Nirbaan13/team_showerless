package spaceapps
import spaceapps.irsa.service.MirrorSearchGate
import spaceapps.irsa.model.ApiError
import zio.*
import zio.test.*
object MirrorSearchGateSpec extends ZIOSpecDefault:
  def spec=suite("MirrorSearchGateSpec")(
    test("at most two searches run and at most four are admitted") {
      ZIO.scoped { for
        gate<-MirrorSearchGate.make
        started<-Ref.make(0)
        release<-Promise.make[Nothing,Unit]
        fibers<-ZIO.foreach(1 to 4)(_=>gate.run(started.update(_+1)*>release.await).forkScoped)
        _<-gate.admitted.repeatUntil(_==4)
        _<-started.get.repeatUntil(_==2)
        rejected<-gate.run(ZIO.unit).either
        count<-started.get
        _<-release.succeed(())
        _<-ZIO.foreachDiscard(fibers)(_.join)
        after<-gate.admitted
      yield assertTrue(count==2,after==0,rejected.left.toOption.exists{case e:ApiError=>e.code=="archive_mirror_capacity";case _=>false}) }
    },
    test("a cancelled search releases admission for the next caller") {
      ZIO.scoped { for
        gate<-MirrorSearchGate.make
        fiber<-gate.run(ZIO.never).forkScoped
        _<-gate.admitted.repeatUntil(_==1)
        _<-fiber.interrupt
        value<-gate.run(ZIO.succeed(42))
        count<-gate.admitted
      yield assertTrue(value==42,count==0) }
    }
  )
