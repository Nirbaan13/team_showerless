package spaceapps.infra.bootstrap

import spaceapps.infra.model.ApiError
import zio.*
import zio.test.*

object RuntimeConcurrencySpec extends ZIOSpecDefault:
  def spec=suite("Processing runtime concurrency")(
    test("accepts the low memory limit and existing default") {
      assertTrue(Application.parseProcessingConcurrency("1")==1,
        Application.parseProcessingConcurrency("2")==2,
        Application.parseProcessingConcurrency("4")==4)
    },
    test("rejects invalid configuration with the environment variable name") {
      ZIO.foreach(List("0","5","many","","1.5")) { raw=>
        ZIO.attempt(Application.parseProcessingConcurrency(raw)).exit.map {
          case Exit.Failure(cause)=>assertTrue(cause.failureOption.exists {
            case e:ApiError=>e.code=="invalid_configuration" && e.message.contains("PROCESSING_CONCURRENCY")
            case _=>false
          })
          case _=>assertTrue(false)
        }
      }.map(results=>results.reduce(_ && _))
    }
  )
