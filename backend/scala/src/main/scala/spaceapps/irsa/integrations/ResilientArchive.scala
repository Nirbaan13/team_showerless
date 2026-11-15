package spaceapps.irsa.integrations

import spaceapps.irsa.model.*
import spaceapps.irsa.service.Archive
import spaceapps.infra.service.ExternalServices
import zio.*
import zio.json.ast.Json
import java.net.URI
import java.nio.file.Path

/** Live discovery is optional; native artifact identities survive failover. */
final class ResilientArchive(primary:Archive,mirror:Archive,services:ExternalServices) extends Archive:
  def search(query:Query):Task[List[ArchiveImage]]=
    services.call("irsa_sia")(primary.search(query).timeoutFail(ApiError("archive_timeout","SIA discovery exceeded the failover deadline",true))(15.seconds)).catchAll {
      case e:ApiError if e.retryable=>
        ZIO.logWarning(s"SIA discovery bypassed: ${e.code}; searching the public mirror index") *> mirror.search(query)
      case error=>ZIO.fail(error)
    }
  override def select(image:ArchiveImage,query:Query):Task[ArchiveImage]=
    if image.observation.header_metadata.get("discovery_source").contains(Json.Str("s3_mirror")) then ZIO.attempt {
      val parent=image.sourceUrl.getOrElse(image.accessUrl)
      val uri=URI.create(parent)
      val hosts=Set("nasa-irsa-spherex.s3.amazonaws.com","nasa-irsa-spherex.s3.us-east-1.amazonaws.com")
      if uri.getScheme!="https" || !hosts.contains(uri.getHost) || uri.getRawQuery!=null || uri.getFragment!=null || uri.getUserInfo!=null ||
        !Option(uri.getPath).exists(_.matches("/(dr1|qr3|qr2)/level2/[A-Za-z0-9_./-]+[.]fits")) || uri.getPath.contains("..") then
        throw ApiError("archive_untrusted_url","Mirror artifact is not an official native SPHEREx product")
      val ibe="https://irsa.ipac.caltech.edu/ibe/data/spherex"+uri.getRawPath
      image.copy(accessUrl=Cutouts.url(ibe,query),sourceUrl=Some(parent))
    }
    else primary.select(image,query)
  def fetch(image:ArchiveImage,destination:Path):Task[Unit]=primary.fetch(image,destination)
