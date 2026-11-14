package spaceapps.archive.protocol
import spaceapps.archive.*
import zio.*
final case class DataLink(url: Option[String],service_def: Option[String],semantic: String,format: String,estimated_bytes: Option[Long],requires_auth: Boolean,error: Option[String])
final case class SodaDescriptor(id: String,endpoint: String,dataset_id: String,circle: Boolean)
final case class DataLinks(links: List[DataLink],services: List[SodaDescriptor])
object DataLinkResolver:
  def decode(bytes: Array[Byte]): DataLinks =
    val table=VOTableCodec.decode(bytes,requireStatus=false)
    val links=table.rows.map(r=>DataLink(r.get("access_url"),r.get("service_def"),r.getOrElse("semantics",""),r.getOrElse("content_type","application/fits"),r.get("content_length").flatMap(_.toLongOption),r.get("link_authorized").exists(v=>v=="false" || v=="0") || r.get("link_auth").contains("required"),r.get("error_message")))
    val services=VOTableCodec.elements(table.root,"RESOURCE").filter(_.getAttribute("utype")=="adhoc:service").flatMap { r=>
      val params=VOTableCodec.elements(r,"PARAM").map(e=>e.getAttribute("name")->e.getAttribute("value")).toMap
      if params.get("standardID").exists(_.contains("SODA#sync")) then
        for endpoint<-params.get("accessURL");id<-params.get("ID").filter(_.nonEmpty)
        yield SodaDescriptor(r.getAttribute("ID"),endpoint,id,params.contains("CIRCLE"))
      else None
    }
    DataLinks(links,services)
final class DataLinkResolver(transport: ArchiveTransport):
  def resolve(url: String,policy: OriginPolicy): IO[ArchiveFailure,DataLinks] = transport.metadata(url,policy).flatMap(b=>ZIO.attempt(DataLinkResolver.decode(b)).mapError(ArchiveFailure.from))
