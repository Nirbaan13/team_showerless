package spaceapps.archive.service
import spaceapps.archive.integrations.ArchiveProvider
import spaceapps.archive.repository.ArchiveRepository
import spaceapps.archive.domain.*
import zio.*
import java.util.UUID

final case class ArchiveLimits(global_parallelism: Int = 3,per_provider_parallelism: Int = 1,request_timeout_ms: Long = 30000,search_deadline_ms: Long = 120000,metadata_bytes: Long = 8L*1024*1024,file_bytes: Long = 256L*1024*1024,max_retries: Int = 2,max_active_jobs: Int = 32):
  require(global_parallelism>0 && per_provider_parallelism>0 && request_timeout_ms>0 && search_deadline_ms>0 && metadata_bytes>0 && file_bytes>0 && max_retries>=0 && max_retries<=2 && max_active_jobs>0)

final class FederatedDiscovery private(val registry: ProviderRegistry,val repository: ArchiveRepository,limits: ArchiveLimits,global: Semaphore,perProvider: Map[String,Semaphore],admission: Semaphore):
  def accept(query: ArchiveQuery): IO[ArchiveFailure,AcceptedJob] = admission.withPermit {
    for
      q <- ZIO.fromEither(query.validate)
      _ <- ZIO.foreachDiscard(q.providers)(registry.get)
      active <- repository.allSearches.map(_.count(j=>Set("queued","running")(j.status)))
      _ <- ZIO.fail(ArchiveFailure("capacity_exceeded","Archive search queue is full",true)).when(active>=limits.max_active_jobs)
      id=UUID.randomUUID().toString
      url=s"/api/archive-searches/$id"
      _ <- repository.saveSearch(SearchSnapshot(id,q,status_url=url))
    yield AcceptedJob(id,url)
  }
  def continue(id: String,provider: String): IO[ArchiveFailure,AcceptedJob] = admission.withPermit {
    for
      active <- repository.allSearches.map(_.count(j=>Set("queued","running")(j.status)))
      _ <- ZIO.fail(ArchiveFailure("capacity_exceeded","Archive search queue is full",true)).when(active>=limits.max_active_jobs)
      job <- repository.updateSearch(id) { job=>
        if Set("queued","running")(job.status) then throw ArchiveFailure("job_active","Search job is already running")
        if !job.query.providers.contains(provider) || !job.continuations.contains(provider) then throw ArchiveFailure("unsupported_continuation","Provider has no genuine continuation for this search")
        job.copy(status="queued",pending_provider=Some(provider),generation=job.generation+1)
      }
    yield AcceptedJob(job.id,job.status_url)
  }
  private def retry[A](effect: => IO[ArchiveFailure,A],attempt: Int = 0): IO[ArchiveFailure,A] = effect.catchAll { error=>
    if error.retryable && attempt<limits.max_retries then
      ZIO.sleep(Duration.fromMillis(error.retry_after_seconds.fold(200L << attempt)(s=>math.max(0L,s)*1000L))) *> retry(effect,attempt+1)
    else ZIO.fail(error)
  }
  private def discover(provider: ArchiveProvider,q: ArchiveQuery,cursor: Option[ProviderCursor]): IO[ArchiveFailure,ProviderPage] = perProvider(provider.id).withPermit(global.withPermit {
    for
      caps <- provider.capabilities
      _ <- ZIO.fail(ArchiveFailure(caps.availability,caps.restrictions.mkString("; "))).unless(caps.availability=="available")
      _ <- ZIO.fail(ArchiveFailure("unsupported_filter","Provider has no qualified exact UTC interval filter")).when(q.hasTime && caps.time_filter!=TimeFilterMode.exact_utc)
      kinds=q.product_kinds.filter(caps.product_kinds.contains)
      _ <- ZIO.fail(ArchiveFailure("unsupported_product","Requested product kinds are unsupported by this provider")).when(kinds.isEmpty)
      page <- retry(provider.search(q.copy(product_kinds=kinds),cursor)
        .catchAllDefect(_=>ZIO.fail(ArchiveFailure("provider_error","Archive provider could not decode or resolve its metadata")))
        .timeoutFail(ArchiveFailure("timeout","Archive metadata request timed out",true))(Duration.fromMillis(limits.request_timeout_ms)))
      _ <- ZIO.fail(ArchiveFailure("invalid_response","Provider returned records outside the requested contract")).when(page.records.size>q.limit_per_provider || page.records.exists(r=>r.provider!=provider.id || !kinds.contains(r.product_kind)))
    yield page
  })
  private def failureStatus(error: ArchiveFailure): String = error.code match
    case "requires_auth"=>"requires_auth"
    case "unsupported_filter"=>"unsupported_filter"
    case "unavailable" | "pending_qualification"=>"unavailable"
    case _=>"failed"
  private def persist(id: String,provider: String,result: Either[ArchiveFailure,ProviderPage]): IO[ArchiveFailure,Unit] = repository.updateSearch(id) { job=>
    val rows=result.toOption.toList.flatMap(_.records)
    val allRecords=(job.records++rows).distinctBy(_.id).sortBy(_.id)
    val count=allRecords.count(_.provider==provider)
    val outcome=result match
      case Right(page)=>ProviderOutcome(provider,if page.records.isEmpty then "empty" else "success",count,page.completeness,page.warnings,has_continuation=page.continuation.nonEmpty)
      case Left(error)=>ProviderOutcome(provider,failureStatus(error),count,Completeness.unknown,error=Some(error))
    val cursors=result.toOption.flatMap(_.continuation).fold(job.continuations-provider)(c=>job.continuations.updated(provider,c))
    job.copy(records=allRecords,outcomes=(job.outcomes.filterNot(_.provider==provider):+outcome).sortBy(_.provider),continuations=cursors,generation=job.generation+1)
  }.unit
  /** Claiming is persisted, so multiple workers cannot execute a job twice. */
  def execute(id: String): IO[ArchiveFailure,Unit] =
    repository.updateSearch(id) { job=>
      if job.status!="queued" then throw ArchiveFailure("job_active","Search job is not queued")
      job.copy(status="running",outcomes=job.pending_provider.fold(job.outcomes)(p=>job.outcomes.filterNot(_.provider==p)))
    }.flatMap { job=>
      val selected=job.pending_provider.toList match
        case Nil=>job.query.providers.filterNot(p=>job.outcomes.exists(_.provider==p))
        case ids=>ids
      val work=ZIO.foreachParDiscard(selected) { id=>registry.get(id).flatMap(p=>discover(p,job.query,job.continuations.get(id))).either.flatMap(persist(job.id,id,_)) }.withParallelism(limits.global_parallelism)
      val timeout=ArchiveFailure("timeout","Archive search deadline exceeded",true)
      work.timeout(Duration.fromMillis(limits.search_deadline_ms)).flatMap {
        case Some(_)=>ZIO.unit
        case None=>repository.search(job.id).flatMap { current=>
          ZIO.foreachDiscard(selected.filterNot(p=>current.outcomes.exists(_.provider==p)))(p=>persist(job.id,p,Left(timeout)))
        }
      } *> repository.updateSearch(job.id) { current=>
        val successes=current.outcomes.count(o=>o.status=="success" || o.status=="empty")
        val status=if successes==current.outcomes.size then "completed" else if successes==0 then "failed" else "partial"
        current.copy(status=status,pending_provider=None)
      }.unit
    }
  def recover: IO[ArchiveFailure,Unit] = repository.allSearches.flatMap(jobs=>ZIO.foreachDiscard(jobs.filter(_.status=="running"))(j=>repository.updateSearch(j.id)(_.copy(status="queued"))))
  def start: ZIO[Scope,Nothing,Unit] =
    val poll=repository.allSearches.flatMap(jobs=>ZIO.foreachDiscard(jobs.filter(_.status=="queued"))(j=>execute(j.id).catchAll(_=>ZIO.unit))).catchAll(_=>ZIO.unit) *> ZIO.sleep(200.millis)
    (poll.forever).forkScoped.unit
object FederatedDiscovery:
  def make(registry: ProviderRegistry,repository: ArchiveRepository,limits: ArchiveLimits = ArchiveLimits()): UIO[FederatedDiscovery] =
    for
      global <- Semaphore.make(limits.global_parallelism.toLong)
      entries <- ZIO.foreach(registry.providers)(p=>Semaphore.make(limits.per_provider_parallelism.toLong).map(p.id->_))
      admission <- Semaphore.make(1)
    yield new FederatedDiscovery(registry,repository,limits,global,entries.toMap,admission)
