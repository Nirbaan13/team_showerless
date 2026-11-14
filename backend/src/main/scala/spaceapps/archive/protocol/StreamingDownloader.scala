package spaceapps.archive.protocol
import spaceapps.archive.*
import spaceapps.integrations.fits.FitsHeaders
import zio.*
import java.nio.file.{Files,Path,StandardCopyOption}
import java.io.{BufferedInputStream,InputStream}
import java.util.zip.GZIPInputStream
import java.security.MessageDigest
import java.nio.charset.StandardCharsets.US_ASCII

final class StreamingDownloader(transport: ArchiveTransport,val directory: Path,maxBytes: Long = 256L*1024*1024):
  require(maxBytes>0)
  def fetch(asset: ArchiveAsset,policy: OriginPolicy): IO[ArchiveFailure,StoredAsset] =
    if asset.requires_auth then ZIO.fail(ArchiveFailure("requires_auth","Selected asset requires authorization"))
    else if !asset.id.matches("[a-zA-Z0-9_-]{1,128}") then ZIO.fail(ArchiveFailure("invalid_asset","Invalid server asset identity"))
    else ZIO.scoped {
      for
        _ <- ZIO.attemptBlocking(Files.createDirectories(directory))
        temp <- ZIO.acquireRelease(ZIO.attemptBlocking(Files.createTempFile(directory,"transfer-",".part")))(p=>ZIO.attemptBlocking(Files.deleteIfExists(p)).ignore)
        decoded <- ZIO.acquireRelease(ZIO.attemptBlocking(Files.createTempFile(directory,"decoded-",".part")))(p=>ZIO.attemptBlocking(Files.deleteIfExists(p)).ignore)
        _ <- transport.response(asset.url,policy) { r=>
          ZIO.scoped {
            ZIO.acquireRelease(ZIO.attemptBlocking(Files.newOutputStream(temp)))(o=>ZIO.attemptBlocking(o.close()).orDie).flatMap { out=>
              transport.bounded(r,maxBytes).chunks.runForeach(c=>ZIO.attemptBlocking(out.write(c.toArray)))
            }
          }
        }
        compressed <- ZIO.attemptBlocking {
          val in=Files.newInputStream(temp)
          try in.read()==0x1f && in.read()==0x8b finally in.close()
        }
        validation=if compressed then decoded else temp
        _ <- if compressed then ZIO.attemptBlockingInterrupt {
          val in=new GZIPInputStream(new BufferedInputStream(Files.newInputStream(temp)))
          val out=Files.newOutputStream(decoded)
          try
            val buffer=new Array[Byte](65536);var total=0L;var n=in.read(buffer)
            while n != -1 do
              total+=n
              if total>maxBytes then throw ArchiveFailure("byte_limit","Decoded product exceeds byte budget")
              out.write(buffer,0,n);n=in.read(buffer)
          finally {in.close();out.close()}
        } else ZIO.unit
        _ <- FitsHeaders.read(validation).mapError(_=>ArchiveFailure("invalid_fits","Product is not a structurally complete FITS file"))
        unit <- ZIO.attemptBlocking {
          val in=Files.newInputStream(validation)
          try
            var value=Option.empty[String];var done=false;var cards=0
            while !done && cards<32768 do
              val card=new String(in.readNBytes(80),US_ASCII);cards+=1
              if card.take(8).trim=="END" || card.length<80 then done=true
              else if card.take(8).trim=="BUNIT" then value=Some(nom.tam.fits.HeaderCard.create(card).getValue)
            value
          finally in.close()
        }
        metadata <- ZIO.attemptBlocking {
          val hash=MessageDigest.getInstance("SHA-256");val in=Files.newInputStream(temp)
          try
            val buffer=new Array[Byte](65536);var n=in.read(buffer)
            while n != -1 do {hash.update(buffer,0,n);n=in.read(buffer)}
          finally in.close()
          StoredAsset(asset.id,Files.size(temp),hash.digest().map(b=>f"${b & 255}%02x").mkString,if compressed then "gzip" else "native",unit,artifact_url=s"/api/archive-assets/${asset.id}")
        }
        _ <- ZIO.attemptBlocking(Files.move(temp,directory.resolve(asset.id),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING))
      yield metadata
    }.mapError(ArchiveFailure.from).timeoutFail(ArchiveFailure("timeout","Product transfer timed out",true))(5.minutes)
