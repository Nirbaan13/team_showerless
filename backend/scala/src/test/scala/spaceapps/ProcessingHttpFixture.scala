package spaceapps

import spaceapps.integrations.processing.HttpProcessingClient
import zio.*
import java.net.{ServerSocket,URI}
import java.net.http.{HttpClient,HttpRequest,HttpResponse}
import java.nio.file.{Files,Path,Paths}
import java.util.concurrent.TimeUnit

/** Tests run the real pipeline HTTP server; production Scala never starts Python. */
object ProcessingHttpFixture:
  def start(data:Path):ZIO[Scope,Throwable,HttpProcessingClient]=
    for
      port<-ZIO.attempt {val s=new ServerSocket(0);try s.getLocalPort finally s.close()}
      root=Paths.get("../pipeline").toAbsolutePath.normalize
      python=sys.env.getOrElse("PROCESSING_PYTHON",Paths.get(sys.props("user.home"),"edu/UtilsAI/.venv/bin/python").toString)
      log=data.resolve("pipeline-test.log")
      process<-ZIO.acquireRelease(ZIO.attemptBlocking {
        val b=new ProcessBuilder(python,"-m","uvicorn","service:app","--host","127.0.0.1","--port",port.toString)
        b.directory(root.toFile);b.environment().put("PYTHONPATH",root.toString)
        b.environment().put("PROCESSING_DATA_ROOT",data.toAbsolutePath.toString)
        b.environment().put("OPENBLAS_NUM_THREADS","1");b.environment().put("OMP_NUM_THREADS","1")
        b.redirectErrorStream(true);b.redirectOutput(log.toFile);b.start()
      })(p=>ZIO.attemptBlocking {
        p.descendants().forEach(_.destroyForcibly());p.destroy()
        if !p.waitFor(3,TimeUnit.SECONDS) then {p.destroyForcibly();p.waitFor(2,TimeUnit.SECONDS)}
        ()
      }.ignore)
      base=s"http://127.0.0.1:$port"
      client=HttpClient.newHttpClient()
      _<-ZIO.attemptBlocking {
        val response=client.send(HttpRequest.newBuilder(URI.create(base+"/internal/capabilities")).timeout(java.time.Duration.ofSeconds(1)).GET().build(),HttpResponse.BodyHandlers.discarding())
        if response.statusCode()!=200 then throw new RuntimeException("Pipeline not ready")
      }.retry(Schedule.spaced(50.millis) && Schedule.recurs(200))
        .mapError(e=>new RuntimeException("Pipeline HTTP fixture could not start: "+scala.util.Try(Files.readString(log)).getOrElse(e.toString)))
      service<-HttpProcessingClient.make(base)
    yield service
