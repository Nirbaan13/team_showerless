package spaceapps.infra.model
import zio.json.*
import java.security.MessageDigest

final case class ApiError(code: String, message: String, retryable: Boolean = false) extends Exception(message) derives JsonCodec
object ApiError:
  def from(t: Throwable): ApiError = t match
    case e: ApiError => e
    case _ => ApiError("internal_error", "The operation failed; inspect service logs", true)

object Hash:
  def sha256(text: String): String = MessageDigest.getInstance("SHA-256").digest(text.getBytes(java.nio.charset.StandardCharsets.UTF_8)).map(b => f"${b & 255}%02x").mkString

final case class Event(sequence:Long,name:String,data:String) derives JsonCodec
