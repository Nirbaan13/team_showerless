package spaceapps.downloads.integrations.protocol
import spaceapps.downloads.model.*
object SodaResolver:
  def url(descriptor: SodaDescriptor,circle: Circle): String =
    if !descriptor.circle then throw ArchiveFailure("unsupported_cutout","Descriptor does not advertise CIRCLE")
    ArchiveTransport.params(descriptor.endpoint,List("ID"->descriptor.dataset_id,"CIRCLE"->s"${circle.ra_degrees} ${circle.dec_degrees} ${circle.radius_degrees}"))
  def select(record: ArchiveRecord,delivery: DeliveryRequest,links: DataLinks): List[ArchiveAsset] =
    val key=ArchiveAssetKey.key(record,delivery)
    val advertised=links.links.filter(l=>l.semantic=="#cutout" && l.error.isEmpty && !l.requires_auth).flatMap(_.service_def).toSet
    val cutout=links.services.find(s=>advertised(s.id) && s.circle)
    if delivery.mode!=DeliveryMode.original && delivery.region.nonEmpty && cutout.nonEmpty then
      List(ArchiveAsset(key,record.provider,url(cutout.get,delivery.region.get)))
    else if delivery.mode==DeliveryMode.require_cutout then throw ArchiveFailure("unsupported_cutout","No advertised spatial cutout for this product")
    else
      val science=links.links.filter(_.semantic=="#this")
      if science.exists(_.requires_auth) && !science.exists(l=> !l.requires_auth && l.url.nonEmpty) then throw ArchiveFailure("requires_auth","Science product requires authorization")
      science.filter(l=>l.error.isEmpty && !l.requires_auth).flatMap(l=>l.url.map(u=>ArchiveAsset(key,record.provider,u,l.semantic,l.format,l.estimated_bytes))) match
        case Nil=>throw ArchiveFailure("missing_product","No science asset was advertised")
        case asset::Nil=>List(asset)
        case _=>throw ArchiveFailure("ambiguous_science_asset","Multiple science originals need a qualified per-artifact identity; select an advertised cutout or another product")
