package spaceapps.integrations.processing

import spaceapps.domain.ApiError
import java.net.http.HttpResponse
import java.nio.ByteBuffer
import java.util.concurrent.{CompletableFuture,CompletionStage,Flow}
import java.io.ByteArrayOutputStream
import scala.jdk.CollectionConverters.*

/** Keep both chunked and Content-Length HTTP responses within the protocol cap. */
private[processing] final class LimitedResponseBody extends HttpResponse.BodySubscriber[Array[Byte]]:
  private val result=new CompletableFuture[Array[Byte]]()
  private val bytes=new ByteArrayOutputStream()
  private var subscription:Flow.Subscription=null
  def getBody():CompletionStage[Array[Byte]]=result
  def onSubscribe(value:Flow.Subscription):Unit=
    subscription=value
    value.request(1)
  def onNext(buffers:java.util.List[ByteBuffer]):Unit=
    try
      buffers.asScala.foreach { buffer=>
        if buffer.remaining()>65536-bytes.size then throw ApiError("processing_protocol","Pipeline response exceeds 64 KiB")
        val data=new Array[Byte](buffer.remaining())
        buffer.get(data);bytes.write(data)
      }
      subscription.request(1)
    catch
      case error:Throwable=>subscription.cancel();result.completeExceptionally(error);()
  def onError(error:Throwable):Unit={result.completeExceptionally(error);()}
  def onComplete():Unit={result.complete(bytes.toByteArray);()}
