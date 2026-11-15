package spaceapps

import spaceapps.irsa.model.*
import spaceapps.irsa.integrations.Cutouts
import zio.json.ast.Json
import zio.test.*
import java.net.{URI,URLDecoder}
import java.nio.charset.StandardCharsets.UTF_8

object IrsaCutoutsSpec extends ZIOSpecDefault:
  private val url="https://irsa.ipac.caltech.edu/ibe/data/spherex/qr3/level2/native.fits"
  private def parameters(value:String):Map[String,String]=URI.create(value).getRawQuery.split("&").map { p=>
    val pair=p.split("=",2);pair(0)->URLDecoder.decode(pair(1),UTF_8)
  }.toMap
  def spec=suite("IRSA spatial cutouts")(
    test("rotated image axes receive a bounding square covering every requested rectangle corner") {
      val q=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2","width_arcmin"->"3","height_arcmin"->"5")).toOption.get
      val p=parameters(Cutouts.url(url,q))
      val size=p("size").stripSuffix("deg").toDouble*60
      assertTrue(p("center")=="1,2deg",size>math.sqrt(34),size<6.2)
    },
    test("range and polygons across RA zero get finite local enclosing cutouts") {
      val range=Query.fromParameters("range",Map("right_ascension_min_deg"->"1","right_ascension_max_deg"->"1.1","declination_min_deg"->"2","declination_max_deg"->"2.1")).toOption.get
      val polygon=Query.fromParameters("polygon",Map("verices_degrees"->"359.95,-0.05,0.05,-0.05,0.05,0.05,359.95,0.05")).toOption.get
      val r=parameters(Cutouts.url(url,range));val p=parameters(Cutouts.url(url,polygon))
      assertTrue(r("size").stripSuffix("deg").toDouble<0.2,p("center")=="0,0deg",p("size").stripSuffix("deg").toDouble<0.2)
    },
    test("a polar field has a finite request without a fabricated reprojection") {
      val q=Query.fromParameters("default",Map("right_ascension_deg"->"359.999","declination_deg"->"90")).toOption.get
      val value=Cutouts.url(url,q)
      assertTrue(!value.contains("NaN"),parameters(value)("size").stripSuffix("deg").toDouble<0.1)
    },
    test("different region dimensions cannot share a retrieval URL") {
      val q=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get
      val larger=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2","width_arcmin"->"5")).toOption.get
      assertTrue(Cutouts.url(url,q)!=Cutouts.url(url,larger),!Cutouts.url(url,q).contains("gzip=true"))
    },
    test("non-IBE paths and pre-existing query strings cannot become fake cutout requests") {
      val q=Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get
      val unsupported=List("https://nasa-irsa-spherex.s3.amazonaws.com/dr1/native.fits",url+"?token=anything")
      assertTrue(unsupported.forall(u=>scala.util.Try(Cutouts.url(u,q)).failed.toOption.exists {
        case e:ApiError=>e.code=="archive_cutout_unavailable"
        case _=>false
      }))
    }
  )
