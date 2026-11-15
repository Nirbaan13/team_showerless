package spaceapps.downloads.controller

import spaceapps.downloads.model.*
import zio.http.Request

/** Common URL filters only; source-specific detector/channel fields are deliberately absent. */
object ObservationParameters:
  def parse(request:Request):Either[ArchiveFailure,ArchiveQuery]=
    scala.util.Try {
      val allowed=Set("right_ascension_deg","declination_deg","ra_degrees","dec_degrees","radius_degrees","providers","product_kinds","observed_after","observed_before","time_start_utc","time_end_utc","limit_per_provider")
      val pairs=request.url.queryParams.map
      if pairs.keys.exists(!allowed.contains(_)) then throw ArchiveFailure("invalid_request","Unsupported common search parameter")
      def one(name:String):Option[String]=
        val values=request.url.queryParams.getAll(name)
        if values.size>1 then throw ArchiveFailure("invalid_request",s"$name must appear once")
        values.headOption
      def alias(name:String,old:String):Option[String]=
        val a=one(name);val b=one(old)
        if a.nonEmpty && b.nonEmpty then throw ArchiveFailure("invalid_request",s"Supply $name only once")
        a.orElse(b)
      def number(value:Option[String],name:String)=value.flatMap(_.toDoubleOption).getOrElse(throw ArchiveFailure("invalid_request",s"$name must be numeric"))
      def values(name:String,default:List[String])=one(name).fold(default)(_.split(",",-1).toList.map(_.trim))
      val region=Circle(number(alias("right_ascension_deg","ra_degrees"),"right_ascension_deg"),number(alias("declination_deg","dec_degrees"),"declination_deg"),number(one("radius_degrees"),"radius_degrees"))
      val kinds=values("product_kinds",List("image")).map(v=>ProductKind.values.find(_.toString==v).getOrElse(throw ArchiveFailure("invalid_request","Unknown product kind")))
      val limit=one("limit_per_provider").fold(100)(v=>v.toIntOption.getOrElse(throw ArchiveFailure("invalid_request","limit_per_provider must be an integer")))
      ArchiveQuery(region,values("providers",Nil),kinds,alias("observed_after","time_start_utc"),alias("observed_before","time_end_utc"),limit)
    }.toEither.left.map {
      case e:ArchiveFailure=>e
      case _=>ArchiveFailure("invalid_request","Invalid common search parameters")
    }.flatMap(_.validate)
