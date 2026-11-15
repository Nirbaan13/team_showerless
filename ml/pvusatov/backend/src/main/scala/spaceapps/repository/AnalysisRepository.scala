package spaceapps.repository

import spaceapps.domain.*
import zio.*
import zio.json.*
import java.nio.file.{Files,Path}
import java.sql.{Connection,DriverManager}
import java.util.UUID

final class AnalysisRepository private(path:Path):
  private def tx[A](f:Connection=>A):Task[A]=ZIO.attemptBlocking {
    val c=DriverManager.getConnection(s"jdbc:sqlite:${path.toAbsolutePath}")
    try
      val s=c.createStatement();try {s.execute("PRAGMA busy_timeout=10000");s.execute("BEGIN IMMEDIATE")} finally s.close()
      try
        val a=f(c);val s=c.createStatement();try s.execute("COMMIT") finally s.close();a
      catch
        case e:Throwable=>val s=c.createStatement();try s.execute("ROLLBACK") finally s.close();throw e
    finally c.close()
  }
  private def sql(c:Connection,s:String,args:Any*):Unit=
    val p=c.prepareStatement(s);try {args.zipWithIndex.foreach((a,i)=>p.setObject(i+1,a));p.executeUpdate();()} finally p.close()
  private def rows(c:Connection,s:String,args:Any*):List[(String,Long)]=
    val p=c.prepareStatement(s)
    try
      args.zipWithIndex.foreach((a,i)=>p.setObject(i+1,a));val r=p.executeQuery();val b=List.newBuilder[(String,Long)]
      try while r.next() do b+=((r.getString(1),if r.getMetaData.getColumnCount>1 then r.getLong(2) else 0L)) finally r.close()
      b.result()
    finally p.close()
  private def decode(s:String)=s.fromJson[AnalysisRecord].fold(_=>throw ApiError("storage_error","Stored analysis metadata is invalid"),identity)
  private def load(c:Connection,id:String)=rows(c,"SELECT body FROM analysis_jobs WHERE id=?",id).headOption.map(r=>decode(r._1)).getOrElse(throw ApiError("not_found","Analysis not found"))
  private def store(c:Connection,r:AnalysisRecord):Unit=
    sql(c,"UPDATE analysis_jobs SET status=?,body=? WHERE id=?",r.analysis.status,r.toJson,r.analysis.id)
    sql(c,"INSERT INTO analysis_events(job_id,data) VALUES (?,?)",r.analysis.id,r.analysis.toJson)
  def accept(request:AnalysisRequest,key:String,max:Int,modelHash:Option[String]=None,modelId:Option[String]=None):Task[Analysis]=tx {c=>
    rows(c,"SELECT body FROM analysis_jobs WHERE request_key=? AND status!='failed' ORDER BY rowid DESC LIMIT 1",key).headOption match
      case Some((body,_))=>decode(body).analysis
      case None=>
        val count=rows(c,"SELECT CAST(COUNT(*) AS TEXT) FROM analysis_jobs WHERE status NOT IN ('completed','failed')").head._1.toInt
        if count>=max then throw ApiError("capacity_exceeded","The analysis queue is full; retry later",true)
        val id=UUID.randomUUID().toString
        val a=Analysis(id,"queued",request.download_id,s"/api/analyses/$id",s"/api/analyses/$id/events")
        val r=AnalysisRecord(a,request,key,modelHash,modelId)
        sql(c,"INSERT INTO analysis_jobs(id,request_key,status,body) VALUES (?,?,?,?)",id,key,a.status,r.toJson)
        sql(c,"INSERT INTO analysis_events(job_id,data) VALUES (?,?)",id,a.toJson)
        a
  }
  def get(id:String):Task[Analysis]=record(id).map(_.analysis)
  def record(id:String):Task[AnalysisRecord]=tx(load(_,id))
  def pending:Task[List[AnalysisRecord]]=tx(c=>rows(c,"SELECT body FROM analysis_jobs WHERE status IN ('queued','waiting_for_download') ORDER BY rowid LIMIT 64").map(r=>decode(r._1)))
  def update(id:String)(f:Analysis=>Analysis):Task[Analysis]=tx {c=>val r=load(c,id);val next=r.copy(analysis=f(r.analysis));store(c,next);next.analysis}
  def recover:Task[Unit]=tx {c=>
    rows(c,"SELECT body FROM analysis_jobs WHERE status IN ('preparing','inferencing')").foreach { (body,_)=>
      val r=decode(body);store(c,r.copy(analysis=r.analysis.copy(status="failed",error=Some(ApiError("analysis_interrupted","Analysis was interrupted by service restart; resubmit to retry",true)))))
    }
  }
  def snapshot(id:String):Task[(Analysis,Long)]=tx(c=>(load(c,id).analysis,rows(c,"SELECT CAST(COALESCE(MAX(sequence),0) AS TEXT) FROM analysis_events WHERE job_id=?",id).head._1.toLong))
  def events(id:String,cursor:Long):Task[List[Event]]=tx(c=>rows(c,"SELECT data,sequence FROM analysis_events WHERE job_id=? AND sequence>? ORDER BY sequence LIMIT 64",id,cursor).map { (body,seq)=>
    val a=body.fromJson[Analysis].toOption.get;Event(seq,if a.terminal then "analysis.completed" else "analysis.updated",body)
  })
object AnalysisRepository:
  def open(path:Path):Task[AnalysisRepository]=ZIO.attemptBlocking {
    Option(path.toAbsolutePath.getParent).foreach(Files.createDirectories(_))
    val c=DriverManager.getConnection(s"jdbc:sqlite:${path.toAbsolutePath}")
    try
      val s=c.createStatement()
      try
        s.execute("PRAGMA journal_mode=WAL");s.execute("PRAGMA busy_timeout=10000")
        s.execute("CREATE TABLE IF NOT EXISTS analysis_jobs(id TEXT PRIMARY KEY,request_key TEXT NOT NULL,status TEXT NOT NULL,body TEXT NOT NULL)")
        s.execute("CREATE INDEX IF NOT EXISTS analysis_request ON analysis_jobs(request_key)")
        s.execute("CREATE TABLE IF NOT EXISTS analysis_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL,data TEXT NOT NULL)")
        s.execute("CREATE INDEX IF NOT EXISTS analysis_event_job ON analysis_events(job_id,sequence)")
      finally s.close()
    finally c.close()
    new AnalysisRepository(path)
  }
