/** Temporary Scala source compatibility until the separate client migration. */
package spaceapps.bootstrap
import zio.*
object Main extends ZIOAppDefault:
  def run=spaceapps.infra.bootstrap.Application.run
