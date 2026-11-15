package spaceapps.downloads.integrations.providers

import spaceapps.downloads.integrations.ArchiveProvider
import spaceapps.downloads.integrations.protocol.*
import spaceapps.downloads.model.*
import spaceapps.infra.model.Hash
import zio.*
import nom.tam.fits.Header
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets.US_ASCII
import java.time.Instant
import java.util.concurrent.{ConcurrentHashMap,Semaphore as JavaSemaphore}

/** Metadata-only discovery for the author's immutable neo11 W2 visit coadds. */
final class UnwiseProvider(transport:ArchiveTransport,base:String=UnwiseProvider.base,override val origins:OriginPolicy=OriginPolicy.unwise) extends ArchiveProvider:
  import UnwiseProvider.*
  val id="unwise-neo11"
  private var atlasCache:Option[List[Tile]]=None
  private val atlasLock=new JavaSemaphore(1)
  private val headers=new ConcurrentHashMap[String,Option[ArchiveRecord]]()
  def capabilities=ZIO.succeed(ProviderCapabilities(List(ProductKind.image),TimeFilterMode.exact_utc,original=true,
    restrictions=List("neo11 W2 visit coadds only; actual MJDMIN/MJDMAX intervals, including the mission gap",
      "Exact UTC visit-interval overlap; a matching result is the whole coadd, not a temporal cutout",
      "Indexed tile subset; maximum radius 0.25 degrees, 4 candidate tiles and 96 science headers per query",
      "Original science, inverse variance, coverage and contributing-frame products; no cutouts",
      "Discovery does not prove local pixels or successful preparation; artifact, outlier and bloom masks unavailable")))
  private def atlas:IO[ArchiveFailure,List[Tile]]=
    ZIO.acquireReleaseWith(ZIO.attemptBlockingInterrupt(atlasLock.acquire()).mapError(ArchiveFailure.from))(_=>ZIO.succeed(atlasLock.release())) { _=>
      atlasCache match
        case Some(rows)=>ZIO.succeed(rows)
        case None=>transport.metadata(base+"/time_resolved_neo11-atlas.fits",origins)
          .flatMap(bytes=>ZIO.attempt(decodeAtlas(bytes)).mapError(invalid))
          .tap(rows=>ZIO.succeed { atlasCache=Some(rows) })
    }
  private def observation(tile:Tile,epoch:Int):IO[ArchiveFailure,Option[ArchiveRecord]]=
    val key=s"${tile.coadd}:$epoch"
    Option(headers.get(key)) match
      case Some(cached)=>ZIO.succeed(cached)
      case None=>
        transport.metadataRange(productUrl(base,tile.coadd,epoch,"img-m.fits"),origins,headerBytes)
          .flatMap(bytes=>ZIO.attempt(decodeObservation(tile,epoch,bytes)).mapError(invalid)).map(Some(_))
          .catchSome { case e if e.code=="http_error" && e.message=="Archive returned HTTP 404"=>ZIO.none }
          .tap(record=>ZIO.succeed { if headers.size>=4096 then headers.clear(); headers.put(key,record); () })
  def search(query:ArchiveQuery,cursor:Option[ProviderCursor]):IO[ArchiveFailure,ProviderPage]=
    for
      q <- ZIO.fromEither(query.validate)
      _ <- ZIO.fail(ArchiveFailure("unsupported_geometry","unWISE indexed search supports radius at most 0.25 degrees")).when(q.region.radius_degrees>0.25)
      _ <- ZIO.fail(ArchiveFailure("unsupported_cursor","unWISE indexed search does not support continuation cursors")).when(cursor.nonEmpty)
      page <- if !q.product_kinds.contains(ProductKind.image) then ZIO.succeed(ProviderPage(Nil,Completeness.indexed_subset)) else for
        rows <- atlas
        tiles=rows.filter(t=>distance(t.ra,t.dec,q.region)<=q.region.radius_degrees+tileRadius).sortBy(t=>distance(t.ra,t.dec,q.region))
        all=tiles.take(4).flatMap(t=>t.epochs.map(t->_))
        candidates=all.take(96)
        probed <- ZIO.foreachPar(candidates) { (tile,epoch)=>observation(tile,epoch).either.map(result=>(tile,epoch,result)) }.withParallelism(4)
        errors=probed.collect { case (tile,epoch,Left(error))=>s"${tile.coadd}/e$epoch: ${error.code}" }
        missing=probed.collect { case (tile,epoch,Right(None))=>s"${tile.coadd}/e$epoch: W2 science unavailable (HTTP 404)" }
        records=probed.collect { case (_,_,Right(Some(record))) if overlaps(record,q)=>record }
        capped=tiles.size>4 || all.size>96 || records.size>q.limit_per_provider
        warnings=List("Indexed candidate subset; no claim of full-sky or complete footprint coverage")++
          Option.when(tiles.size>4)("Candidate tile budget reached (4); additional tile coverage was not searched")++
          Option.when(all.size>96)("Science-header budget reached (96); additional epochs were not searched")++
          Option.when(records.size>q.limit_per_provider)("Result limit reached; additional matching observations were omitted")++errors++missing
        _ <- if records.isEmpty && errors.nonEmpty && missing.isEmpty then ZIO.fail(ArchiveFailure("metadata_unavailable","No candidate science headers could be validated: "+errors.take(3).mkString("; "),true)) else ZIO.unit
      yield ProviderPage(records.take(q.limit_per_provider),if capped then Completeness.truncated else Completeness.indexed_subset,warnings=warnings)
    yield page
  def resolve(record:ArchiveRecord,delivery:DeliveryRequest):IO[ArchiveFailure,List[ArchiveAsset]]=ZIO.attempt {
    if delivery.mode==DeliveryMode.require_cutout then throw ArchiveFailure("cutout_unavailable","unWISE neo11 supplies native coadds, not cutouts")
    val identity="([0-9]{4}[pm][0-9]{3}):w2:e([0-9]{3})".r
    val (tile,epoch)=record.native_id match
      case identity(tile,epoch)=>(tile,epoch.toInt)
      case _=>throw ArchiveFailure("invalid_record","Invalid server unWISE observation identity")
    val expected=ArchiveRecord.create(id,"neo11",record.native_id,ProductKind.image,Some("neo11"))
    if record.provider!=id || record.collection!="neo11" || record.product_kind!=ProductKind.image || record.version!=Some("neo11") || record.id!=expected.id ||
      !Map("coadd_id"->tile,"epoch"->epoch.toString,"band"->"2","FILTER"->"W2","release"->"neo11").forall((k,v)=>record.native.get(k).contains(v)) then
      throw ArchiveFailure("invalid_record","Observation is not a validated neo11 W2 record")
    val science=ArchiveAssetKey.key(record,delivery)
    List(("#this","img-m.fits"),("#inverse-variance","invvar-m.fits.gz"),("#coverage","n-m.fits.gz"),("#contributors","frames.fits")).map { (role,suffix)=>
      ArchiveAsset(if role=="#this" then science else Hash.sha256(science+"|"+role),id,productUrl(base,tile,epoch,suffix),role)
    }
  }.mapError(invalid)

