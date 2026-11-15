package spaceapps.equipment.service
import spaceapps.infra.service.FileCache

import spaceapps.infra.model.{ApiError, Hash}
import spaceapps.irsa.repository.Repository
import spaceapps.equipment.integrations.{CalibrationArchive, CalibrationLimits, CalibrationProduct}
import zio.*
import zio.http.Client
import zio.json.*
import zio.json.ast.Json
import java.nio.file.{Files, LinkOption, Path, StandardCopyOption}
import java.time.Instant

final case class EquipmentFile(path: Path, fileName: String, contentType: String)

final class EquipmentService private (repository: Repository, directory: Path, archive: CalibrationArchive, limits: CalibrationLimits, catalogGate: Semaphore, fileGate: Semaphore, cache: FileCache):
  private val namespace = Hash.sha256(archive.baseUrl)
  private val ttlSeconds = 3600L
  private def decode[A: JsonDecoder](body: String): Task[A] = ZIO.fromEither(body.fromJson[A].left.map(_ => ApiError("storage_error", "Stored calibration metadata could not be read")))
  private def identityKey(id: String) = "equipment:file:" + id
  private def products(release: String): Task[List[CalibrationProduct]] = catalogGate.withPermit {
    val key = s"equipment:catalog:$namespace:$release"
    for
      saved <- repository.cachedMetadata(key)
      now <- ZIO.succeed(Instant.now().getEpochSecond)
      result <- saved match
        case Some((body,time)) if now >= time && now-time < ttlSeconds => decode[List[CalibrationProduct]](body).tap(ps => ZIO.attempt(ps.foreach(archive.validate)))
        case _ =>
          for
            discovered <- archive.discover(release)
            _ <- ZIO.foreachDiscard(discovered)(p => repository.cacheMetadata(identityKey(p.id),p.toJson))
            _ <- repository.cacheMetadata(key,discovered.toJson)
          yield discovered
    yield result
  }
  def catalog(release: String, detector: Option[Int]): Task[Json] =
    val normalized = release.toUpperCase(java.util.Locale.ROOT)
    if !Set("DR1","QR3").contains(normalized) then ZIO.fail(ApiError("invalid_release", "Equipment release must be DR1 or QR3"))
    else if detector.exists(d => d < 1 || d > 6) then ZIO.fail(ApiError("invalid_detector", "Detector array must be between 1 and 6"))
    else products(normalized).map { all =>
      val selected = all.filter(p => detector.isEmpty || p.detector_array.isEmpty || p.detector_array == detector)
      val bands = List((0.75,1.09,39),(1.10,1.62,41),(1.63,2.41,41),(2.42,3.82,35),(3.83,4.41,112),(4.42,5.00,128))
      val detectors = bands.zipWithIndex.collect { case ((lo,hi,r),index) if detector.forall(_ == index+1) =>
        Json.Obj("detector_array" -> Json.Num(index+1), "wavelength_min_um" -> Json.Num(lo), "wavelength_max_um" -> Json.Num(hi), "resolving_power" -> Json.Num(r))
      }
      Json.Obj("facility" -> Json.Str("SPHEREx"),"instrument" -> Json.Str("SPHEREx"),"release" -> Json.Str(normalized),
        "detectors" -> Json.Arr(Chunk.fromIterable(detectors)),"calibration_products" -> selected.toJsonAST.toOption.get,
        "catalogue_source" -> Json.Str(archive.baseUrl),"catalogue_complete" -> Json.Bool(true), "catalogue_ttl_seconds" -> Json.Num(ttlSeconds),
        "catalogue_scope" -> Json.Str("All versions in recognized public calibration prefixes; science images and cubes excluded."),
        "not_listed_product_types" -> archive.productTypes.diff(all.map(_.product_type).toSet).toList.sorted.toJsonAST.toOption.get,
        "frame_applicability" -> Json.Str("Release catalogue only. Match a frame's pipeline calibration provenance before use; no latest-version assumption is made."))
    }
  private def contentType(name: String): String =
    if name.endsWith(".yaml") || name.endsWith(".yml") then "application/yaml"
    else if name.endsWith(".ecsv") || name.endsWith(".csv") then "text/plain"
    else if name.endsWith(".gz") then "application/gzip"
    else "application/fits"
  private def checkedPath(id: String): Path =
    val path = directory.resolve(id).normalize()
    if path.getParent != directory || Files.isSymbolicLink(path) || Files.isSymbolicLink(directory) then throw ApiError("calibration_cache_error", "Unsafe calibration cache path")
    path
  /** The caller keeps this scope open until its HTTP/gRPC stream closes. */
  def leasedFile(id: String): ZIO[Scope,Throwable,EquipmentFile] =
    if !id.matches("[0-9a-f]{64}") then ZIO.fail(ApiError("not_found", "Calibration file not found"))
    else ZIO.attempt(checkedPath(id)).flatMap(path=>cache.protect(path) *> file(id))
  def file(id: String): Task[EquipmentFile] =
    if !id.matches("[0-9a-f]{64}") then ZIO.fail(ApiError("not_found", "Calibration file not found"))
    else for
      saved <- repository.cachedMetadata(identityKey(id))
      body <- ZIO.fromOption(saved.map(_._1)).orElseFail(ApiError("not_found", "Calibration file not found"))
      product <- decode[CalibrationProduct](body)
      _ <- ZIO.attempt { archive.validate(product); if product.id != id then throw ApiError("storage_error", "Calibration identifier does not match its stored metadata") }
      result <- fileGate.withPermit {
        for
          path <- ZIO.attempt(checkedPath(id))
          _ <- ZIO.fail(ApiError("calibration_size_limit", "Calibration file exceeds the download byte limit")).when(product.size_bytes>limits.maxFileBytes)
          _ <- ZIO.scoped {
            cache.protect(path) *> cache.cached(path).flatMap { existing=>
              ZIO.attemptBlocking(existing.exists(p=>Files.size(p)==product.size_bytes)).flatMap { valid=>
                ZIO.unless(valid)(cache.publish(path,product.size_bytes)(partial=>archive.fetch(product,partial)))
              }
            }
          }
        yield EquipmentFile(path,product.file_name,contentType(product.file_name))
      }
    yield result

