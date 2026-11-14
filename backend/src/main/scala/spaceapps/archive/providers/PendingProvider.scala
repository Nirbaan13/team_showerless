package spaceapps.archive.providers
import spaceapps.archive.*
import zio.*
final class PendingProvider(entry: ProviderInventory) extends ArchiveProvider:
  val id=entry.id
  def capabilities=ZIO.succeed(entry.capabilities)
  def search(q: ArchiveQuery,cursor: Option[ProviderCursor])=ZIO.fail(ArchiveFailure(entry.capabilities.availability,entry.capabilities.restrictions.mkString("; ")))
  def resolve(r: ArchiveRecord,d: DeliveryRequest)=ZIO.fail(ArchiveFailure("unsupported_delivery","Provider delivery is not qualified"))
object PendingProvider:
  val inventory: List[ProviderInventory] = List(
    ("esasky","unavailable","Maintenance HTML observed; direct ESA Gaia is independent"),
    ("nadc-ast3","pending_qualification","FITS byte range verified; sky/time discovery has not passed qualification"),
    ("einstein-probe","requires_auth","Official archive requires login"),
    ("nadc-plates","pending_qualification","Machine discovery and delivery unqualified"),
    ("sao-ras","pending_qualification","Independent ground archive; machine discovery unqualified"),
    ("erodat","pending_qualification","Release and hemisphere rights require qualification")
  ).map((id,state,reason)=>ProviderInventory(id,ProviderCapabilities(Nil,availability=state,restrictions=List(reason))))
