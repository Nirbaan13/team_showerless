package spaceapps.downloads

import spaceapps.downloads.integrations.protocol.OriginPolicy
import zio.*
import zio.http.Client
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets.US_ASCII
import java.net.InetSocketAddress
import com.sun.net.httpserver.HttpServer
import java.util.concurrent.ConcurrentLinkedQueue

/** Analytic transport fixtures; the e022 header is real metadata, not acceptance pixels. */
object UnwiseFixtures:
  def cards(values:List[String]):Array[Byte]=
    val text=(values:+"END").map(_.padTo(80,' ')).mkString
    text.padTo(((text.length+2879)/2880)*2880,' ').getBytes(US_ASCII)
  def atlas(rows:List[(String,Double,Double,List[(Int,Int)])]):Array[Byte]=
    val primary=cards(List("SIMPLE  =                    T","BITPIX  =                    8","NAXIS   =                    0","EXTEND  =                    T"))
    val table=cards(List("XTENSION= 'BINTABLE'","BITPIX  =                    8","NAXIS   =                    2","NAXIS1  =                  459",s"NAXIS2  = ${rows.size}","PCOUNT  =                    0","GCOUNT  =                    1","TFIELDS =                    5",
      "TTYPE1  = 'COADD_ID'","TTYPE2  = 'RA'","TTYPE3  = 'DEC'","TTYPE4  = 'ROW'","TTYPE5  = 'EPOCH_BITMASK'",
      "TFORM1  = '8A'","TFORM2  = 'D'","TFORM3  = 'D'","TFORM4  = 'K'","TFORM5  = '427B'"))
    val data=ByteBuffer.allocate(((rows.size*459+2879)/2880)*2880)
    rows.zipWithIndex.foreach { case ((id,ra,dec,epochs),i)=>
      data.put(id.getBytes(US_ASCII));data.putDouble(ra);data.putDouble(dec);data.putLong(i.toLong)
      val mask=Array.fill[Byte](427)(0);epochs.foreach((epoch,bits)=>mask(epoch)=bits.toByte);data.put(mask)
    }
    primary++table++data.array
  val oneAtlas=atlas(List(("1342m076",134.237284,-7.572222,List(0->3,1->1,22->3,23->3))))
  def resourceHeader(name:String):Array[Byte]=
    val stream=getClass.getResourceAsStream("/archive/"+name)
    val text=try new String(stream.readAllBytes(),US_ASCII) finally stream.close()
    val raw=text.linesIterator.map(_.padTo(80,' ')).mkString
    raw.padTo(((raw.length+2879)/2880)*2880,' ').getBytes(US_ASCII)
  def header(epoch:Int=22,changes:Map[String,String]=Map.empty):Array[Byte]=
    val original=new String(resourceHeader("unwise-e022-header.txt"),US_ASCII)
    original.grouped(80).map { line=>
      val key=line.take(8).trim
      val value=changes.get(key).orElse(Option.when(key=="EPOCH")(epoch.toString))
      value.fold(line)(v=>s"${key.padTo(8,' ')}= $v".padTo(80,' '))
    }.mkString.getBytes(US_ASCII)
  final case class Fixture(base:String,policy:OriginPolicy,requests:ConcurrentLinkedQueue[(String,Option[String])])
  def server[A](atlasBytes:Array[Byte]=oneAtlas,headers:Map[Int,Array[Byte]]=Map(0->header(0,Map("MJDMIN"->"55224.1","MJDMAX"->"55225.2")),22->header()),rangeMode:String="normal")
    (use:Fixture=>ZIO[Client,Throwable,A]):ZIO[Client,Throwable,A]=ZIO.scoped {
      val requests=new ConcurrentLinkedQueue[(String,Option[String])]()
      for
        server <- ZIO.acquireRelease(ZIO.attempt {
          val s=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0)
          s.createContext("/",e=> {
            val path=e.getRequestURI.getPath
            val range=Option(e.getRequestHeaders.getFirst("Range"))
            requests.add(path->range)
            val epoch="/e([0-9]{3})/".r.findFirstMatchIn(path).map(_.group(1).toInt)
            val data=if path.endsWith("time_resolved_neo11-atlas.fits") then Some(atlasBytes) else epoch.flatMap(headers.get)
            if path=="/redirect" then
              e.getResponseHeaders.add("Location","/e022/a");e.sendResponseHeaders(307,-1)
            else data match
              case None=>e.sendResponseHeaders(404,-1)
              case Some(bytes)=>
                val ranged=range.nonEmpty
                val requested=range.flatMap("bytes=0-([0-9]+)".r.findFirstMatchIn).map(_.group(1).toInt+1).getOrElse(bytes.length)
                val payload=if ranged && rangeMode=="ignored" then bytes++Array.fill[Byte](65536)(0) else if ranged && rangeMode=="oversize" then bytes++Array.fill[Byte](requested)(0) else bytes.take(requested)
                if ranged && rangeMode!="ignored" then e.getResponseHeaders.add("Content-Range",s"bytes ${if rangeMode=="bad-range" then 1 else 0}-${if rangeMode=="oversize" then requested-1 else payload.length-1}/16784640")
                e.sendResponseHeaders(if ranged && rangeMode!="ignored" then 206 else 200,payload.length)
                e.getResponseBody.write(payload)
            e.close()
          });s.start();s
        })(s=>ZIO.succeed(s.stop(0)))
        base=s"http://127.0.0.1:${server.getAddress.getPort}"
        result <- use(Fixture(base,OriginPolicy(Set.empty,Set(base)),requests))
      yield result
    }
