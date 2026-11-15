package spaceapps.processing.repository

import spaceapps.processing.service.model.{UnificationJob,UnificationRecord}
import spaceapps.infra.model.ApiError
import zio.*
import zio.json.*
import zio.json.ast.Json
import java.nio.file.{Files,Path}
import java.sql.{Connection,DriverManager}
import java.util.UUID

final class UnificationRepository private(database:Path):
  private def tx[A](f:Connection=>A):Task[A]=ZIO.attemptBlocking {
    val c=DriverManager.getConnection(s"jdbc:sqlite:${database.toAbsolutePath}")
    try
      val s=c.createStatement()
      try {s.execute("PRAGMA busy_timeout=10000");s.execute("BEGIN IMMEDIATE")} finally s.close()
      try
        val result=f(c)
        val end=c.createStatement();try end.execute("COMMIT") finally end.close()
        result
      catch
        case e:Throwable=>val end=c.createStatement();try end.execute("ROLLBACK") finally end.close();throw e
    finally c.close()
  }
  private def read(c:Connection,id:String):UnificationRecord=
    val s=c.prepareStatement("SELECT body,request FROM unification_jobs WHERE id=?")
    try
      s.setString(1,id);val r=s.executeQuery()
      try
        if !r.next() then throw ApiError("not_found","Image unification job not found")
        UnificationRecord(r.getString(1).fromJson[UnificationJob].fold(_=>throw ApiError("storage_error","Invalid job state"),identity),r.getString(2).fromJson[Json].fold(_=>throw ApiError("storage_error","Invalid job request"),identity))
      finally r.close()
    finally s.close()
  private def save(c:Connection,job:UnificationJob):Unit=
    val s=c.prepareStatement("UPDATE unification_jobs SET status=?,body=? WHERE id=?")
    try {s.setString(1,job.status);s.setString(2,job.toJson);s.setString(3,job.id);s.executeUpdate();()} finally s.close()
  def accept(request:Json,limit:Int=8):Task[UnificationJob]=tx { c=>
    val s=c.createStatement();val r=s.executeQuery("SELECT COUNT(*) FROM unification_jobs WHERE status IN ('queued','running')")
    val active=try {r.next();r.getInt(1)} finally {r.close();s.close()}
    if active>=limit then throw ApiError("capacity_exceeded","Image unification queue is full",true)
    val id=UUID.randomUUID().toString
    val job=UnificationJob(id,"queued",s"/api/image-unifications/$id")
    val insert=c.prepareStatement("INSERT INTO unification_jobs(id,status,body,request) VALUES(?,?,?,?)")
    try {insert.setString(1,id);insert.setString(2,job.status);insert.setString(3,job.toJson);insert.setString(4,request.toJson);insert.executeUpdate()} finally insert.close()
    job
  }
  def get(id:String):Task[UnificationJob]=tx(c=>read(c,id).job)
  def update(job:UnificationJob):Task[Unit]=tx(c=>save(c,job))
  def claim:Task[Option[UnificationRecord]]=tx { c=>
    val s=c.createStatement();val r=s.executeQuery("SELECT id FROM unification_jobs WHERE status='queued' ORDER BY rowid LIMIT 1")
    val id=try Option.when(r.next())(r.getString(1)) finally {r.close();s.close()}
    id.map { value=>val record=read(c,value);val next=record.job.copy(status="running");save(c,next);record.copy(job=next) }
  }
  def recover:Task[List[String]]=tx { c=>
    val s=c.createStatement();val r=s.executeQuery("SELECT id FROM unification_jobs WHERE status IN ('queued','running')")
    val ids=try {val b=List.newBuilder[String];while r.next() do b+=r.getString(1);b.result()} finally {r.close();s.close()}
    ids.foreach(id=>save(c,read(c,id).job.copy(status="failed",artifact_url=None,error=Some(ApiError("interrupted","Image unification was interrupted; submit again",true)))))
    ids
  }
object UnificationRepository:
  def open(database:Path):Task[UnificationRepository]=ZIO.attemptBlocking {
    Files.createDirectories(database.toAbsolutePath.getParent)
    val c=DriverManager.getConnection(s"jdbc:sqlite:${database.toAbsolutePath}")
    try
      val s=c.createStatement()
      try {s.execute("PRAGMA busy_timeout=10000");s.execute("PRAGMA journal_mode=WAL");s.execute("CREATE TABLE IF NOT EXISTS unification_jobs(id TEXT PRIMARY KEY,status TEXT NOT NULL,body TEXT NOT NULL,request TEXT NOT NULL)")} finally s.close()
    finally c.close()
    new UnificationRepository(database)
  }
