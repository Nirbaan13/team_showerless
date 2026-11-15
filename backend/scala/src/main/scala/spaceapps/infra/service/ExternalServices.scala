package spaceapps.infra.service

import spaceapps.infra.model.ApiError
import zio.*
import zio.json.ast.Json
import java.io.IOException
import java.time.Instant
import java.util.concurrent.TimeoutException

/** Independent, fail-closed circuits. Only dedicated, validated probes restore traffic. */
final class ExternalServices private (
  probes: Map[String, Task[Unit]],
  interval: Duration,
  states: Ref[Map[String, ExternalServices.State]]
):
  import ExternalServices.*

  def isAvailable(name: String): UIO[Boolean] = states.get.map(_.get(name).exists(_.available))

  def call[A](name: String)(effect: Task[A]): Task[A] =
    states.get.flatMap { snapshot => snapshot.get(name) match
      case Some(state) if state.available => effect.tapError { error =>
        if transient(error) then Clock.instant.flatMap { now =>
          states.update { current =>
            val latest = current(name)
            if latest.generation != state.generation then current
            else current.updated(name, latest.copy(available = false, generation = latest.generation + 1,
              lastError = Some(errorCode(error)), changed = now))
          }
        } else ZIO.unit
      }
      case _ => ZIO.fail(ApiError("archive_circuit_open", s"$name is unavailable; awaiting its scheduled health probe", true))
    }

  /** Concurrent calls coalesce; a caller never turns an open circuit into a request probe. */
  def checkNow(name: String): Task[Unit] = probes.get(name) match
    case None => ZIO.fail(ApiError("external_service_unknown", s"Unknown external service: $name"))
    case Some(probe) => ZIO.uninterruptibleMask { restore =>
      for
        claimed <- states.modify { all =>
          val state = all(name)
          if state.checking then (None, all)
          else (Some(state.generation), all.updated(name, state.copy(checking = true)))
        }
        _ <- ZIO.foreachDiscard(claimed) { generation =>
          for
            result <- restore(probe.timeoutFail(ApiError("external_probe_timeout", "External service probe timed out", true))(45.seconds)).exit
            now <- Clock.instant
            _ <- states.update { all =>
              val current = all(name)
              val released = current.copy(checking = false)
              if current.generation != generation then all.updated(name, released)
              else result match
                case Exit.Success(_) => all.updated(name, released.copy(available = true, generation = generation + 1,
                  lastCheck = Some(now), lastSuccess = Some(now), lastError = None, nextCheck = now.plusMillis(interval.toMillis), changed = now))
                case Exit.Failure(cause) if cause.isInterrupted => all.updated(name, released)
                case Exit.Failure(cause) =>
                  val error = cause.failureOption.map(errorCode).getOrElse("external_probe_failed")
                  all.updated(name, released.copy(available = false, generation = generation + 1,
                    lastCheck = Some(now), lastError = Some(error), nextCheck = now.plusMillis(interval.toMillis), changed = now))
            }
            _ <- if result.isInterrupted then ZIO.interrupt else ZIO.unit
          yield ()
        }
      yield ()
    }

  def status: UIO[Json] = states.get.map { all =>
    val services = all.toList.sortBy(_._1).map { (name, state) =>
      name -> Json.Obj(
        "state" -> Json.Str(if state.checking && !state.available then "half_open" else if state.available then "closed" else "open"),
        "available" -> Json.Bool(state.available),
        "checking" -> Json.Bool(state.checking),
        "last_check" -> timestamp(state.lastCheck),
        "last_success" -> timestamp(state.lastSuccess),
        "last_error" -> state.lastError.fold[Json](Json.Null)(Json.Str(_)),
        "next_check" -> Json.Str(state.nextCheck.toString),
        "changed_at" -> Json.Str(state.changed.toString))
    }
    val primary = all.get("irsa_sia").exists(_.available)
    Json.Obj("services" -> Json.Obj(Chunk.fromIterable(services)),
      "primary_available" -> Json.Bool(primary),
      "preferred_route" -> Json.Str(if primary then "irsa_sia" else "s3_mirror"),
      "check_interval_seconds" -> Json.Num(interval.toSeconds))
  }

object ExternalServices:
  private final case class State(
    available: Boolean, checking: Boolean, generation: Long,
    lastCheck: Option[Instant], lastSuccess: Option[Instant], lastError: Option[String],
    nextCheck: Instant, changed: Instant
  )
  private def timestamp(value: Option[Instant]): Json = value.fold[Json](Json.Null)(time => Json.Str(time.toString))
  private def errorCode(error: Throwable): String = error match
    case api: ApiError => api.code
    case _: IOException => "external_transport_failure"
    case _: TimeoutException => "external_timeout"
    case _ => "external_probe_failed"
  private def transient(error: Throwable): Boolean = error match
    case api: ApiError => api.retryable && (api.code.endsWith("_timeout") || api.code.endsWith("_unavailable") || api.code.endsWith("_http_error"))
    case _: IOException | _: TimeoutException => true
    case _ => false

  def make(probes: Map[String, Task[Unit]], interval: Duration = 1.hour): ZIO[Scope, Nothing, ExternalServices] =
    for
      now <- Clock.instant
      states <- Ref.make(probes.keys.map(name => name -> State(false, false, 0L, None, None, None, now, now)).toMap)
      service = new ExternalServices(probes, interval, states)
      _ <- ZIO.foreachDiscard(probes.keys) { name =>
        (service.checkNow(name).ignore *> (ZIO.sleep(interval) *> service.checkNow(name).ignore).forever).forkScoped
      }
    yield service
