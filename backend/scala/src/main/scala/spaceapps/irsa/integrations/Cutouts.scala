package spaceapps.irsa.integrations

import spaceapps.irsa.model.{ApiError,Query}
import java.net.{URI,URLEncoder}
import java.nio.charset.StandardCharsets.UTF_8

/** Requests an enclosing native-axis subset, without rotating or resampling pixels. */
object Cutouts:
  private case class V(x:Double,y:Double,z:Double):
    def +(other:V):V=V(x+other.x,y+other.y,z+other.z)
    def dot(other:V):Double=x*other.x+y*other.y+z*other.z
    def norm:Double=math.sqrt(dot(this))
    def angle(other:V):Double=
      val cross=V(y*other.z-z*other.y,z*other.x-x*other.z,x*other.y-y*other.x)
      math.atan2(cross.norm,dot(other))
  private def vector(ra:Double,dec:Double):V=
    val a=math.toRadians(ra);val d=math.toRadians(dec)
    V(math.cos(d)*math.cos(a),math.cos(d)*math.sin(a),math.sin(d))
  private def invalid():Nothing=throw ApiError("archive_cutout_geometry","The query cannot be represented by a bounded IRSA spatial cutout")
  private def number(value:Double):String=
    BigDecimal(if math.abs(value)<1e-10 then 0d else value).setScale(10,BigDecimal.RoundingMode.HALF_UP).bigDecimal.stripTrailingZeros.toPlainString
  private def geometry(query:Query):(Double,Double,Double)=
    val tokens=query.position.trim.split("\\s+").toList
    val values=tokens.drop(1).map(_.toDoubleOption.filter(_.isFinite).getOrElse(invalid()))
    val (center,points,radius)=tokens.headOption match
      case Some("CIRCLE") if values.size==3 && values(2)>0 && values(2)<90=>
        (vector(values(0),values(1)),List.empty[V],Some(math.toRadians(values(2))))
      case Some("RANGE") if values.size==4=>
        val List(lo,hi,bottom,top)=values: @unchecked
        val corners=List(vector(lo,bottom),vector(hi,bottom),vector(hi,top),vector(lo,top))
        (vector((lo+hi)/2,(bottom+top)/2),corners,None)
      case Some("POLYGON") if values.size>=6 && values.size%2==0=>
        val vertices=values.grouped(2).map(p=>vector(p(0),p(1))).toList
        (vertices.reduce(_+_),vertices,None)
      case _=>invalid()
    if center.norm<1e-10 then invalid()
    val r=radius.getOrElse(points.map(center.angle).max)
    // A cap below a hemisphere contains the convex polygon's great-circle edges too.
    if r>=math.Pi/2 then invalid()
    val ra=if math.hypot(center.x,center.y)<1e-12*center.norm then 0d else (math.toDegrees(math.atan2(center.y,center.x))+360)%360
    val dec=math.toDegrees(math.atan2(center.z,math.hypot(center.x,center.y)))
    // One nominal SPHEREx source pixel per edge protects native-grid rounding.
    val diameter=math.toDegrees(2*r)+2*6.15/3600
    (ra,dec,diameter)
  def url(parent:String,query:Query):String=
    val uri=URI.create(parent)
    if !Option(uri.getPath).exists(_.startsWith("/ibe/data/spherex/")) || uri.getRawQuery!=null || uri.getFragment!=null then
      throw ApiError("archive_cutout_unavailable","Spatial subsets require an unmodified IRSA IBE spectral-image URL")
    val (ra,dec,size)=geometry(query)
    parent+"?center="+URLEncoder.encode(s"${number(ra)},${number(dec)}deg",UTF_8)+"&size="+number(size)+"deg"
