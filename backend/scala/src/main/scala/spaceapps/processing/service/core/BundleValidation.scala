package spaceapps.processing.service.core

import spaceapps.infra.model.ApiError
import java.nio.file.Path
import java.util.zip.ZipFile
import java.nio.charset.StandardCharsets.US_ASCII
import scala.jdk.CollectionConverters.*
import zio.json.*
import zio.json.ast.Json

/** Independent, bounded structural check before a private worker artifact becomes public. */
private[processing] object BundleValidation:
  private def invalid():Nothing=throw ApiError("invalid_output","Invalid or oversized NPZ bundle")
  def validate(path:Path,frames:Int,height:Int,width:Int,expectedManifest:Option[String]=None):Unit=
    val zip=new ZipFile(path.toFile)
    try
      val entries=zip.entries().asScala.toList
      if entries.isEmpty || entries.size>32 || entries.map(_.getName).distinct.size!=entries.size then invalid()
      val cubes=Set("images","tensor","valid_mask","footprint","variance","variance_valid_mask","outlier","bloom")
      val vectors=Set("times","time_known_mask","frame_ids","observation_ids","dates_utc")
      val required=(cubes++vectors++Set("manifest","schema_version")).map(_+".npy")
      if required!=entries.map(_.getName).toSet then invalid()
      var expanded=0L
      entries.foreach { entry=>
        if entry.isDirectory || !entry.getName.matches("[A-Za-z][A-Za-z0-9_]*[.]npy") || entry.getSize<10 || entry.getSize>192L*1024*1024 then invalid()
        expanded+=entry.getSize
        if expanded>192L*1024*1024 then invalid()
        val in=zip.getInputStream(entry)
        try
          val prefix=in.readNBytes(8)
          if prefix.length!=8 || prefix(0)!=0x93.toByte || new String(prefix.slice(1,6),US_ASCII)!="NUMPY" || !Set(1,2,3)(prefix(6).toInt) then invalid()
          val lengthBytes=in.readNBytes(if prefix(6)==1 then 2 else 4)
          if lengthBytes.length!=(if prefix(6)==1 then 2 else 4) then invalid()
          val length=lengthBytes.zipWithIndex.map((b,i)=>(b & 255).toLong << (8*i)).sum
          if length<=0 || length>65536 then invalid()
          val headerBytes=in.readNBytes(length.toInt)
          if headerBytes.length!=length then invalid()
          val header=new String(headerBytes,US_ASCII)
          // NumPy interprets the last duplicate dictionary key; accept one canonical
          // dictionary so independent validation and NumPy cannot disagree.
          val canonical="""(?s)\{\s*['"]descr['"]\s*:\s*['"][<>=|][?biufUS][0-9]+['"]\s*,\s*['"]fortran_order['"]\s*:\s*False\s*,\s*['"]shape['"]\s*:\s*\([0-9,\s]*\)\s*,?\s*\}\s*"""
          if !header.matches(canonical) then invalid()
          val dtype="['\"]descr['\"]\\s*:\\s*['\"]([^'\"]+)['\"]".r.findFirstMatchIn(header).map(_.group(1)).getOrElse(invalid())
          if !dtype.matches("[<>=|][?biufUS][0-9]+") || dtype.contains("O") || !header.matches("(?s).*['\"]fortran_order['\"]\\s*:\\s*False.*") then invalid()
          val shapeText="['\"]shape['\"]\\s*:\\s*\\(([^)]*)\\)".r.findFirstMatchIn(header).map(_.group(1)).getOrElse(invalid())
          val shape=shapeText.split(",").toList.map(_.trim).filter(_.nonEmpty).map(s=>s.toLongOption.filter(n=>n>=0 && n<=1000000).getOrElse(invalid()))
          val name=entry.getName.stripSuffix(".npy")
          if cubes(name) && shape!=List(frames.toLong,height.toLong,width.toLong) then invalid()
          if vectors(name) && shape!=List(frames.toLong) then invalid()
          if Set("images","tensor","footprint","variance")(name) && !dtype.matches("[<>=]f4") then invalid()
          if Set("valid_mask","variance_valid_mask","outlier","bloom","time_known_mask")(name) && dtype!="|b1" then invalid()
          if name=="times" && !dtype.matches("[<>=]f8") then invalid()
          val unicode=Map("frame_ids"->256,"observation_ids"->650,"dates_utc"->64)
          if unicode.contains(name) && !dtype.matches(s"[<>=]U${unicode(name)}") then invalid()
          if name=="schema_version" && (shape.nonEmpty || !dtype.matches("[<>=]i2")) then invalid()
          if name=="manifest" && (shape.size!=1 || shape.head<=0 || shape.head>1024*1024 || dtype!="|u1") then invalid()
          val elementSize=scala.util.Try(dtype.drop(2).toLong).getOrElse(invalid())*(if dtype(1)=='U' then 4 else 1)
          if elementSize<=0 || elementSize>1024*1024 then invalid()
          val count=shape.foldLeft(BigInt(1))(_*_)
          val expected=count*elementSize
          if expected>192L*1024*1024 || expected+8+lengthBytes.length+length!=entry.getSize then invalid()
          val small=if name=="manifest" || name=="schema_version" then Some(new java.io.ByteArrayOutputStream()) else None
          val buffer=new Array[Byte](65536);var actual=8L+lengthBytes.length+length;var n=in.read(buffer)
          while n>=0 do
            actual+=n
            small.foreach(_.write(buffer,0,n))
            if actual>entry.getSize then invalid()
            n=in.read(buffer)
          if actual!=entry.getSize then invalid()
          if name=="schema_version" then
            val bytes=small.get.toByteArray
            if bytes.toList!=(if dtype.startsWith(">") then List[Byte](0,1) else List[Byte](1,0)) then invalid()
          if name=="manifest" then
            val embedded=new String(small.get.toByteArray,java.nio.charset.StandardCharsets.UTF_8).fromJson[Json].fold(_=>invalid(),identity)
            expectedManifest.foreach { text=>if text.fromJson[Json].toOption!=Some(embedded) then invalid() }
        finally in.close()
      }
    finally zip.close()