object EquipmentService:
  /** One JVM owns the data directory; startup reclaims its abandoned calibration partial files. */
  def make(repository: Repository, dataDir: Path, client: Client, baseUrl: String = "https://nasa-irsa-spherex.s3.amazonaws.com/", limits: CalibrationLimits = CalibrationLimits(), capacity: Option[FileCache] = None): Task[EquipmentService] =
    val archive = new CalibrationArchive(client,baseUrl,limits)
    for
      directory <- ZIO.attemptBlocking {
        archive.validateConfiguration()
        val root = dataDir.toAbsolutePath.normalize()
        Files.createDirectories(root)
        val cache = root.resolve("calibration-cache")
        if Files.isSymbolicLink(cache) then throw ApiError("calibration_cache_error", "Calibration cache directory cannot be a symlink")
        Files.createDirectories(cache)
        val directory = cache.toRealPath()
        val entries = Files.list(directory)
        try
          val iterator = entries.iterator()
          while iterator.hasNext do
            val entry = iterator.next()
            val uuid="[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
            if entry.getFileName.toString.matches(s"[0-9a-f]{64}(?:[.]$uuid)?[.]part") then
              if Files.isSymbolicLink(entry) || !Files.isRegularFile(entry,LinkOption.NOFOLLOW_LINKS) then
                throw ApiError("calibration_cache_error", "Unsafe abandoned calibration partial file")
              Files.delete(entry)
        finally entries.close()
        directory
      }
      cache <- ZIO.fromOption(capacity).orElse(FileCache.open(dataDir,dataDir.resolve("cache.sqlite"),limits.cacheBytes,math.min(limits.maxFileBytes,limits.cacheBytes),limits.minFreeBytes))
      catalogGate <- Semaphore.make(1)
      fileGate <- Semaphore.make(1)
    yield new EquipmentService(repository,directory,archive,limits,catalogGate,fileGate,cache)
