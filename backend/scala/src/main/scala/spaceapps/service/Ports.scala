package spaceapps.service

import zio.*
import java.nio.file.Path
import spaceapps.domain.{ArchiveImage,Query}

trait Archive:
  def search(query: Query): Task[List[ArchiveImage]]
  def select(image: ArchiveImage, query: Query): Task[ArchiveImage] = ZIO.succeed(image)
  def fetch(image: ArchiveImage, destination: Path): Task[Unit]

trait Processor:
  def supportsPreview: Boolean = true
  def supportedModes: Set[String] = Set.empty
  def prepare(image: Path, output: Path, mode: String, reference: Option[Path], query: Query): Task[Unit]
  def preview(image: Path, output: Path): Task[Unit]
