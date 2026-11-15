package spaceapps.integrations.fits

import spaceapps.domain.ApiError
import zio.*
import zio.json.ast.Json
import nom.tam.fits.{Header, HeaderCard}
import java.io.RandomAccessFile
import java.nio.charset.StandardCharsets.US_ASCII
import java.nio.file.Path

/** Reads physical header cards and seeks over data blocks; pixel and table arrays are never loaded. */
object FitsHeaders:
  private val maxCards = 32768
  private val maxHdus = 64
  private def obj(fields: (String, Json)*): Json = Json.Obj(Chunk.fromIterable(fields))
  private def arr(values: Iterable[Json]): Json = Json.Arr(Chunk.fromIterable(values))
  private def invalid(message: String): Nothing = throw ApiError("metadata_invalid_fits", message)
  private def str(value: String): Json = Option(value).fold[Json](Json.Null)(Json.Str(_))
  private def cardValue(card: HeaderCard): Json =
    val value = card.getValue
    if value == null then Json.Null
    else if card.isStringValue then Json.Str(value)
    else if card.isIntegerType || card.isDecimalType then scala.util.Try(BigDecimal(value.replace('D', 'E').replace('d', 'e'))).toOption.fold[Json](Json.Str(value))(Json.Num(_))
    else if card.valueType() == classOf[java.lang.Boolean] then Json.Bool(value == "T")
    else Json.Str(value)

  def read(path: Path): Task[Json] = ZIO.attemptBlocking {
    val file = new RandomAccessFile(path.toFile, "r")
    try
      val length = file.length()
      if length == 0 || length % 2880 != 0 then invalid("Cached native file is not a complete FITS block sequence")
      val hdus = List.newBuilder[Json]
      var hduIndex = 0
      var totalCards = 0
      while file.getFilePointer < length do
        if hduIndex >= maxHdus then throw ApiError("metadata_fits_limit", "Cached FITS exceeds the HDU metadata limit")
        val offset = file.getFilePointer
        val raw = List.newBuilder[String]
        var ended = false
        var count = 0
        while !ended do
          if totalCards >= maxCards then throw ApiError("metadata_fits_limit", "Cached FITS exceeds the header card limit")
          val bytes = new Array[Byte](80)
          file.readFully(bytes)
          val line = new String(bytes, US_ASCII)
          if count == 0 && (if hduIndex == 0 then !line.startsWith("SIMPLE  =") else !line.startsWith("XTENSION=")) then invalid("Invalid FITS HDU signature")
          raw += line
          ended = line.take(8).trim == "END"
          count += 1
          totalCards += 1
        val lines = raw.result()
        val header = new Header(lines.toArray)
        val naxis = header.getIntValue("NAXIS", -1)
        val bitpix = header.getIntValue("BITPIX", 0)
        if naxis < 0 || naxis > 999 || !Set(8, 16, 32, 64, -32, -64).contains(bitpix) || (hduIndex == 0 && !header.getBooleanValue("SIMPLE")) then invalid("Invalid FITS structure")
        val axes = (1 to naxis).map(axis => header.getLongValue(s"NAXIS$axis", -1L))
        if axes.exists(_ < 0) || header.getLongValue("PCOUNT", 0L) < 0 || header.getLongValue("GCOUNT", 1L) < 1 then invalid("Invalid FITS data dimensions")
        val dataOffset = offset + ((count.toLong * 80 + 2879) / 2880) * 2880
        val shape = if header.getBooleanValue("GROUPS") && axes.headOption.contains(0L) then axes.drop(1) else axes
        val pixels = if naxis == 0 then BigInt(0) else shape.foldLeft(BigInt(1))(_ * _)
        val expectedBytes = if naxis == 0 then BigInt(0) else
          BigInt(math.abs(bitpix) / 8) * header.getLongValue("GCOUNT", 1L) * (pixels + header.getLongValue("PCOUNT", 0L))
        val paddedBytes = ((expectedBytes + 2879) / 2880) * 2880
        if !paddedBytes.isValidLong || paddedBytes > BigInt(length) - dataOffset then invalid("Cached FITS has overflowing or truncated data dimensions")
        val dataSize = header.getDataSize
        if dataSize < 0 || BigInt(dataSize) != paddedBytes then invalid("Cached FITS has an inconsistent data segment size")
        val cards = lines.map { line =>
          val card = HeaderCard.create(line)
          obj("key" -> str(card.getKey), "value" -> cardValue(card), "comment" -> str(card.getComment), "raw" -> Json.Str(line))
        }
        hdus += obj("index" -> Json.Num(hduIndex), "name" -> str(header.getStringValue("EXTNAME")),
          "type" -> Json.Str(if hduIndex == 0 then "PRIMARY" else header.getStringValue("XTENSION", "UNKNOWN").trim),
          "bitpix" -> Json.Num(bitpix), "axes" -> arr(axes.map(n => Json.Num(n))),
          "header_offset_bytes" -> Json.Num(offset), "data_offset_bytes" -> Json.Num(dataOffset), "data_size_bytes" -> Json.Num(dataSize), "cards" -> arr(cards))
        file.seek(dataOffset + dataSize)
        hduIndex += 1
      obj("status" -> Json.Str("available"), "hdus" -> arr(hdus.result()))
    finally file.close()
  }.mapError {
    case error: ApiError => error
    case _ => ApiError("metadata_invalid_fits", "Cached FITS headers could not be read")
  }
