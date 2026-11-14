package spaceapps.archive
import spaceapps.domain.Hash
import zio.json.*
object AssetCache:
  def key(record: ArchiveRecord, delivery: DeliveryRequest): String = Hash.sha256(List(record.provider,record.collection,record.native_id,record.version.getOrElse(""),record.product_kind.toString,record.time.toJson,delivery.toJson).mkString("|"))
