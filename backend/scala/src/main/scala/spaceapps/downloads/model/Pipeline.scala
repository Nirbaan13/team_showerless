package spaceapps.downloads.model

import zio.json.*
import java.nio.file.Path

final case class DownloadChunk(id:String,record_id:String,artifact_url:String,status:String="pending",error:Option[ArchiveFailure]=None) derives JsonCodec
final case class DownloadProgress(discovery_complete:Boolean=true,total_chunks:Int=0,ready_chunks:Int=0,failed_chunks:Int=0,unavailable_chunks:Int=0) derives JsonCodec

enum AssetResource:
  case Pending
  case Ready(path:Path,asset:StoredAsset)
  case Failed(error:ArchiveFailure)
