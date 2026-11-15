package spaceapps.service

import spaceapps.domain.*
import zio.*
import zio.json.*
import java.nio.file.{Files,Path}
import scala.jdk.CollectionConverters.*

final case class SpectrumPoint(channel:Int,frame_id:String,detector:String,detector_array:Int,
  wavelength_um:Double,bandwidth_um:Double,flux_mjy:Double,uncertainty_mjy:Double,snr:Double,mjd:Double,
  flagged:Boolean=false) derives JsonCodec
final case class SpectrumSummary(range:String,mean_flux_mjy:Double,mean_snr:Double,channels:Int) derives JsonCodec
final case class SpectrumFailure(frame_id:String,code:String) derives JsonCodec
final case class SpectrumResult(ra:Double,dec:Double,aperture_radius_pix:Double,subtraction_mode:String,
  bad_pixel_mask:String,wcs_mode:String,quality:String,scientifically_calibrated:Boolean,
  detectors_summary:Map[String,SpectrumSummary],total_channels:Int,n_exposures_found:Int,
  n_masked_or_outside:Int,n_failed:Int,failures:List[SpectrumFailure],spectrum:List[SpectrumPoint],warnings:List[String],
  molecular_detections:List[zio.json.ast.Json]=Nil,target:String="",candidate_id:Option[String]=None,
  download_id:String="",n_download_failed:Int=0,n_unmeasured:Int=0) derives JsonCodec

trait SpectrumProcessor:
  def measure(inputs:List[(String,Path)],output:Path,ra:Double,dec:Double,radius:Double,subtraction:String):Task[SpectrumResult]

final case class SpectrumQuery(ra:Double,dec:Double,radius:Double=2,subtraction:String="zodi_subtracted",
  size:Double=1.5,maxFrames:Int=120,candidate:Option[String]=None,downloadId:Option[String]=None,
  detector:Option[String]=None,after:Option[String]=None,before:Option[String]=None)
object SpectrumQuery:
  def parse(p:Map[String,String]):Either[ApiError,SpectrumQuery]=scala.util.Try {
    def fail(message:String):Nothing=throw ApiError("invalid_request",message)
    def number(key:String,default:Option[Double]=None):Double=
      val n=p.get(key).map(_.toDouble).orElse(default).getOrElse(fail(s"$key is required"))
      if !n.isFinite then fail(s"$key must be finite")
      n
    val ra=number("ra");val dec=number("dec");val radius=number("radius_pix",Some(2))
    val size=number("size_arcmin",Some(1.5));val max=number("max_frames",Some(120))
    if ra<0 || ra>=360 || dec< -90 || dec>90 || radius<0.5 || radius>10 || size<0.5 || size>10 ||
      !max.isWhole || max<1 || max>120 then fail("Coordinates, aperture, size or frame limit are outside supported ranges")
    val mode=p.getOrElse("subtraction","zodi_subtracted")
    if !Set("zodi_subtracted","raw_calibrated").contains(mode) then fail("Unsupported subtraction mode")
    val candidate=p.get("candidate_id").filter(_.nonEmpty)
    if candidate.exists(s=>s.length>256 || s.exists(_.isControl)) then fail("candidate_id is too long or contains control characters")
    val id=p.get("download_id")
    if id.exists(!_.matches("[A-Za-z0-9-]{1,128}")) then fail("Invalid download_id")
    val result=SpectrumQuery(ra,dec,radius,mode,size,max.toInt,candidate,id,p.get("detector_array"),p.get("observed_after"),p.get("observed_before"))
    // Validate dates and detector even when the caller reuses an existing download.
    result.nativeQuery.fold(throw _,identity)
    result
  }.toEither.left.map {case e:ApiError=>e;case _=>ApiError("invalid_request","Invalid numeric spectrum parameter")}
extension (q:SpectrumQuery)
  def nativeQuery:Either[ApiError,Query]=Query.fromParameters("default",Map("right_ascension_deg"->q.ra.toString,
    "declination_deg"->q.dec.toString,"width_arcmin"->q.size.toString,"height_arcmin"->q.size.toString) ++
    q.detector.map("detector_array"->_) ++ q.after.map("observed_after"->_) ++ q.before.map("observed_before"->_))

enum SpectrumReply:
  case Pending(download:Download)
  case Ready(result:SpectrumResult)

final class SpectrumService private(jobs:Jobs,processor:SpectrumProcessor,data:Path,
  slots:Semaphore,cache:Ref[Map[String,SpectrumResult]]):
  def get(query:SpectrumQuery):Task[SpectrumReply]=
    for
      download<-query.downloadId match
        case Some(id)=>jobs.get(id)
        case None=>ZIO.fromEither(query.nativeQuery).flatMap(jobs.submit(_,"default",None))
      _<-ZIO.fail(ApiError("invalid_request","Spectrum measurements require native default-mode FITS, before ZODI processing"))
        .when(download.mode!="default")
      result<-if !download.terminal then ZIO.succeed(SpectrumReply.Pending(download))
        else measured(download,query).map(SpectrumReply.Ready(_))
    yield result

  private def measured(download:Download,q:SpectrumQuery):Task[SpectrumResult]=
    val key=Hash.sha256(s"spectrum-preview-v1|${download.id}|${q.ra}|${q.dec}|${q.radius}|${q.subtraction}|${q.maxFrames}")
    val selected=download.chunks.filter(_.status=="ready").take(q.maxFrames)
    val compute=ZIO.scoped {
      for
        _<-ZIO.fail(ApiError("no_measurements","No downloaded native FITS is available; inspect the download errors"))
          .when(selected.isEmpty)
        folder<-ZIO.acquireRelease(ZIO.attemptBlocking {
          Files.createDirectories(data.resolve("spectra"))
          Files.createTempDirectory(data.resolve("spectra"),"spectrum-")
        })(p=>ZIO.attemptBlocking {
          val walk=Files.walk(p)
          try walk.iterator().asScala.toList.reverse.foreach(Files.deleteIfExists(_)) finally walk.close()
        }.ignore)
        inputs<-ZIO.foreach(selected) { chunk=>
          jobs.leasedResource(chunk.id,false).flatMap {
            case Resource.Ready(path)=>ZIO.succeed(chunk.frame_id->path)
            case _=>ZIO.fail(ApiError("cache_missing","A native FITS input was evicted; submit a new download",true))
          }
        }
        result<-processor.measure(inputs,folder.resolve("result.json"),q.ra,q.dec,q.radius,q.subtraction)
      yield result.copy(download_id=download.id,n_exposures_found=download.observations.size,
        n_download_failed=download.chunks.count(_.status!="ready"),n_unmeasured=math.max(0,download.chunks.count(_.status=="ready")-selected.size),
        warnings=result.warnings ++ Option.when(download.chunks.count(_.status=="ready")>selected.size)("frame_limit_reached") ++
          Option.when(download.chunks.exists(_.status!="ready"))("download_incomplete"))
    }
    slots.withPermit {
      cache.get.flatMap(_.get(key) match
        case Some(value)=>ZIO.succeed(value)
        case None=>compute.tap(value=>cache.update(entries=>entries.take(15).updated(key,value))))
    }.map(_.copy(target=q.candidate.getOrElse(s"RA ${q.ra}, Dec ${q.dec}"),candidate_id=q.candidate))

object SpectrumService:
  def make(jobs:Jobs,processor:SpectrumProcessor,data:Path):UIO[SpectrumService]=
    for
      slots<-Semaphore.make(1)
      cache<-Ref.make(Map.empty[String,SpectrumResult])
    yield new SpectrumService(jobs,processor,data,slots,cache)
