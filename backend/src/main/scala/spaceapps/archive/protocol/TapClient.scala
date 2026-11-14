package spaceapps.archive.protocol
import spaceapps.archive.*
import zio.*
import java.time.Instant
final class TapClient(transport: ArchiveTransport):
  def query(endpoint: String,policy: OriginPolicy,adql: String,limit: Int): IO[ArchiveFailure,VoTable] =
    transport.metadata(ArchiveTransport.params(endpoint,List("REQUEST"->"doQuery","LANG"->"ADQL","FORMAT"->"votable","MAXREC"->limit.toString,"QUERY"->adql)),policy).flatMap(b=>ZIO.attempt(VOTableCodec.decode(b)).mapError(ArchiveFailure.from))
object TapClient:
  def mjd(value: String): Double =
    val t=Instant.parse(value);40587d+t.getEpochSecond.toDouble/86400d+t.getNano.toDouble/86400e9
  def obsQuery(q: ArchiveQuery): String =
    val c=q.region
    val kinds=q.product_kinds.filter(k=>Set(ProductKind.image,ProductKind.cube,ProductKind.spectrum)(k)).map(k=>s"'$k'")
    val time=q.time_start_utc.map(t=>s"t_max > ${mjd(t)}").toList++q.time_end_utc.map(t=>s"t_min < ${mjd(t)}")
    s"SELECT * FROM ivoa.ObsCore WHERE dataproduct_type IN (${kinds.mkString(",")}) AND INTERSECTS(s_region,CIRCLE('ICRS',${c.ra_degrees},${c.dec_degrees},${c.radius_degrees}))=1"+time.map(" AND "+_).mkString
