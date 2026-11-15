package spaceapps

import spaceapps.infra.model.ApiError
import spaceapps.infra.service.ExternalServices
import spaceapps.infra.integrations.ExternalServiceProbes
import zio.http.Client
import com.sun.net.httpserver.HttpServer
import java.net.{InetSocketAddress, URLDecoder}
import java.nio.charset.StandardCharsets.UTF_8
import java.util.concurrent.atomic.AtomicReference
import zio.*
import zio.json.ast.Json
import zio.test.*

object ExternalServicesSpec extends ZIOSpecDefault:
  private def field(json: Json, names: String*): Json = names.foldLeft(json) { (value, name) => value match
    case Json.Obj(fields) => fields.find(_._1 == name).map(_._2).getOrElse(Json.Null)
    case _ => Json.Null
  }
  private def state(services: ExternalServices, name: String): UIO[Json] = services.status.map(field(_, "services", name, "state"))
  private def ready(services: ExternalServices, name: String): UIO[Unit] =
    state(services, name).repeatUntil(_ == Json.Str("closed")).unit
  private def code(result: Either[Throwable, Any]): Option[String] = result.left.toOption.collect { case e: ApiError => e.code }

  private val siaDocument = """<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE type="results"><INFO name="QUERY_STATUS" value="OK"/><TABLE><FIELD name="obs_publisher_did" datatype="char" arraysize="*"/><FIELD name="access_url" datatype="char" arraysize="*"/><FIELD name="obs_collection" datatype="char" arraysize="*"/><FIELD name="energy_bandpassname" datatype="char" arraysize="*"/><FIELD name="t_min" datatype="double"/><DATA><TABLEDATA/></DATA></TABLE><INFO name="QUERY_STATUS" value="OVERFLOW"/></RESOURCE></VOTABLE>"""
  private val siaOverflowOnly = siaDocument.replace("<INFO name=\"QUERY_STATUS\" value=\"OK\"/>", "")
    .replace("<TABLEDATA/>", "<TABLEDATA><TR><TD>ivo://irsa/spherex/one</TD><TD>https://irsa.ipac.caltech.edu/ibe/data/one.fits</TD><TD>spherex_dr1</TD><TD>SPHEREx-D1</TD><TD>60800</TD></TR></TABLEDATA>")
  private val tapDocument = """<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE type="results"><INFO name="QUERY_STATUS" value="OK"/><TABLE><FIELD name="table_name" datatype="char" arraysize="*"/><DATA><TABLEDATA><TR><TD>spherex.artifact</TD></TR></TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>"""
  private def withProbe(document: String, key: String, status: Int = 200)(use: (Task[Unit], AtomicReference[String]) => ZIO[Scope, Throwable, TestResult]): ZIO[Client, Throwable, TestResult] = ZIO.scoped {
    for
      query <- ZIO.succeed(new AtomicReference[String](""))
      server <- ZIO.acquireRelease(ZIO.attempt {
        val server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/probe", exchange => {
          query.set(URLDecoder.decode(exchange.getRequestURI.getRawQuery, UTF_8))
          val body = document.getBytes(UTF_8)
          exchange.sendResponseHeaders(status, body.length.toLong)
          try exchange.getResponseBody.write(body) finally exchange.close()
        })
        server.start()
        server
      })(server => ZIO.succeed(server.stop(0)))
      client <- ZIO.service[Client]
      endpoint = s"http://127.0.0.1:${server.getAddress.getPort}/probe"
      probes = ExternalServiceProbes.irsa(client, endpoint, endpoint)
      result <- use(probes(key), query)
    yield result
  }

  def spec = suite("Independent external service circuits")(
    test("unknown services remain open while the startup probe has not succeeded") {
      ZIO.scoped {
        for
          services <- ExternalServices.make(Map("irsa_sia" -> ZIO.never))
          executed <- Ref.make(false)
          result <- services.call("irsa_sia")(executed.set(true)).either
          ran <- executed.get
          snapshot <- services.status
        yield assertTrue(code(result).contains("archive_circuit_open"), !ran,
          field(snapshot, "preferred_route") == Json.Str("s3_mirror"))
      }
    },
    test("a transport failure opens only its own circuit and requests never probe") {
      ZIO.scoped {
        for
          services <- ExternalServices.make(Map("irsa_sia" -> ZIO.unit, "irsa_tap" -> ZIO.unit))
          _ <- ready(services, "irsa_sia") *> ready(services, "irsa_tap")
          _ <- services.call("irsa_sia")(ZIO.fail(new java.net.ConnectException("offline"))).either
          attempts <- Ref.make(0)
          rejected <- ZIO.foreach(1 to 5)(_ => services.call("irsa_sia")(attempts.update(_ + 1)).either)
          count <- attempts.get
          tap <- services.call("irsa_tap")(ZIO.succeed("metadata"))
          current <- state(services, "irsa_sia")
        yield assertTrue(count == 0, rejected.forall(result => code(result).contains("archive_circuit_open")),
          tap == "metadata", current == Json.Str("open"))
      }
    },
    test("query validation and record overflow leave a healthy circuit closed") {
      ZIO.scoped {
        for
          services <- ExternalServices.make(Map("irsa_sia" -> ZIO.unit))
          _ <- ready(services, "irsa_sia")
          _ <- services.call("irsa_sia")(ZIO.fail(ApiError("archive_overflow", "narrow the region"))).either
          _ <- services.call("irsa_sia")(ZIO.fail(ApiError("archive_query_error", "invalid query"))).either
          value <- services.call("irsa_sia")(ZIO.succeed(42))
        yield assertTrue(value == 42)
      }
    },
    test("HTTP service failures open the circuit and only successful probes restore traffic") {
      ZIO.scoped {
        for
          healthy <- Ref.make(true)
          probe = healthy.get.flatMap(ok => if ok then ZIO.unit else ZIO.fail(new java.io.IOException("down")))
          services <- ExternalServices.make(Map("irsa_tap" -> probe))
          _ <- ready(services, "irsa_tap")
          _ <- services.call("irsa_tap")(ZIO.fail(ApiError("metadata_http_error", "HTTP 503", true))).either
          _ <- healthy.set(false)
          _ <- services.checkNow("irsa_tap")
          blocked <- services.call("irsa_tap")(ZIO.unit).either
          _ <- healthy.set(true)
          _ <- services.checkNow("irsa_tap")
          restored <- services.call("irsa_tap")(ZIO.succeed("restored"))
          snapshot <- services.status
        yield assertTrue(code(blocked).contains("archive_circuit_open"), restored == "restored",
          field(snapshot, "services", "irsa_tap", "last_success") != Json.Null,
          field(snapshot, "services", "irsa_tap", "last_error") == Json.Null)
      }
    },
    test("hourly checks restore an open service even with no user traffic") {
      ZIO.scoped {
        for
          healthy <- Ref.make(false)
          calls <- Ref.make(0)
          probe = calls.update(_ + 1) *> healthy.get.flatMap(ok => if ok then ZIO.unit else ZIO.fail(new java.io.IOException("offline")))
          services <- ExternalServices.make(Map("irsa_sia" -> probe))
          _ <- services.status.repeatUntil(json => field(json, "services", "irsa_sia", "last_check") != Json.Null)
          _ <- healthy.set(true)
          _ <- TestClock.adjust(59.minutes)
          before <- calls.get
          _ <- TestClock.adjust(1.minute)
          _ <- ready(services, "irsa_sia")
          after <- calls.get
          snapshot <- services.status
        yield assertTrue(before == 1, after == 2,
          field(snapshot, "preferred_route") == Json.Str("irsa_sia"),
          field(snapshot, "services", "irsa_sia", "next_check") != Json.Null)
      }
    },
    test("late request success cannot close a circuit opened by a concurrent failure") {
      ZIO.scoped {
        for
          services <- ExternalServices.make(Map("irsa_sia" -> ZIO.unit))
          _ <- ready(services, "irsa_sia")
          started <- Promise.make[Nothing, Unit]
          release <- Promise.make[Nothing, Unit]
          pending <- services.call("irsa_sia")(started.succeed(()) *> release.await).fork
          _ <- started.await
          _ <- services.call("irsa_sia")(ZIO.fail(new java.net.ConnectException("offline"))).either
          _ <- release.succeed(()) *> pending.join
          blocked <- services.call("irsa_sia")(ZIO.unit).either
        yield assertTrue(code(blocked).contains("archive_circuit_open"))
      }
    },
    test("a stale successful probe cannot erase a newer transport failure") {
      ZIO.scoped {
        for
          probing <- Ref.make(false)
          started <- Promise.make[Nothing, Unit]
          release <- Promise.make[Nothing, Unit]
          probe = probing.get.flatMap(active => if active then started.succeed(()) *> release.await else ZIO.unit)
          services <- ExternalServices.make(Map("irsa_sia" -> probe))
          _ <- ready(services, "irsa_sia")
          _ <- probing.set(true)
          pending <- services.checkNow("irsa_sia").fork
          _ <- started.await
          _ <- services.call("irsa_sia")(ZIO.fail(new java.io.IOException("new outage"))).either
          _ <- release.succeed(()) *> pending.join
          blocked <- services.call("irsa_sia")(ZIO.unit).either
          _ <- probing.set(false) *> services.checkNow("irsa_sia")
          restored <- services.call("irsa_sia")(ZIO.succeed(true))
        yield assertTrue(code(blocked).contains("archive_circuit_open"), restored)
      }
    },
    test("cancelling a manual probe releases the single-flight guard") {
      ZIO.scoped {
        for
          hang <- Ref.make(false)
          entered <- Promise.make[Nothing, Unit]
          probe = hang.get.flatMap(active => if active then entered.succeed(()) *> ZIO.never else ZIO.unit)
          services <- ExternalServices.make(Map("irsa_sia" -> probe))
          _ <- ready(services, "irsa_sia")
          _ <- services.call("irsa_sia")(ZIO.fail(new java.io.IOException("offline"))).either
          _ <- hang.set(true)
          pending <- services.checkNow("irsa_sia").fork
          _ <- entered.await *> pending.interrupt
          _ <- hang.set(false) *> services.checkNow("irsa_sia")
          restored <- services.call("irsa_sia")(ZIO.succeed(true))
        yield assertTrue(restored)
      }
    }
    ,
    test("concurrent health checks share one in-flight probe") {
      ZIO.scoped {
        for
          blocked <- Ref.make(false)
          calls <- Ref.make(0)
          entered <- Promise.make[Nothing, Unit]
          release <- Promise.make[Nothing, Unit]
          probe = calls.update(_ + 1) *> blocked.get.flatMap(active => if active then entered.succeed(()) *> release.await else ZIO.unit)
          services <- ExternalServices.make(Map("irsa_sia" -> probe))
          _ <- ready(services, "irsa_sia")
          _ <- blocked.set(true)
          first <- services.checkNow("irsa_sia").fork
          _ <- entered.await
          _ <- ZIO.foreachParDiscard(1 to 10)(_ => services.checkNow("irsa_sia"))
          count <- calls.get
          _ <- release.succeed(()) *> first.join
        yield assertTrue(count == 2)
      }
    },
    test("a stuck probe times out and leaves traffic on the mirror") {
      ZIO.scoped {
        for
          entered <- Promise.make[Nothing, Unit]
          services <- ExternalServices.make(Map("irsa_sia" -> (entered.succeed(()) *> ZIO.never)))
          _ <- entered.await
          _ <- TestClock.adjust(45.seconds)
          snapshot <- services.status.repeatUntil(json => field(json, "services", "irsa_sia", "last_check") != Json.Null)
          rejected <- services.call("irsa_sia")(ZIO.unit).either
        yield assertTrue(code(rejected).contains("archive_circuit_open"),
          field(snapshot, "services", "irsa_sia", "last_error") == Json.Str("external_probe_timeout"),
          field(snapshot, "preferred_route") == Json.Str("s3_mirror"))
      }
    },
    test("closing the application scope stops scheduled probes") {
      for
        calls <- Ref.make(0)
        _ <- ZIO.scoped {
          ExternalServices.make(Map("irsa_sia" -> calls.update(_ + 1))).flatMap(services => ready(services, "irsa_sia"))
        }
        _ <- TestClock.adjust(2.hours)
        count <- calls.get
      yield assertTrue(count == 1)
    },
    test("a late failed request cannot undo a newer successful health probe") {
      ZIO.scoped {
        for
          services <- ExternalServices.make(Map("irsa_sia" -> ZIO.unit))
          _ <- ready(services, "irsa_sia")
          entered <- Promise.make[Nothing, Unit]
          release <- Promise.make[Nothing, Unit]
          pending <- services.call("irsa_sia")(entered.succeed(()) *> release.await *> ZIO.fail(new java.io.IOException("old outage"))).either.fork
          _ <- entered.await *> services.checkNow("irsa_sia")
          _ <- release.succeed(()) *> pending.join
          result <- services.call("irsa_sia")(ZIO.succeed(true))
        yield assertTrue(result)
      }
    },
    suite("bounded real protocol probes")(
      test("SIA executes a one-record image query and accepts structurally valid OVERFLOW") {
        withProbe(siaDocument, "irsa_sia") { (probe, query) => probe.as(assertTrue(
          query.get.contains("MAXREC=1"), query.get.contains("POS=CIRCLE"), query.get.contains("COLLECTION=spherex_dr1"))) }
      },
      test("SIA accepts sole OVERFLOW with a valid one-row results table") {
        withProbe(siaOverflowOnly, "irsa_sia") { (probe, _) =>
          probe.either.map(result => assertTrue(result.isRight))
        }
      },
      test("TAP rejects sole OVERFLOW even with a valid results table") {
        withProbe(tapDocument.replace("value=\"OK\"", "value=\"OVERFLOW\""), "irsa_tap") { (probe, _) =>
          probe.either.map(result => assertTrue(code(result).contains("external_probe_invalid_response")))
        }
      },
      test("SIA sole OVERFLOW still requires the declared result schema") {
        withProbe(siaOverflowOnly.replace("name=\"access_url\"", "name=\"unexpected\""), "irsa_sia") { (probe, _) =>
          probe.either.map(result => assertTrue(code(result).contains("external_probe_invalid_response")))
        }
      },
      test("TAP performs a real TOP 1 schema query and validates table_name") {
        withProbe(tapDocument, "irsa_tap") { (probe, query) => probe.as(assertTrue(
          query.get.contains("SELECT TOP 1 table_name FROM TAP_SCHEMA.tables"), query.get.contains("MAXREC=1"))) }
      },
      test("HTTP 200 HTML never restores an unavailable service") {
        withProbe("<html><body>temporarily down</body></html>", "irsa_sia") { (probe, _) =>
          for
            services <- ExternalServices.make(Map("irsa_sia" -> probe))
            _ <- services.status.repeatUntil(json => field(json, "services", "irsa_sia", "last_check") != Json.Null)
            result <- services.call("irsa_sia")(ZIO.unit).either
            snapshot <- services.status
          yield assertTrue(code(result).contains("archive_circuit_open"),
            field(snapshot, "services", "irsa_sia", "last_success") == Json.Null)
        }
      },
      test("QUERY_STATUS ERROR rejects a well formed VOTable") {
        withProbe(tapDocument.replace("value=\"OK\"", "value=\"ERROR\""), "irsa_tap") { (probe, _) =>
          probe.either.map(result => assertTrue(code(result).contains("external_probe_invalid_response")))
        }
      },
      test("capabilities-only or fieldless XML is not a successful data probe") {
        withProbe("<VOTABLE><RESOURCE><INFO name=\"QUERY_STATUS\" value=\"OK\"/><TABLE><DATA><TABLEDATA/></DATA></TABLE></RESOURCE></VOTABLE>", "irsa_tap") { (probe, _) =>
          probe.either.map(result => assertTrue(code(result).contains("external_probe_invalid_response")))
        }
      },
      test("metadata responses larger than 512 KiB fail before parsing") {
        withProbe(" " * (512 * 1024 + 1), "irsa_tap") { (probe, _) =>
          probe.either.map(result => assertTrue(code(result).contains("external_probe_size_limit")))
        }
      },
      test("a service HTTP 503 cannot be considered healthy") {
        withProbe(tapDocument, "irsa_tap", 503) { (probe, _) =>
          probe.either.map(result => assertTrue(code(result).contains("external_probe_http_error")))
        }
      }
    ).provideLayerShared(Client.default) @@ TestAspect.withLiveClock
  ) @@ TestAspect.timeout(15.seconds)
