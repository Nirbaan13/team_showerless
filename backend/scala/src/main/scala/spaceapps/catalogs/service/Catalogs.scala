package spaceapps.catalogs.service

import spaceapps.catalogs.integrations.TapCatalogs
import spaceapps.infra.model.ApiError
import zio.*
import zio.json.*
import zio.json.ast.Json

final class Catalogs private(tap:TapCatalogs,slots:Semaphore):
  def query(ra:Double,dec:Double,fov:Double,candidate:Option[String]):Task[(Json,Boolean)]=slots.withPermit {
    for
      results<-ZIO.foreachPar(List("Gaia DR3","WISE","SIMBAD"))(kind=>tap.query(kind,ra,dec,fov/120).either.map(kind->_))
      sources=results.map((k,v)=>k->v.toOption.getOrElse(Nil)).toMap
      failed=results.count(_._2.isLeft)
      status=if failed==3 then "unavailable" else if failed>0 then "partial_agency" else "live_agency"
      providers=results.map { (kind,result)=>
        Json.Obj("catalog"->Json.Str(kind),"status"->Json.Str(if result.isRight then "ok" else "failed"),
          "error"->result.left.toOption.fold[Json](Json.Null)(e=>ApiError.from(e).toJson.fromJson[Json].toOption.get))
      }
    yield (Json.Obj("status"->Json.Str(status),"queriedCoordinate"->Json.Obj("ra"->Json.Num(ra),"dec"->Json.Num(dec),"fovArcmin"->Json.Num(fov)),
      "queriedAt"->Json.Str(java.time.Instant.now.toString),"candidateId"->candidate.fold[Json](Json.Null)(Json.Str(_)),
      "agenciesQueried"->Json.Arr(zio.Chunk.fromIterable(results.map(r=>Json.Str(r._1)))),
      "providers"->Json.Arr(zio.Chunk.fromIterable(providers)),
      "gaiaSources"->Json.Arr(zio.Chunk.fromIterable(sources("Gaia DR3"))),
      "wiseSources"->Json.Arr(zio.Chunk.fromIterable(sources("WISE"))),
      "simbadSources"->Json.Arr(zio.Chunk.fromIterable(sources("SIMBAD"))),
      "ephemerisSources"->Json.Arr(),"totalObjects"->Json.Num(sources.values.map(_.size).sum)),failed==3)
  }
object Catalogs:
  def make(tap:TapCatalogs):UIO[Catalogs]=Semaphore.make(4).map(new Catalogs(tap,_))
