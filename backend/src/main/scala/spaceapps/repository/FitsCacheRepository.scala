package spaceapps.repository

import java.nio.file.Path
import java.sql.{Connection,DriverManager}

/** Shares the jobs SQLite database; callers serialize filesystem changes with their cache coordinator. */
final class FitsCacheRepository(val databasePath:Path):
  private def connection[A](f:Connection=>A):A=
    val c=DriverManager.getConnection(s"jdbc:sqlite:${databasePath.toAbsolutePath}")
    try
      val s=c.createStatement()
      try s.execute("PRAGMA busy_timeout=10000") finally s.close()
      f(c)
    finally c.close()
  def initialize():Unit=connection { c=>
    val s=c.createStatement()
    try s.executeUpdate("CREATE TABLE IF NOT EXISTS fits_cache (identity TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, size_bytes INTEGER NOT NULL, last_accessed_at INTEGER NOT NULL)")
    finally s.close()
  }
  def entries():List[(String,Path,Long,Long)]=connection { c=>
    val s=c.createStatement()
    try
      val rs=s.executeQuery("SELECT identity,path,size_bytes,last_accessed_at FROM fits_cache ORDER BY last_accessed_at,identity")
      val out=List.newBuilder[(String,Path,Long,Long)]
      while rs.next() do out+=((rs.getString(1),Path.of(rs.getString(2)),rs.getLong(3),rs.getLong(4)))
      out.result()
    finally s.close()
  }
  def put(identity:String,path:Path,size:Long,accessed:Long):Unit=connection { c=>
    val s=c.prepareStatement("INSERT INTO fits_cache(identity,path,size_bytes,last_accessed_at) VALUES(?,?,?,?) ON CONFLICT(identity) DO UPDATE SET path=excluded.path,size_bytes=excluded.size_bytes,last_accessed_at=excluded.last_accessed_at")
    try
      s.setString(1,identity); s.setString(2,path.toString); s.setLong(3,size); s.setLong(4,accessed); s.executeUpdate(); ()
    finally s.close()
  }
  def remove(identity:String):Unit=connection { c=>
    val s=c.prepareStatement("DELETE FROM fits_cache WHERE identity=?")
    try
      s.setString(1,identity); s.executeUpdate(); ()
    finally s.close()
  }
