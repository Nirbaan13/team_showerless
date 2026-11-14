package spaceapps.archive
import spaceapps.archive.protocol.*
import zio.test.*
object VoProtocolSpec extends ZIOSpecDefault:
  def fixture(name: String): Array[Byte] =
    val in=getClass.getResourceAsStream("/archive/"+name)
    try in.readAllBytes() finally in.close()
  def spec=suite("VO protocols")(
    test("real ESO and CADC trailing OVERFLOW retain records and truncation") {
      val eso=VOTableCodec.decode(fixture("eso-region-overflow.xml"))
      val cadc=VOTableCodec.decode(fixture("cadc-region-overflow.xml"))
      assertTrue(eso.rows.size==3,cadc.rows.size==3,eso.completeness==Completeness.truncated,cadc.completeness==Completeness.truncated)
    },
    test("maintenance and protocol ERROR never become empty success") {
      assertTrue(scala.util.Try(VOTableCodec.decode("<html>Maintenance</html>".getBytes)).isFailure,
        scala.util.Try(VOTableCodec.decode("<VOTABLE><RESOURCE><INFO name='QUERY_STATUS' value='ERROR'>bad</INFO></RESOURCE></VOTABLE>".getBytes)).isFailure)
    },
    test("DataLink selects science and preserves exact SODA dataset IDs") {
      val eso=DataLinkResolver.decode(fixture("eso-links-1.xml"))
      val cadc=DataLinkResolver.decode(fixture("cadc-neossat-links.xml"))
      assertTrue(eso.links.exists(_.semantic=="#this"),eso.links.exists(_.semantic=="#auxiliary"),
        eso.services.exists(_.dataset_id.startsWith("ivo://eso.org/")),cadc.services.exists(_.dataset_id.startsWith("cadc:NEOSSAT/")),
        cadc.links.find(_.semantic=="#this").exists(!_.requires_auth))
    },
    test("image footprint query uses INTERSECTS and UTC overlap") {
      val q=ArchiveQuery(Circle(210.8,54.35,0.1),List("eso"),time_start_utc=Some("2020-01-01T00:00:00Z"),time_end_utc=Some("2021-01-01T00:00:00Z"))
      val adql=TapClient.obsQuery(q)
      assertTrue(adql.contains("INTERSECTS(s_region,CIRCLE('ICRS',210.8,54.35,0.1))=1"),adql.contains("t_max >"),adql.contains("t_min <"),!adql.contains("TOP"))
    }
  )
