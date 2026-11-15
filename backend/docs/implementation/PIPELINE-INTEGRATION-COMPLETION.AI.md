# Existing team pipeline HTTP integration

Final scope: Scala integration only. The user prohibits edits to the team's
Python service and to frontend TypeScript. pipeline/ and frontend/ must have zero
diff against main. No Python adapter, new Python endpoint, subprocess worker or
spectral normalization service is introduced.

## Flow

Frontend -> Scala PipelineApi -> HttpPipelineClient -> existing pipeline HTTP
container. Responses keep their completed synchronous JSON/PNG contract. No202
polling is added. The Scala adapter validates inputs, bounds concurrency, request
and response sizes, checks PNG signatures/JSON syntax, and maps upstream errors.

Public Scala routes mirror the existing Python API:
- POST /api/cutout/search
- GET /api/cutout/render
- GET /api/spectrum
- POST /api/spectrum/measure

Python's existing spectrum endpoint only implements ZODI-subtracted measurements;
Scala rejects unsupported raw-spectrum options explicitly. Cached measurement
requests accept basenames rather than client filesystem paths. Rendered cutouts
are chosen by Python's coordinate search, not guaranteed to match a Scala chunk.

Native Scala download jobs and the independent existing ML analysis retain their
main behavior. The original pipeline HTTP API does not expose processed-FITS
output or rendering by native frame ID, so this integration does not fabricate
those capabilities or relabel PNG as FITS. Legacy scientific endpoints retain
explicit unavailable responses where their contract cannot be fulfilled.

## Layout and delivery

Scala/protobuf/resources: backend/scala/src. OpenAPI: backend/docs/openapi.yaml.
backend/python contains dependency lock configuration only. Team Python code
remains in pipeline/. Compose starts Scala and the existing Python service in
separate containers, with the same immutable image revision and a persistent
Python cutout cache. Existing deployment installations require the documented
one-time refresh of their root-installed deployment script before topology upgrade.

## Verification and limits

Scala gateway tests cover synchronous contract, request validation, timeout,
upstream500 handling and POST forwarding. Python service source is not modified
or patched to make tests pass. Original service issues remain visible: the current
cleaning module references fits/numpy/WCS without imports, and query.cutout uses
requests/time without imports. The adapter maps service failures to explicit
502 responses. These issues require fixes by the Python owner before all real
processing operations can succeed; successful gateway tests do not prove those
upstream numerical operations work.
