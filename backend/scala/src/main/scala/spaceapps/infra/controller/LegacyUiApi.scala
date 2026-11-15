package spaceapps.infra.controller

import zio.http.*
import zio.json.*
import zio.json.ast.Json

/** Fail closed for retired UI dependencies; never start the legacy data generators. */
final class LegacyUiApi(includeMotionSearch:Boolean=true):
  private def unsupported=Response.json(Json.Obj("code"->Json.Str("unsupported_legacy_operation"),
    "message"->Json.Str("This legacy service is not deployed. Use the documented Scala APIs."),
    "retryable"->Json.Bool(false),"motion_analysis_url"->Json.Str("/api/analyses/motion")).toJson)
    .status(Status.NotImplemented).addHeader("Cache-Control","no-store")
  private def submission=Response.json(Json.Obj("code"->Json.Str("submission_disabled"),
    "message"->Json.Str("Client-provided confirmations do not authorize publication. No submission was created."),
    "retryable"->Json.Bool(false)).toJson).status(Status.Forbidden).addHeader("Cache-Control","no-store")
  private val search=if includeMotionSearch then Routes(Method.POST / "api" / "motion" / "search" -> handler(unsupported)) else Routes.empty
  val routes=search ++ Routes(
    Method.POST / "api" / "motion" / "detect" -> handler(unsupported),
    Method.GET / "api" / "motion" / "spectrum" -> handler(unsupported),
    Method.GET / "api" / "motion" / "cutout" / "render" -> handler(unsupported),
    Method.GET / "api" / "motion" / "coadd" / string("candidate") / string("mode") -> handler((candidate:String,mode:String,r:Request)=>unsupported),
    Method.GET / "api" / "motion" / "verifications" -> handler(unsupported),
    Method.POST / "api" / "motion" / "verifications" -> handler(unsupported),
    Method.POST / "api" / "motion" / "verifications" / string("id") / "upvote" -> handler((id:String,r:Request)=>unsupported),
    Method.GET / "api" / "motion" / "candidates" -> handler(unsupported),
    Method.POST / "api" / "motion" / "candidates" -> handler(unsupported),
    Method.GET / "api" / "catalogue" / "kpis" -> handler(unsupported),
    Method.GET / "api" / "catalogue" / "candidates" -> handler(unsupported),
    Method.POST / "api" / "catalogue" / "candidates" -> handler(unsupported),
    Method.GET / "api" / "catalogue" / "candidates" / string("id") -> handler((id:String,r:Request)=>unsupported),
    Method.POST / "api" / "catalogue" / "candidates" / string("id") / "classify" -> handler((id:String,r:Request)=>unsupported),
    Method.POST / "api" / "catalogue" / "candidates" / string("id") / "submissions" -> handler((id:String,r:Request)=>submission),
    Method.POST / "api" / "catalogue" / "auto-submit" -> handler(submission),
    Method.POST / "api" / "motion" / "catalogue" / "auto-submit" -> handler(submission)
  )
