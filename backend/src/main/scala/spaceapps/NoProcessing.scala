package spaceapps

import zio.*
import java.nio.file.Path

/** Scientific processing is intentionally deferred until the team supplies its pipeline. */
object NoProcessing extends Processor:
  override val supportsPreview = false
  def prepare(image: Path, output: Path, mode: String, reference: Option[Path], query: Query): Task[Unit] =
    ZIO.fail(ApiError("unsupported_processing", "Scientific processing is not available yet"))
  def preview(image: Path, output: Path): Task[Unit] =
    ZIO.fail(ApiError("preview_unavailable", "PNG previews are not available yet"))
