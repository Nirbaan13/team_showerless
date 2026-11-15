<?php
// Same-origin API delivery for the static Hostinger frontend. Scientific work
// remains in the VPS services; this script forwards HTTP without inventing data.
declare(strict_types=1);

function proxyError(int $status, string $code, string $message): never {
    http_response_code($status);
    header('Content-Type: application/json');
    header('Cache-Control: no-store');
    echo json_encode(['code' => $code, 'message' => $message, 'retryable' => $status === 502]);
    exit;
}

$target = $_SERVER['REQUEST_URI'] ?? '';
if (!preg_match('~^/(api|backend)(/|\?|$)~', $target) || preg_match('/[\x00-\x20\x7f]/', $target)) {
    proxyError(404, 'not_found', 'No API route exists at this path.');
}
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
if (!in_array($method, ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'], true)) {
    proxyError(405, 'method_not_allowed', 'Unsupported HTTP method.');
}
$limit = 2 * 1024 * 1024;
if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > $limit) {
    proxyError(413, 'request_too_large', 'The API request exceeds 2 MiB.');
}
$body = file_get_contents('php://input', false, null, 0, $limit + 1);
if ($body === false || strlen($body) > $limit) {
    proxyError(413, 'request_too_large', 'The API request exceeds 2 MiB.');
}
$headers = ['Connection: close', 'Accept-Encoding: identity'];
foreach (['CONTENT_TYPE' => 'Content-Type', 'HTTP_ACCEPT' => 'Accept', 'HTTP_AUTHORIZATION' => 'Authorization', 'HTTP_RANGE' => 'Range', 'HTTP_IF_NONE_MATCH' => 'If-None-Match', 'HTTP_LAST_EVENT_ID' => 'Last-Event-ID'] as $key => $name) {
    if (isset($_SERVER[$key]) && !preg_match('/[\r\n]/', $_SERVER[$key])) {
        $headers[] = $name . ': ' . $_SERVER[$key];
    }
}
// The upstream is deployment configuration, never a request parameter or header.
$base = rtrim(getenv('SPACEAPPS_API_UPSTREAM') ?: 'http://144.124.238.101:8080', '/');
$context = stream_context_create(['http' => [
    'method' => $method, 'header' => $headers, 'content' => $body,
    'timeout' => 300, 'ignore_errors' => true, 'follow_location' => 0,
    'protocol_version' => 1.1,
]]);
$upstream = @fopen($base . $target, 'rb', false, $context);
if ($upstream === false) {
    proxyError(502, 'api_upstream_unavailable', 'The VPS API is temporarily unreachable.');
}
$metadata = stream_get_meta_data($upstream);
$status = 502;
$responseHeaders = $metadata['wrapper_data'] ?? [];
foreach ($responseHeaders as $line) {
    if (preg_match('~^HTTP/\S+\s+(\d{3})~', $line, $match)) {
        $status = (int)$match[1];
    }
}
http_response_code($status);
header('Cache-Control: no-store');
foreach ($responseHeaders as $line) {
    $name = strtolower(explode(':', $line, 2)[0]);
    if (in_array($name, ['content-type', 'content-disposition', 'content-range', 'accept-ranges', 'cache-control', 'etag', 'last-modified', 'retry-after', 'location'], true)) {
        header($line, true);
    }
}
header('X-Accel-Buffering: no');
if ($method !== 'HEAD') {
    // Bound memory for FITS/PNG resources and let event-stream chunks flush.
    while (ob_get_level() > 0) {
        ob_end_flush();
    }
    while (!feof($upstream) && !connection_aborted()) {
        $chunk = fread($upstream, 65536);
        if ($chunk === false) break;
        echo $chunk;
        flush();
    }
}
fclose($upstream);
