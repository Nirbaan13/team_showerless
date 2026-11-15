package spaceapps.irsa.service
import spaceapps.irsa.model.ApiError
import zio.*
/** Shared bounded admission for memory-heavy Python/Astropy search processes. */
final class MirrorSearchGate private(slots:Semaphore,count:Ref[Int]):
  private[spaceapps] def admitted:UIO[Int]=count.get
  def run[A](search:Task[A]):Task[A]=ZIO.uninterruptibleMask { restore=>
    count.modify(n=>if n>=4 then (false,n) else (true,n+1)).flatMap {
      case false=>ZIO.fail(ApiError("archive_mirror_capacity","Mirror search queue is full; retry later",true))
      case true=>restore(slots.withPermit(search).timeoutFail(ApiError("archive_mirror_timeout","Mirror search exceeded its bounded request budget",true))(8.seconds)).ensuring(count.update(_-1))
    }
  }
object MirrorSearchGate:
  def make:UIO[MirrorSearchGate]=for
    slots<-Semaphore.make(2)
    count<-Ref.make(0)
  yield new MirrorSearchGate(slots,count)
