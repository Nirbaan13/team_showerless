package spaceapps.processing.service.model

import spaceapps.infra.model.ApiError
import zio.json.*
import zio.json.ast.Json
import scala.util.Try

final case class UnificationInput(kind:String,id:String,downloadId:Option[String],imageHdu:Json,planeIndices:Json)
final case class UnificationRequest(inputs:List[UnificationInput],grid:Json,options:Json,width:Int,height:Int)
final case class UnificationJob(id:String,status:String,status_url:String,artifact_url:Option[String]=None,error:Option[ApiError]=None) derives JsonCodec
final case class UnificationRecord(job:UnificationJob,request:Json)

object UnificationRequest:
  private def invalid():Nothing=throw ApiError("invalid_request","Invalid image unification selection, grid or options")
  private[processing] def obj(json:Json,allowed:Set[String]):Map[String,Json]=json match
    case Json.Obj(fields) if fields.map(_._1).distinct.size==fields.size && fields.forall((k,_)=>allowed(k))=>fields.toMap
    case _=>invalid()
  private[processing] def string(value:Json):String=value match
    case Json.Str(s) if s.nonEmpty && s.length<=256=>s
    case _=>invalid()
  private[processing] def integer(value:Json,min:Int,max:Int):Int=value match
    case Json.Num(n) if n.scale<=0 || n.stripTrailingZeros().scale<=0=>
      val v=Try(n.intValueExact()).getOrElse(invalid())
      if v<min || v>max then invalid() else v
    case _=>invalid()
  private def number(value:Json,min:Double,max:Double):Double=value match
    case Json.Num(n)=>val v=n.doubleValue(); if !v.isFinite || v<min || v>max then invalid() else v
    case _=>invalid()
  def parse(json:Json):Either[ApiError,UnificationRequest]=Try {
    val root=obj(json,Set("inputs","grid","options"))
    val inputs=root.getOrElse("inputs",Json.Null) match
      case Json.Arr(values) if values.nonEmpty && values.size<=32=>values.toList.map { value=>
        val v=obj(value,Set("kind","id","download_id","image_hdu","plane_indices"))
        val kind=string(v.getOrElse("kind",Json.Null));val id=string(v.getOrElse("id",Json.Null))
        if !Set("native_chunk","archive_asset")(kind) then invalid()
        val download=v.get("download_id").map(string)
        if (kind=="native_chunk")!=download.isDefined then invalid()
        val hdu=v.getOrElse("image_hdu",Json.Null) match
          case Json.Null=>Json.Null
          case value @ Json.Str(s) if s.nonEmpty && s.length<=68=>value
          case value @ Json.Num(_)=>Json.Num(integer(value,0,1024))
          case _=>invalid()
        val planes=v.getOrElse("plane_indices",Json.Arr()) match
          case Json.Arr(xs) if xs.size<=8=>Json.Arr(xs.map(value=>Json.Num(integer(value,0,4095))))
          case _=>invalid()
        UnificationInput(kind,id,download,hdu,planes)
      }
      case _=>invalid()
    if inputs.map(_.id).distinct.size!=inputs.size then invalid()
    val grid=root.getOrElse("grid",Json.Null)
    val g=obj(grid,Set("kind","width","height","ra_degrees","dec_degrees","pixel_scale_arcsec"))
    val width=integer(g.getOrElse("width",Json.Null),1,512);val height=integer(g.getOrElse("height",Json.Null),1,512)
    string(g.getOrElse("kind",Json.Null)) match
      case "pixel"=>if g.keySet!=Set("kind","width","height") then invalid()
      case "sky"=>
        if g.keySet!=Set("kind","width","height","ra_degrees","dec_degrees","pixel_scale_arcsec") then invalid()
        if number(g("ra_degrees"),0,360)>=360 then invalid()
        number(g("dec_degrees"),-90,90)
        if number(g("pixel_scale_arcsec"),0,3600)<=0 then invalid()
      case _=>invalid()
    val options=root.getOrElse("options",Json.Obj("target_unit"->Json.Null,"normalization"->Json.Str("none"),"mask_policy"->Json.Str("science")))
    val o=obj(options,Set("target_unit","normalization","mask_policy"))
    o.get("target_unit").foreach {case Json.Null=>();case value=>if string(value).length>128 then invalid();()}
    if !Set("none","robust")(o.get("normalization").fold("none")(string)) then invalid()
    if o.get("mask_policy").exists(v=>v!=Json.Str("science") && v!=Json.Str("motion")) then invalid()
    val canonicalGrid=grid match
      case Json.Obj(fields)=>Json.Obj(fields.map {
        case ("width",_)=>"width"->Json.Num(width)
        case ("height",_)=>"height"->Json.Num(height)
        case field=>field
      })
      case _=>invalid()
    UnificationRequest(inputs,canonicalGrid,options,width,height)
  }.toEither.left.map {case e:ApiError=>e;case _=>ApiError("invalid_request","Invalid image unification request")}
