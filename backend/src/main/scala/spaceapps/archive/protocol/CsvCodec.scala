package spaceapps.archive.protocol
import spaceapps.archive.*
import java.nio.charset.StandardCharsets.UTF_8
object CsvCodec:
  /** RFC4180 quoting, embedded newlines and empty values; IDs never pass through numbers. */
  def decode(bytes: Array[Byte],required: Set[String]): List[Map[String,String]] =
    if bytes.isEmpty || bytes.length>8*1024*1024 then throw ArchiveFailure("invalid_response","Empty or oversized CSV metadata")
    val text=new String(bytes,UTF_8).stripPrefix("\uFEFF")
    val rows=List.newBuilder[List[String]];val cells=List.newBuilder[String];val value=new StringBuilder
    var quoted=false;var i=0;var rowOpen=false
    while i<text.length do
      val c=text.charAt(i)
      if c=='"' then
        if quoted && i+1<text.length && text.charAt(i+1)=='"' then {value+='"';i+=1}
        else if quoted || value.isEmpty then quoted = !quoted
        else throw ArchiveFailure("invalid_response","Malformed CSV quoting")
        rowOpen=true
      else if !quoted && c==',' then {cells+=value.toString;value.clear();rowOpen=true}
      else if !quoted && (c=='\n' || c=='\r') then
        if c=='\r' && i+1<text.length && text.charAt(i+1)=='\n' then i+=1
        if rowOpen || value.nonEmpty then {cells+=value.toString;rows+=cells.result();cells.clear();value.clear();rowOpen=false}
      else {value+=c;rowOpen=true}
      i+=1
    if quoted then throw ArchiveFailure("invalid_response","Truncated CSV quote")
    if rowOpen || value.nonEmpty then {cells+=value.toString;rows+=cells.result()}
    val all=rows.result()
    val header=all.headOption.getOrElse(throw ArchiveFailure("invalid_response","Missing CSV header"))
    if !required.subsetOf(header.toSet) || header.distinct.size!=header.size then throw ArchiveFailure("invalid_response","Unexpected CSV schema")
    all.tail.map { row=>
      if row.size!=header.size then throw ArchiveFailure("invalid_response","CSV row width mismatch")
      header.zip(row).filter(_._2.nonEmpty).toMap
    }
