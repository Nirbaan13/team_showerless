# Deployed V4 checkpoint after PR 20

The authorized PR merged as `195996740890f0e94d1d54522fe9bb6a01c7dae0`. Backend, frontend and Hostinger deployment gates succeeded. The first backend build encountered HTTP 429 while fetching sbt; an unchanged rerun succeeded. The separate ML HTTP service deployment exceeded its transfer budget and is not claimed successful by this checkpoint.

The source audit and real HTTP probe captured backend revision `1959967` with C596 graph and all eleven exact runtime sources. Latest image tags, exact revision tags and running backend/frontend images agreed at the captured checkpoint; the processing worker was healthy and used the backend image. Subsequent independent teammate deployments may advance those services.

The HTTP request returned 36 candidates, four frames and 80 decoded PNG resources. SSE completion, deduplication, result schema, empty output and error responses passed. The gRPC request returned one candidate and three frames; its scientific result exactly matched HTTP and the completed watch replayed correctly. The old SSH tunnel had expired before the first gRPC attempt; a fresh tunnel passed using the unchanged probe.

The laptop's configured outbound proxy initially returned HTTP 502 for the direct-IP health request. Direct access with the VPS in `NO_PROXY` and server-local requests returned the deployed revision. No server change was needed for that transport issue. Original checkpoint evidence remains unchanged; these three JSON receipts are additional observations.
