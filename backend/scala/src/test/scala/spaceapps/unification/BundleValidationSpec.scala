package spaceapps.unification
import zio.*
import zio.test.*
import java.nio.file.{Files,Path}
import java.util.zip.{ZipEntry,ZipOutputStream}
import scala.util.Try

private[unification] object BundleFixture:
  def npy(dtype:String,shape:List[Int],bytes:Option[Array[Byte]]=None):Array[Byte]=
    val tuple=shape.mkString(", ")+(if shape.size==1 then "," else "")
    val base=s"{'descr': '$dtype', 'fortran_order': False, 'shape': ($tuple), }"
    val header=base+" "*((16-(10+base.length+1)%16)%16)+"\n"
    val item=dtype.drop(2).toInt*(if dtype(1)=='U' then 4 else 1)
    Array[Byte](0x93.toByte,78,85,77,80,89,1,0,(header.length & 255).toByte,(header.length >> 8).toByte)++header.getBytes(java.nio.charset.StandardCharsets.US_ASCII)++bytes.getOrElse(Array.fill[Byte](shape.product*item)(0))
  def members:Map[String,Array[Byte]]=withFrames(1)
  def withFrames(n:Int):Map[String,Array[Byte]]=
    val images=List("images","tensor","footprint","variance").map(_->npy("<f4",List(n,2,2)))
    val masks=List("valid_mask","variance_valid_mask","outlier","bloom").map(_->npy("|b1",List(n,2,2)))
    (images++masks++List("times"->npy("<f8",List(n)),"time_known_mask"->npy("|b1",List(n)),"frame_ids"->npy("<U256",List(n)),"observation_ids"->npy("<U650",List(n)),"dates_utc"->npy("<U64",List(n)),"manifest"->npy("|u1",List(2),Some("{}".getBytes)),"schema_version"->npy("<i2",Nil,Some(Array[Byte](1,0))))).toMap
  def write(p:Path,members:Map[String,Array[Byte]]):Unit=
    val zip=new ZipOutputStream(Files.newOutputStream(p))
    try members.foreach { (name,bytes)=>zip.putNextEntry(new ZipEntry(name+".npy"));zip.write(bytes);zip.closeEntry() } finally zip.close()

object BundleValidationSpec extends ZIOSpecDefault:
  def spec=suite("NPZ publication validation")(
    test("ambiguous NPY dictionary headers cannot disguise a different array dtype") {
      ZIO.acquireReleaseWith(ZIO.attemptBlocking(Files.createTempFile("unification-ambiguous-header",".npz")))(p=>ZIO.attemptBlocking(Files.deleteIfExists(p)).orDie) { p=>ZIO.attemptBlocking {
        val bytes=BundleFixture.npy("<f4",List(1,2,2))
        val length=(bytes(8) & 255)+((bytes(9) & 255)<<8)
        val header=new String(bytes.slice(10,10+length),java.nio.charset.StandardCharsets.US_ASCII).replace("}","'descr': '<i4', }")
        val malformed=bytes.take(8)++Array[Byte]((header.length & 255).toByte,(header.length>>8).toByte)++header.getBytes(java.nio.charset.StandardCharsets.US_ASCII)++bytes.drop(10+length)
        BundleFixture.write(p,BundleFixture.members.updated("images",malformed))
        val rejected=Try(BundleValidation.validate(p,1,2,2)).isFailure
        assertTrue(rejected)
      }}
    },
    test("requires complete typed bundle and exact frame shapes before publication") {
      ZIO.acquireReleaseWith(ZIO.attemptBlocking(Files.createTempFile("unification-bundle",".npz")))(p=>ZIO.attemptBlocking(Files.deleteIfExists(p)).orDie) { p=>ZIO.attemptBlocking {
        val bad=List(BundleFixture.members-"outlier",BundleFixture.members.updated("valid_mask",BundleFixture.npy("<f4",List(1,2,2))),BundleFixture.members.updated("images",BundleFixture.npy("<f4",List(2,2,2))),BundleFixture.members.updated("times",BundleFixture.npy("<f8",List(2))))
        val rejected=bad.map { entries=>BundleFixture.write(p,entries);Try(BundleValidation.validate(p,1,2,2)).isFailure }
        BundleFixture.write(p,BundleFixture.members)
        val valid=Try(BundleValidation.validate(p,1,2,2)).isSuccess
        assertTrue(valid,rejected==List(true,true,true,true))
      }}
    }
  )
