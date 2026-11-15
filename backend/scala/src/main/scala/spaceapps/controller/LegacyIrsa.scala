/** Temporary Scala source compatibility until the separate client migration. */
package spaceapps.controller
export spaceapps.infra.controller.Api

object LegacyAnalysisRoutes:
  def routes(service:spaceapps.service.Analyses)=new AnalysisApi(service).routes
