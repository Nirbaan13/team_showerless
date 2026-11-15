package spaceapps.domain

import zio.json.*
import zio.json.ast.Json
import scala.util.Try

final case class AnalysisOptions(min_snr:Double=4, min_speed_arcsec_per_hour:Double=3.075,
  max_speed_arcsec_per_hour:Double=369,mask_policy:String="motion",max_candidates:Int=100,
  max_peaks:Int=100,pixel_scale_arcsec:Double=6.15,min_epochs:Int=3) derives JsonCodec:
  def validate:Either[ApiError,AnalysisOptions]=
    if !List(min_snr,min_speed_arcsec_per_hour,max_speed_arcsec_per_hour,pixel_scale_arcsec).forall(_.isFinite) ||
      min_snr<=0 || min_snr>100 || min_speed_arcsec_per_hour<=0 || max_speed_arcsec_per_hour<min_speed_arcsec_per_hour || max_speed_arcsec_per_hour>100000 ||
      !Set("motion","science").contains(mask_policy) || max_candidates<1 || max_candidates>100 || max_peaks<1 || max_peaks>100 ||
      pixel_scale_arcsec<0.1 || pixel_scale_arcsec>60 || min_epochs<3 || min_epochs>32 then
      Left(ApiError("invalid_request","Analysis options exceed supported limits"))
    else Right(this)
final case class AnalysisRequest(download_id:Option[String]=None,preset:Option[String]=None,options:AnalysisOptions=AnalysisOptions(),frame_ids:Option[List[String]]=None) derives JsonCodec:
  def validate:Either[ApiError,AnalysisRequest]=
    if download_id.isDefined==preset.isDefined || download_id.exists(s=>s.isEmpty || s.length>128) || preset.exists(s=> !AnalysisPreset.ids.contains(s)) then
      Left(ApiError("invalid_request","Supply exactly one existing download_id or a registered preset"))
    else if frame_ids.exists(ids=>download_id.isEmpty || ids.size<3 || ids.size>32 || ids.distinct.size!=ids.size || ids.exists(id=>id.isEmpty || id.length>256)) then
      Left(ApiError("invalid_request","frame_ids requires a download and 3 to 32 distinct native frame IDs"))
    else options.validate.map(_=>this)
object AnalysisRequest:
  def parse(body:String):Either[ApiError,AnalysisRequest]=
    def validObject(j:Json,allowed:Set[String]):Boolean=j match
      case Json.Obj(fs)=>fs.map(_._1).distinct.size==fs.size && fs.forall((k,_)=>allowed.contains(k))
      case _=>false
    for
      ast<-body.fromJson[Json].left.map(_=>ApiError("invalid_request","Expected a JSON analysis request"))
      _<-Either.cond(validObject(ast,Set("download_id","preset","options","frame_ids")) && (ast match
        case Json.Obj(fs)=>fs.find(_._1=="options").forall((_,v)=>validObject(v,Set("min_snr","min_speed_arcsec_per_hour","max_speed_arcsec_per_hour","mask_policy","max_candidates","max_peaks","pixel_scale_arcsec","min_epochs")))
        case _=>false),(),ApiError("invalid_request","Unknown or duplicate analysis request properties"))
      req<-body.fromJson[AnalysisRequest].left.map(_=>ApiError("invalid_request","Analysis request properties have invalid types"))
      out<-req.validate
    yield out
final case class Analysis(id:String,status:String,download_id:Option[String],status_url:String,events_url:String,
  result:Option[Json]=None,error:Option[ApiError]=None) derives JsonCodec:
  def terminal:Boolean=status=="completed" || status=="failed"
final case class AnalysisRecord(analysis:Analysis,request:AnalysisRequest,key:String,model_hash:Option[String]=None,model_id:Option[String]=None) derives JsonCodec
final case class AnalysisPreset(id:String,title:String,description:String,source_url:String) derives JsonCodec
object AnalysisPreset:
  val ids=Set("comet-d6","comet-d2","vesta-d6","vesta-d3")
  val all=List("comet-d6","comet-d2","vesta-d6","vesta-d3").map(id=>AnalysisPreset(id,id,
    "Archived SPHEREx real observations, selected development/recovery case; not a representative precision benchmark.","https://irsa.ipac.caltech.edu/Missions/spherex.html"))
final case class AnalysisRegion(right_ascension_deg:Double,declination_deg:Double,width_arcmin:Double,height_arcmin:Double) derives JsonCodec
object AnalysisRegion:
  def fromQuery(q:Query,o:AnalysisOptions):Either[ApiError,AnalysisRegion]=Try {
    val f=q.document.asInstanceOf[Json.Obj].fields.toMap
    def n(k:String)=f(k).asInstanceOf[Json.Num].value.doubleValue
    // Width/height describe linear TAN-plane extents consumed by the Python WCS grid.
    val region=if f.contains("right_ascension_deg") then
      AnalysisRegion(n("right_ascension_deg"),n("declination_deg"),math.toDegrees(math.tan(math.toRadians(n("width_arcmin")/120)))*120,math.toDegrees(math.tan(math.toRadians(n("height_arcmin")/120)))*120)
    else
      val points=if f.contains("verices_degrees") then f("verices_degrees").asInstanceOf[Json.Arr].elements.map(_.asInstanceOf[Json.Num].value.doubleValue).toList.grouped(2).map(p=>(p(0),p(1))).toList
      else List((n("right_ascension_min_deg"),n("declination_min_deg")),(n("right_ascension_max_deg"),n("declination_min_deg")),(n("right_ascension_max_deg"),n("declination_max_deg")),(n("right_ascension_min_deg"),n("declination_max_deg")))
      val anchor=points.head._1
      val unwrapped=points.map((ra,dec)=>(anchor+((ra-anchor+540)%360-180),dec))
      val ra=(unwrapped.map(_._1).min+unwrapped.map(_._1).max)/2
      val dec=(points.map(_._2).min+points.map(_._2).max)/2
      val projected=unwrapped.map { (a,d)=>
        val delta=math.toRadians(a-ra);val lat=math.toRadians(d);val center=math.toRadians(dec)
        val den=math.sin(center)*math.sin(lat)+math.cos(center)*math.cos(lat)*math.cos(delta)
        if den<=0 then throw ApiError("analysis_too_large","Requested region does not fit a supported analysis grid")
        (math.cos(lat)*math.sin(delta)/den,(math.cos(center)*math.sin(lat)-math.sin(center)*math.cos(lat)*math.cos(delta))/den)
      }
      AnalysisRegion((ra+360)%360,dec,math.toDegrees(projected.map(p=>math.abs(p._1)).max)*120,math.toDegrees(projected.map(p=>math.abs(p._2)).max)*120)
    if math.ceil(region.width_arcmin*60/o.pixel_scale_arcsec)>512 || math.ceil(region.height_arcmin*60/o.pixel_scale_arcsec)>512 then
      throw ApiError("analysis_too_large","Requested bounds exceed the 512 by 512 analysis grid; reduce the region or increase pixel_scale_arcsec")
    region
  }.toEither.left.map(ApiError.from)
