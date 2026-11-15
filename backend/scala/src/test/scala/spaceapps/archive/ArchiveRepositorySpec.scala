package spaceapps.archive
import spaceapps.domain.*
import spaceapps.archive.domain.*
import spaceapps.service.*
import spaceapps.archive.service.*
import spaceapps.archive.repository.ArchiveRepository
import spaceapps.archive.bootstrap.ArchiveRuntime
import spaceapps.archive.integrations.ArchiveProvider
import zio.*
import zio.test.*
import java.nio.file.Files
object ArchiveRepositorySpec extends ZIOSpecDefault:
  def spec=suite("archive SQLite")(
    test("partial outcomes and snapshot pagination survive reopen") {
      for
        dir <- ZIO.attempt(Files.createTempDirectory("archive-repo-"))
        repo <- ArchiveRepository.open(dir.resolve("jobs.sqlite"))
        r=ArchiveRecord.create("eso","VISTA","dataset",ProductKind.image)
        job=SearchSnapshot("search",ArchiveQuery(Circle(0,0,0.1),List("eso","esasky")),status="partial",records=List(r),outcomes=List(ProviderOutcome("eso","success",1,Completeness.truncated),ProviderOutcome("esasky","unavailable",0,Completeness.unknown)))
        _ <- repo.saveSearch(job)
        reopened <- ArchiveRepository.open(dir.resolve("jobs.sqlite"))
        restored <- reopened.search("search")
        page <- reopened.page("search",None,1)
      yield assertTrue(restored==job,page.records==List(r),page.outcomes.head.completeness==Completeness.truncated,page.next_cursor.isEmpty)
    }
  )
