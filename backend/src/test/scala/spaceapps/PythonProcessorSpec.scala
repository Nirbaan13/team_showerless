package spaceapps

import spaceapps.domain.*
import spaceapps.integrations.processing.PythonProcessor
import zio.*
import zio.test.*
import java.nio.file.{Files,Path,Paths}
import nom.tam.fits.Fits

object PythonProcessorSpec extends ZIOSpecDefault:
  private val python = sys.env.getOrElse("PROCESSING_PYTHON", {
    val shared=Paths.get(java.lang.System.getProperty("user.home"),"edu","UtilsAI",".venv","bin","python")
    if Files.isExecutable(shared) then shared.toString else "python3"
  })
  private def source(dir:Path):Task[Path]=ZIO.attemptBlocking {
    val path=dir.resolve("native.fits")
    val input=getClass.getResourceAsStream("/processing/native_fixture.fits")
    try Files.copy(input,path) finally input.close()
    path
  }
  private def processor=PythonProcessor.make(python,Paths.get("processing/worker.py"),Paths.get("../pipeline"))
  def spec=suite("Supervised Python processing")(
    test("a timed out worker is terminated and cannot retain the native-file processing scope") {
      for
        dir <- ZIO.attempt(Files.createTempDirectory("python-timeout-"))
        input <- source(dir)
        script=dir.resolve("slow.py")
        _ <- ZIO.attempt(Files.writeString(script,"""import json,os,sys,time
r=json.load(sys.stdin)
if r['operation']=='capabilities':
 print(json.dumps({'status':'ok','operations':['preview','zodi']}))
else:
 with open(r['output_path']+'.pid','w') as f:f.write(str(os.getpid()))
 time.sleep(600)
"""))
        service <- PythonProcessor.make(python,script,Paths.get("../pipeline"),timeout=1.second)
        result <- service.preview(input,dir.resolve("never.png")).either
        dead <- ZIO.attempt {
          val pid=Files.readString(dir.resolve("never.png.pid")).toLong
          val process=ProcessHandle.of(pid)
          !process.isPresent || !process.get().isAlive
        }
      yield assertTrue(result.left.toOption.exists {case e:ApiError=>e.code=="processing_timeout";case _=>false},dead)
    },
    test("excessive worker output is rejected instead of filling memory or producing a false success") {
      for
        dir <- ZIO.attempt(Files.createTempDirectory("python-output-"))
        input <- source(dir)
        script=dir.resolve("noisy.py")
        _ <- ZIO.attempt(Files.writeString(script,"""import json,sys
r=json.load(sys.stdin)
if r['operation']=='capabilities':print(json.dumps({'status':'ok','operations':['preview','zodi']}))
else:print('x'*200000)
"""))
        service <- PythonProcessor.make(python,script,Paths.get("../pipeline"),timeout=5.seconds)
        result <- service.preview(input,dir.resolve("never.png")).either
      yield assertTrue(result.left.toOption.exists {case e:ApiError=>e.code=="processing_protocol";case _=>false},!Files.exists(dir.resolve("never.png")))
    },
    test("real native FITS produces PNG and exactly one ZODI subtraction without changing source bytes") {
      for
        dir <- ZIO.attempt(Files.createTempDirectory("python-process-"))
        input <- source(dir)
        before <- ZIO.attempt(Files.readAllBytes(input).toList)
        service <- processor
        _ <- service.preview(input,dir.resolve("preview.png"))
        _ <- service.prepare(input,dir.resolve("clean.fits"),"zodi_reference_subtracted",None,Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get)
        _ <- service.preview(dir.resolve("clean.fits"),dir.resolve("clean.png"))
        values <- ZIO.attemptBlocking {
          val fits=new Fits(dir.resolve("clean.fits").toFile)
          try
            val hdus=fits.read();val image=hdus.find(_.getHeader.getStringValue("EXTNAME","")=="IMAGE").get
            val pixels=image.getKernel.asInstanceOf[Array[Array[Double]]]
            (pixels(0)(0),pixels(4)(4),image.getHeader.getBooleanValue("ZODISUB"),hdus.length)
          finally fits.close()
        }
        after <- ZIO.attempt(Files.readAllBytes(input).toList)
        png <- ZIO.attempt(Files.readAllBytes(dir.resolve("preview.png")).take(8).toList)
      yield assertTrue(service.supportsPreview,service.supportedModes.contains("zodi_reference_subtracted"),
        before==after,png==List[Byte](-119,80,78,71,13,10,26,10),values._1==8.0,values._2==18.0,values._3,values._4>=5)
    },
    test("scientific failures do not become generated replacement images") {
      for
        dir <- ZIO.attempt(Files.createTempDirectory("python-errors-"))
        invalid=dir.resolve("invalid.fits")
        _ <- ZIO.attempt(Files.writeString(invalid,"not a FITS"))
        service <- processor
        failed <- service.preview(invalid,dir.resolve("output.png")).either
        output <- ZIO.attempt(Files.exists(dir.resolve("output.png")))
      yield assertTrue(failed.isLeft,!output)
    },
    test("unsupported epoch differences fail before launching scientific processing") {
      for
        dir <- ZIO.attempt(Files.createTempDirectory("python-mode-"))
        input <- source(dir)
        service <- processor
        result <- service.prepare(input,dir.resolve("difference.fits"),"epoch_difference",None,Query.fromParameters("default",Map("right_ascension_deg"->"1","declination_deg"->"2")).toOption.get).either
      yield assertTrue(result.left.toOption.exists {case e:ApiError=>e.code=="unsupported_processing";case _=>false},!Files.exists(dir.resolve("difference.fits")))
    }
  ) @@ TestAspect.withLiveClock
