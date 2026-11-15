package spaceapps.catalogs.integrations

import spaceapps.infra.model.ApiError
import zio.*
import zio.http.{Client,Request}
import zio.json.*
import zio.json.ast.Json
import java.net.URLEncoder
import java.nio.charset.StandardCharsets.UTF_8

/** Real TAP rows only. Empty data is a successful empty result, never a seed. */
final class TapCatalogs(client:Client,vizier:String="https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync",
  simbad:String="https://simbad.cfa.harvard.edu/simbad/sim-tap/sync"):
  private def protocol=ApiError("catalog_protocol","Catalogue returned invalid or oversized data",true)
  private def num(value:Json):Double=value match
    case Json.Num(n) if n.doubleValue.isFinite=>n.doubleValue
    case _=>throw protocol
  private def identity(value:Json):String=value match
    case Json.Str(s) if s.nonEmpty && s.length<=256=>s.trim
    case Json.Num(n)=>n.toPlainString
    case _=>throw protocol
  private def optional(value:Json):Json=if value==Json.Null then Json.Null else Json.Num(num(value))
  def query(kind:String,ra:Double,dec:Double,radius:Double):Task[List[Json]]=
    val circle=s"CIRCLE('ICRS', $ra, $dec, $radius)"
    val (endpoint,adql)=kind match
      case "Gaia DR3"=>(vizier,s"""SELECT TOP 8 Source, RA_ICRS, DE_ICRS, Gmag, pmRA, pmDE FROM "I/355/gaiadr3" WHERE CONTAINS(POINT('ICRS', RA_ICRS, DE_ICRS), $circle)=1""")
      case "WISE"=>(vizier,s"""SELECT TOP 8 AllWISE, RAJ2000, DEJ2000, W1mag, W2mag FROM "II/328/allwise" WHERE CONTAINS(POINT('ICRS', RAJ2000, DEJ2000), $circle)=1""")
      case "SIMBAD"=>(simbad,s"SELECT TOP 8 main_id, ra, dec, otype FROM basic WHERE CONTAINS(POINT('ICRS', ra, dec), $circle)=1")
    ZIO.scoped {
      for
        response<-client.request(Request.get(endpoint+"?request=doQuery&lang=adql&format=json&query="+URLEncoder.encode(adql,UTF_8)))
        _<-ZIO.fail(ApiError("catalog_upstream_error",s"$kind returned HTTP ${response.status.code}",true)).unless(response.status.code==200)
        bytes<-response.body.asStream.take(1048577).runCollect
        _<-ZIO.fail(protocol).when(bytes.size>1048576)
        document<-ZIO.fromEither(new String(bytes.toArray,UTF_8).fromJson[Json]).mapError(_=>protocol)
        rows<-ZIO.attempt {
          val values=document.asObject.flatMap(_.get("data")).flatMap(_.asArray).getOrElse(throw protocol)
          if values.size>8 then throw protocol
          values.toList.map { row=>
            val cells=row.asArray.getOrElse(throw protocol)
            val count=if kind=="Gaia DR3" then 6 else if kind=="WISE" then 5 else 4
            if cells.size!=count then throw protocol
            val rawId=identity(cells(0))
            val x=num(cells(1));val y=num(cells(2))
            if x<0 || x>=360 || y< -90 || y>90 then throw protocol
            val id=if kind=="SIMBAD" then rawId else s"${if kind=="WISE" then "AllWISE" else "Gaia DR3"} $rawId"
            val encoded=URLEncoder.encode(rawId,UTF_8)
            val reference=if kind=="SIMBAD" then s"https://simbad.cds.unistra.fr/simbad/sim-id?Ident=$encoded"
              else if kind=="WISE" then s"https://vizier.cds.unistra.fr/viz-bin/VizieR-5?-source=II/328/allwise&AllWISE=$encoded"
              else s"https://vizier.cds.unistra.fr/viz-bin/VizieR-5?-source=I/355/gaiadr3&Source=$encoded"
            val extra=if kind=="Gaia DR3" then List("mag"->optional(cells(3)),"pmRa"->optional(cells(4)),"pmDec"->optional(cells(5)))
              else if kind=="WISE" then List("mag"->optional(cells(3)),"w2Mag"->optional(cells(4)))
              else List("mag"->Json.Null,"objectType"->cells(3))
            Json.Obj(zio.Chunk.fromIterable(List("id"->Json.Str(id),"label"->Json.Str(id),"ra"->Json.Num(x),"dec"->Json.Num(y),
              "provider_url"->Json.Str(endpoint),"agency"->Json.Str(kind+" TAP"),"referenceUrl"->Json.Str(reference),"catalogType"->Json.Str(kind))++extra))
          }
        }
      yield rows
    }.timeoutFail(ApiError("catalog_timeout",s"$kind request timed out",true))(6.seconds)
      .mapError { case e:ApiError=>e;case _=>ApiError("catalog_unavailable",s"$kind is unavailable",true) }
