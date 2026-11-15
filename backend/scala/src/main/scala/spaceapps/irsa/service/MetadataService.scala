package spaceapps.irsa.service

import spaceapps.irsa.model.*
import spaceapps.irsa.repository.Repository
import spaceapps.irsa.integrations.TapMetadata
import spaceapps.infra.integrations.fits.FitsHeaders
import zio.*
import zio.http.Client
import zio.json.*
import zio.json.ast.Json
import java.nio.file.Path
import java.util.concurrent.TimeUnit

final class MetadataService private (
  repository: Repository,
  cachedFile: ArchiveImage => ZIO[Scope, Throwable, Option[Path]],
  tap: TapMetadata,
  endpoint: String,
  pending: Ref.Synchronized[Map[String, Promise[Throwable, Json]]],
  network: Semaphore,
  applicationScope: Scope
):
  private def obj(fields: (String, Json)*): Json = Json.Obj(zio.Chunk.fromIterable(fields))
  private def status(value: Json): Option[String] = value match
    case Json.Obj(fields) => fields.collectFirst { case ("status", Json.Str(s)) => s }
    case _ => None
  private def sourceError(error: Throwable): Json =
    val e = error match
      case value: ApiError => value
      case _ => ApiError("metadata_unavailable", "Metadata source is unavailable", true)
    obj("status" -> Json.Str("error"), "error" -> obj("code" -> Json.Str(e.code), "message" -> Json.Str(e.message), "retryable" -> Json.Bool(e.retryable)))
  private def cachedTap(image: ArchiveImage): Task[Json] =
    val key = "tap-metadata:v1:" + Hash.sha256(endpoint + "|" + image.toJson)
    for
      stored <- repository.cachedMetadata(key)
      now <- Clock.currentTime(TimeUnit.SECONDS)
      cached = stored.flatMap { (body, saved) => body.fromJson[Json].toOption.map(value => (value, saved)) }
      result <- cached match
        case Some((value, saved)) if saved <= now && now - saved < (if status(value).contains("available") then 3600L else 60L) => ZIO.succeed(value)
        case _ =>
          network.withPermit(tap.fetch(image)).tap { value =>
            if Set("available", "not_found").exists(status(value).contains) then
              repository.cacheMetadata(key, value.toJson).catchAll(error =>
                ZIO.logWarningCause("TAP metadata cache write failed; returning live metadata", Cause.fail(error)))
            else ZIO.unit
          }.catchAll { error => cached match
            case Some((Json.Obj(fields), _)) =>
              val details = sourceError(error) match
                case Json.Obj(errors) => errors.filterNot(_._1 == "status")
                case _ => zio.Chunk.empty
              ZIO.succeed(Json.Obj(fields.filterNot(_._1 == "status") ++ zio.Chunk("status" -> Json.Str("stale")) ++ details))
            case _ => ZIO.succeed(sourceError(error))
          }
    yield result
  private def sharedTap(image: ArchiveImage): Task[Json] = ZIO.uninterruptibleMask { restore =>
    val key = image.observation.frame_id
    for
      shared <- pending.modifyZIO { current => current.get(key) match
        case Some(promise) => ZIO.succeed(((promise, false), current))
        case None if current.size >= 64 => ZIO.fail(ApiError("capacity_exceeded", "The metadata request queue is full", true))
        case None => Promise.make[Throwable, Json].map(promise => ((promise, true), current.updated(key, promise)))
      }
      (promise, owner) = shared
      _ <- if owner then
        cachedTap(image).interruptible.exit.flatMap(promise.done)
          .ensuring(pending.update(_ - key)).forkIn(applicationScope).unit
      else ZIO.unit
      value <- restore(promise.await)
    yield value
  }
  def get(frameId: String): Task[Json] =
    for
      found <- repository.image(frameId)
      image <- ZIO.fromOption(found).orElseFail(ApiError("not_found", "Frame not found"))
      observation <- ZIO.fromEither(image.observation.toJson.fromJson[Json]).mapError(_ => ApiError("metadata_serialization", "Observation metadata could not be encoded"))
      tapResult <- sharedTap(image).catchAll(error => ZIO.succeed(sourceError(error)))
      fitsResult <- ZIO.scoped { cachedFile(image).flatMap {
        case Some(path) => FitsHeaders.read(path).map {
          case Json.Obj(fields) if image.sourceUrl.nonEmpty => Json.Obj(fields :+ ("spatial_subset" -> Json.Bool(true)))
          case value => value
        }
        case None => ZIO.succeed(obj("status" -> Json.Str("not_downloaded"), "reason" -> Json.Str("Native FITS has not been cached; metadata does not download image data")))
      } }.catchAll(error => ZIO.succeed(sourceError(error)))
      sia = obj("status" -> Json.Str(if image.observation.header_metadata.isEmpty then "unavailable" else "available"), "data" -> Json.Obj(zio.Chunk.fromIterable(image.observation.header_metadata.toList.sortBy(_._1))))
      complete = List(sia, tapResult, fitsResult).forall(value => status(value).contains("available"))
    yield obj("frame_id" -> Json.Str(frameId), "status" -> Json.Str(if complete then "complete" else "partial"),
      "observation" -> observation, "sia" -> sia, "tap" -> tapResult, "fits" -> fitsResult)

object MetadataService:
  def make(repository: Repository, cachedFile: ArchiveImage => ZIO[Scope, Throwable, Option[Path]], client: Client,
    tapEndpoint: String = "https://irsa.ipac.caltech.edu/TAP/sync", availability: Option[spaceapps.infra.service.ExternalServices] = None): ZIO[Scope, Throwable, MetadataService] =
    for
      applicationScope <- ZIO.scope
      pending <- Ref.Synchronized.make(Map.empty[String, Promise[Throwable, Json]])
      network <- Semaphore.make(4)
      _ <- ZIO.addFinalizer(pending.getAndSet(Map.empty).flatMap(remaining => ZIO.foreachDiscard(remaining.values)(_.interrupt)))
    yield new MetadataService(repository, cachedFile, new TapMetadata(client, tapEndpoint, availability), tapEndpoint, pending, network, applicationScope)
