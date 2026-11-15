/** Temporary Scala source compatibility until the separate client migration. */
package spaceapps.integrations.grpc
export spaceapps.irsa.integrations.grpc.{GrpcServer,GrpcMapping}

object LegacyAnalysisBinding:
  def bind(service:spaceapps.service.Analyses)=spaceapps.integrations.grpc.v1.ZioAnalysis.GAnalysisService.genericBindable.bind(new AnalysisGrpc(service))
