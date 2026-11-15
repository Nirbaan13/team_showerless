package spaceapps.downloads.integrations.protocol
import spaceapps.downloads.model.*
import java.io.ByteArrayInputStream
import javax.xml.XMLConstants
import javax.xml.parsers.DocumentBuilderFactory
import org.w3c.dom.Element
import org.xml.sax.{ErrorHandler,SAXParseException}

final case class VoTable(rows: List[Map[String,String]], completeness: Completeness, root: Element)
object VOTableCodec:
  def elements(node: Element,name: String): List[Element] =
    val n=node.getElementsByTagNameNS("*",name)
    (0 until n.getLength).map(i=>n.item(i).asInstanceOf[Element]).toList
  def children(node: Element,name: String): List[Element] =
    val n=node.getChildNodes
    (0 until n.getLength).flatMap(i=>n.item(i) match
      case e: Element if Option(e.getLocalName).getOrElse(e.getTagName)==name=>Some(e)
      case _=>None).toList
  def decode(bytes: Array[Byte],maxBytes: Long = 8L*1024*1024,requireStatus: Boolean = true): VoTable =
    def invalid(message: String): Nothing = throw ArchiveFailure("invalid_response",message)
    if bytes.isEmpty || bytes.length>maxBytes then invalid("Metadata is empty or exceeds byte budget")
    val factory=DocumentBuilderFactory.newInstance()
    factory.setNamespaceAware(true)
    factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING,true)
    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl",true)
    factory.setFeature("http://xml.org/sax/features/external-general-entities",false)
    factory.setFeature("http://xml.org/sax/features/external-parameter-entities",false)
    factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD,"")
    factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA,"")
    factory.setXIncludeAware(false);factory.setExpandEntityReferences(false)
    val parser=factory.newDocumentBuilder()
    parser.setErrorHandler(new ErrorHandler:
      def warning(e: SAXParseException): Unit = ()
      def error(e: SAXParseException): Unit = throw e
      def fatalError(e: SAXParseException): Unit = throw e)
    val root=try parser.parse(new ByteArrayInputStream(bytes)).getDocumentElement catch case _: Exception=>invalid("Malformed or unsafe VOTable XML")
    if Option(root.getLocalName).getOrElse(root.getTagName)!="VOTABLE" then invalid("Expected VOTable, received another document")
    val statuses=elements(root,"INFO").filter(_.getAttribute("name").equalsIgnoreCase("QUERY_STATUS")).map(_.getAttribute("value").toUpperCase(java.util.Locale.ROOT))
    if statuses.contains("ERROR") then throw ArchiveFailure("query_error","Archive rejected the query")
    if (requireStatus && statuses.isEmpty) || statuses.exists(s=>s!="OK" && s!="OVERFLOW") then invalid("Missing or unrecognized query status")
    val table=elements(root,"TABLE").headOption.getOrElse(invalid("Missing result table"))
    val fields=children(table,"FIELD").map(_.getAttribute("name").toLowerCase(java.util.Locale.ROOT))
    if fields.isEmpty || fields.distinct.size!=fields.size then invalid("Missing or duplicate table fields")
    if List("BINARY","BINARY2","FITS").exists(n=>elements(table,n).nonEmpty) then throw ArchiveFailure("unsupported_serialization","Only bounded TABLEDATA is qualified")
    if elements(table,"TABLEDATA").size!=1 then invalid("Missing TABLEDATA")
    val rows=elements(table,"TR").map { row=>
      val values=children(row,"TD").map(_.getTextContent.trim)
      if values.size!=fields.size then invalid("Inconsistent table row width")
      fields.zip(values).filter(_._2.nonEmpty).toMap
    }
    VoTable(rows,if statuses.contains("OVERFLOW") then Completeness.truncated else Completeness.complete,root)
