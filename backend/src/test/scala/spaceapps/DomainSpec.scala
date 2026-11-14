package spaceapps

import zio.*
import zio.json.*
import zio.json.ast.Json
import zio.test.*

object DomainSpec extends ZIOSpecDefault:
  def spec = suite("Sky request validation")(
    test("JSON numbers cannot be supplied as strings or duplicate fields") {
      assertTrue(
        Query.fromJson("""{"right_ascension_deg":"1","declination_deg":2}""").isLeft,
        Query.fromJson("""{"right_ascension_deg":1,"declination_deg":2,"detector_array":"1"}""").isLeft,
        Query.fromJson("""{"right_ascension_deg":1,"right_ascension_deg":2,"declination_deg":2}""").isLeft)
    },
    test("range is forwarded in ICRS degrees") {
      val result = Query.fromParameters("range", Map("right_ascension_min_deg" -> "210.8", "right_ascension_max_deg" -> "210.81", "declination_min_deg" -> "54.34", "declination_max_deg" -> "54.35"))
      assertTrue(result.exists(_.position.startsWith("RANGE 210.8 210.81 54.34 54.35")))
    },
    test("public polygon spelling is preserved and convexity is enforced") {
      val valid = Query.fromParameters("polygon", Map("verices_degrees" -> "359,10,1,10,1,11,359,11"))
      val crossed = Query.fromParameters("polygon", Map("verices_degrees" -> "0,0,1,1,0,1,1,0"))
      assertTrue(valid.isRight, crossed.isLeft)
    },
    test("non-finite coordinates, invalid detectors and inverted times are rejected") {
      val base = Map("right_ascension_deg" -> "1", "declination_deg" -> "2")
      assertTrue(Query.fromParameters("default", base.updated("right_ascension_deg", "NaN")).isLeft,
        Query.fromParameters("default", base.updated("detector_array", "7")).isLeft,
        Query.fromJson("""{"right_ascension_deg":1,"declination_deg":2,"observed_after":"2026-02-01T00:00:00Z","observed_before":"2026-01-01T00:00:00Z"}""").isLeft)
    },
    test("center query wraps RA and supports a polar center without resampling pixels") {
      val result = Query.fromParameters("default", Map("right_ascension_deg" -> "359.999", "declination_deg" -> "90"))
      assertTrue(result.exists(q => q.position.startsWith("POLYGON ") && !q.position.contains("NaN")))
    },
    test("default filter representations deduplicate") {
      val a=Query.fromParameters("default",Map("right_ascension_deg"->"1", "declination_deg"->"2"))
      val b=Query.fromParameters("default",Map("right_ascension_deg"->"1.0", "declination_deg"->"2.0", "detector_array"->"all", "width_arcmin"->"3"))
      assertTrue(a.map(_.key("default",None)) == b.map(_.key("default",None)))
    }
  )
