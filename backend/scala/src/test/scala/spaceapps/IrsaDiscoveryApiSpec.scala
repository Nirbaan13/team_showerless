package spaceapps
import spaceapps.irsa.controller.{IrsaDiscoveryApi,IrsaDiscoveryRequest}
import spaceapps.irsa.model.ApiError
import zio.test.*
object IrsaDiscoveryApiSpec extends ZIOSpecDefault:
  def spec=suite("IrsaDiscoveryApiSpec")(
    test("gateway preserves detector and UTC time constraints") {
      val r=IrsaDiscoveryRequest(250,5.79,0.025,Some(6),Some("2025-01-01T00:00:00Z"),Some("2025-12-31T00:00:00Z"))
      val q=IrsaDiscoveryApi.query(r)
      assertTrue(q.position=="CIRCLE 250.0 5.79 0.025",q.detector.contains(6),q.after==r.observed_after,q.before==r.observed_before)
    },
    test("invalid coordinates, detector, radius and backwards time fail before discovery") {
      val bad=List(IrsaDiscoveryRequest(360,0,0.01),IrsaDiscoveryRequest(1,91,0.01),IrsaDiscoveryRequest(1,1,0),
        IrsaDiscoveryRequest(1,1,Double.NaN),IrsaDiscoveryRequest(1,1,0.01,Some(7)),
        IrsaDiscoveryRequest(1,1,0.01,None,Some("2026-01-01T00:00:00Z"),Some("2025-01-01T00:00:00Z")))
      assertTrue(bad.forall(r=>scala.util.Try(IrsaDiscoveryApi.query(r)).failed.toOption.exists{case e:ApiError=>e.code=="invalid_request";case _=>false}))
    }
  )