object UnwiseProvider:
  val base="https://portal.nersc.gov/project/cosmo/temp/ameisner/neo11"
  private val headerBytes=11520
  private val tileRadius=math.sqrt(2)*1024*2.75/3600
  private final case class Tile(coadd:String,ra:Double,dec:Double,row:Long,epochs:List[Int])
  private def invalid(t:Throwable):ArchiveFailure=t match
    case e:ArchiveFailure=>e
    case _=>ArchiveFailure("invalid_response","Invalid unWISE metadata or unsupported atlas layout")
  private def productUrl(base:String,tile:String,epoch:Int,suffix:String):String=f"$base/e$epoch%03d/${tile.take(3)}/$tile/unwise-$tile-w2-$suffix"
  /** Header cards only: the response may include a few bytes past END, never a full image. */
  private def header(bytes:Array[Byte],offset:Int=0):(Header,Int)=
    val lines=scala.collection.mutable.ListBuffer.empty[String]
    var pos=offset
    var end=false
    while !end && pos+80<=bytes.length && pos-offset<headerBytes do
      val card=new String(bytes,pos,80,US_ASCII)
      lines+=card;pos+=80;end=card.take(8).trim=="END"
    if !end then throw ArchiveFailure("invalid_response","Bounded FITS header has no END card")
    (new Header(lines.toArray),offset+((pos-offset+2879)/2880)*2880)
  private def string(h:Header,key:String):String=Option(h.getStringValue(key)).fold("")(_.trim)
  private def number(h:Header,key:String):Double=
    val value=h.getDoubleValue(key,Double.NaN)
    if !value.isFinite then throw ArchiveFailure("invalid_response",s"Missing or nonfinite FITS $key")
    value
  private def decodeAtlas(bytes:Array[Byte]):List[Tile]=
    val (primary,next)=header(bytes)
    if !primary.getBooleanValue("SIMPLE",false) || primary.getIntValue("NAXIS",-1)!=0 then throw ArchiveFailure("invalid_response","Invalid unWISE atlas primary HDU")
    val (table,start)=header(bytes,next)
    val schema=List("COADD_ID"->"8A","RA"->"D","DEC"->"D","ROW"->"K","EPOCH_BITMASK"->"427B")
    val count=table.getIntValue("NAXIS2",-1)
    if string(table,"XTENSION")!="BINTABLE" || table.getIntValue("NAXIS1")!=459 || table.getIntValue("TFIELDS")!=5 || table.getIntValue("PCOUNT")!=0 ||
      count<0 || count>20000 || start.toLong+459L*count>bytes.length || !schema.zipWithIndex.forall { case ((name,format),i)=>string(table,s"TTYPE${i+1}")==name && string(table,s"TFORM${i+1}")==format } then
      throw ArchiveFailure("invalid_response","Unexpected bounded unWISE atlas schema")
    val data=ByteBuffer.wrap(bytes)
    val rows=(0 until count).map { i=>
      data.position(start+i*459)
      val tileBytes=new Array[Byte](8);data.get(tileBytes)
      val tile=new String(tileBytes,US_ASCII)
      val ra=data.getDouble();val dec=data.getDouble();val row=data.getLong()
      val bits=new Array[Byte](427);data.get(bits)
      if !tile.matches("[0-9]{4}[pm][0-9]{3}") || !ra.isFinite || !dec.isFinite || ra<0 || ra>=360 || dec< -90 || dec>90 || row<0 then throw ArchiveFailure("invalid_response","Invalid atlas tile identity or position")
      Tile(tile,ra,dec,row,bits.zipWithIndex.collect { case (mask,epoch) if (mask & 2)!=0=>epoch }.toList)
    }.toList
    if rows.map(_.coadd).distinct.size!=rows.size then throw ArchiveFailure("invalid_response","Duplicate unWISE atlas tile identity")
    rows
  private def mjd(value:Double):String=
    val seconds=(BigDecimal(value.toString)-BigDecimal(40587))*BigDecimal(86400)
    val whole=seconds.setScale(0,BigDecimal.RoundingMode.FLOOR).toLong
    Instant.ofEpochSecond(whole,((seconds-BigDecimal(whole))*BigDecimal(1000000000)).toLong).toString
  private def decodeObservation(tile:Tile,epoch:Int,bytes:Array[Byte]):ArchiveRecord=
    val (h,_)=header(bytes)
    val explicitBand=Option(h.findCard("BAND"))
    // Author's early neo11 coadds omit BAND; preserve that absence in native header metadata.
    // The candidate already came from the author's W2 atlas bit and a generated W2 URL.
    val validBand=explicitBand.fold(string(h,"REFEREN1").endsWith("_w2"))(_=>h.getIntValue("BAND",-1)==2)
    val validFilter=Option(h.findCard("FILTER")).forall(_=>string(h,"FILTER")=="W2")
    if !h.getBooleanValue("SIMPLE",false) || h.getIntValue("EPOCH",-1)!=epoch || !validBand || !validFilter ||
      distance(number(h,"CRVAL1"),number(h,"CRVAL2"),Circle(tile.ra,tile.dec,0.01))>0.00001 then
      throw ArchiveFailure("invalid_response","Science header identity does not match atlas tile, W2 band and epoch")
    val min=number(h,"MJDMIN");val max=number(h,"MJDMAX")
    if min<50000 || max>100000 || max<min then throw ArchiveFailure("invalid_response","Invalid science observation MJD interval")
    val magnitude=number(h,"MAGZP")
    val scale=2.75/3600
    val qualified=h.getIntValue("NAXIS")==2 && h.getIntValue("NAXIS1")==2048 && h.getIntValue("NAXIS2")==2048 && h.getIntValue("BITPIX")== -32 &&
      string(h,"CTYPE1")=="RA---TAN" && string(h,"CTYPE2")=="DEC--TAN" &&
      math.abs(number(h,"CD1_1")+scale)<1e-12 && math.abs(number(h,"CD2_2")-scale)<1e-12 && math.abs(number(h,"CD1_2"))<1e-12 && math.abs(number(h,"CD2_1"))<1e-12 &&
      math.abs(magnitude-22.5)<1e-8 && math.abs(number(h,"UNW_DVER")-3.3)<1e-8
    val keys=List("MJDMIN","MJDMAX","MAGZP","UNW_DVER","UNW_DATE","UNW_VER","REFEREN1","BAND","CRVAL1","CRVAL2","CD1_1","CD1_2","CD2_1","CD2_2","NAXIS1","NAXIS2","CRPIX1","CRPIX2")
    val native=keys.flatMap(k=>Option(h.findCard(k)).map(c=>k->c.getValue)).toMap++Map("coadd_id"->tile.coadd,"epoch"->epoch.toString,"band"->"2","FILTER"->"W2","release"->"neo11","atlas_row"->tile.row.toString,"pixel_scale_arcsec"->"2.75")
    val provenance=Map("archive"->"author unWISE NERSC","release"->"neo11","analysis_profile"->"unwise","observation_time_source"->"science FITS MJDMIN/MJDMAX (UTC MJD)",
      "band_identity_source"->(if explicitBand.nonEmpty then "science_fits_BAND" else "atlas_w2+archive_product_path+REFEREN1"),
      "spatial_semantics"->"indexed atlas candidates; coadd geometry, per-pixel coverage requires preparation","unavailable_masks"->"artifact,outlier,bloom",
      "preparation_limits"->"PSF and astrometry require qualification; no local pixels verified by discovery")++Option.when(!qualified)("analysis_ineligible_reason"->"Unsupported unWISE W2 geometry, calibration or data model")
    ArchiveRecord.create("unwise-neo11","neo11",f"${tile.coadd}:w2:e$epoch%03d",ProductKind.image,Some("neo11"),native).copy(
      mission=Some("WISE/NEOWISE"),instrument=Some("WISE"),time=ObservationTime(Some(mjd(min)),Some(mjd(max)),TimeQuality.verified,Map("MJDMIN"->min.toString,"MJDMAX"->max.toString)),
      sky_coverage=Some(s"ICRS TAN native coadd centered at ${tile.ra},${tile.dec}; per-pixel coverage not yet verified"),
      brightness_unit=Some(if math.abs(magnitude-22.5)<1e-8 then "Vega nanomaggy (MAGZP 22.5)" else s"Vega relative flux (MAGZP $magnitude)"),
      provenance=provenance,original=true,analysisEligible=qualified)
  private def distance(ra:Double,dec:Double,c:Circle):Double=
    val a=math.toRadians(ra-c.ra_degrees);val d=math.toRadians(dec);val center=math.toRadians(c.dec_degrees)
    math.toDegrees(math.acos(math.max(-1d,math.min(1d,math.sin(d)*math.sin(center)+math.cos(d)*math.cos(center)*math.cos(a)))))
  private def overlaps(record:ArchiveRecord,q:ArchiveQuery):Boolean=
    val start=record.time.start_utc.map(Instant.parse).get
    val end=record.time.end_utc.map(Instant.parse).get
    q.time_start_utc.forall(t=> !end.isBefore(Instant.parse(t))) && q.time_end_utc.forall(t=>start.isBefore(Instant.parse(t)))
