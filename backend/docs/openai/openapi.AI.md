# Raw OpenAPI YAML; the .AI.md suffix marks AI-generated documentation.
openapi: 3.1.0
info:
  title: SPHEREx Backend API
  version: 0.1.0
  description: |
    Proposed backend contract. Search is independent from data preparation.
    The observation endpoints replace POST /api/downloads and select the
    processing mode through the URL. Download status, events, chunk data,
    and preview endpoints are retained.
    URLs may be returned before their resources are ready. Clients must use
    resource status or readiness events before fetching image or FITS data.
servers:
  - url: http://35.159.162.202
tags:
  - name: Observations
  - name: Downloads
  - name: Chunks
paths:
  /api/observations/search:
    post:
      tags: [Observations]
      operationId: searchObservations
      summary: Search archive observations without downloading image data
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SkyQuery'
      responses:
        '200':
          description: Matching observation metadata
          content:
            application/json:
              schema:
                type: object
                required: [observations]
                properties:
                  observations:
                    type: array
                    items:
                      $ref: '#/components/schemas/Observation'
        '422':
          $ref: '#/components/responses/InvalidRequest'
        '503':
          $ref: '#/components/responses/ArchiveUnavailable'
  /api/observations/default:
    get:
      tags: [Observations]
      operationId: prepareDefaultObservations
      summary: Prepare calibrated observations without additional subtraction
      description: |
        Immediately returns a download job and stable future resource URLs.
        Discovery and preparation run in the background. Repeated identical
        requests reuse the existing active job or cached result.
      parameters:
        - $ref: '#/components/parameters/RightAscension'
        - $ref: '#/components/parameters/Declination'
        - $ref: '#/components/parameters/Width'
        - $ref: '#/components/parameters/Height'
        - $ref: '#/components/parameters/Detector'
        - $ref: '#/components/parameters/Channel'
      responses:
        '200':
          $ref: '#/components/responses/ReadyJob'
        '202':
          $ref: '#/components/responses/PendingJob'
        '422':
          $ref: '#/components/responses/InvalidRequest'
  /api/observations/zodi-reference-subtracted:
    get:
      tags: [Observations]
      operationId: prepareZodiSubtractedObservations
      summary: Prepare observations with zodiacal reference subtraction
      description: |
        Uses the processing pipeline to prepare the requested mode.
        Immediately returns a job; it does not wait for processing to finish.
      parameters:
        - $ref: '#/components/parameters/RightAscension'
        - $ref: '#/components/parameters/Declination'
        - $ref: '#/components/parameters/Width'
        - $ref: '#/components/parameters/Height'
        - $ref: '#/components/parameters/Detector'
        - $ref: '#/components/parameters/Channel'
      responses:
        '200':
          $ref: '#/components/responses/ReadyJob'
        '202':
          $ref: '#/components/responses/PendingJob'
        '422':
          $ref: '#/components/responses/InvalidRequest'
  /api/observations/epoch-difference:
    get:
      tags: [Observations]
      operationId: prepareEpochDifferenceObservations
      summary: Prepare differences against a selected reference observation
      description: Immediately returns a job for background processing.
      parameters:
        - $ref: '#/components/parameters/RightAscension'
        - $ref: '#/components/parameters/Declination'
        - $ref: '#/components/parameters/Width'
        - $ref: '#/components/parameters/Height'
        - $ref: '#/components/parameters/Detector'
        - $ref: '#/components/parameters/Channel'
        - name: reference_frame_id
          in: query
          required: true
          description: Reference frame ID returned by observation search
          schema:
            type: string
            minLength: 1
      responses:
        '200':
          $ref: '#/components/responses/ReadyJob'
        '202':
          $ref: '#/components/responses/PendingJob'
        '404':
          $ref: '#/components/responses/NotFound'
        '422':
          $ref: '#/components/responses/InvalidRequest'
  /api/downloads/{id}:
    parameters:
      - $ref: '#/components/parameters/Id'
    get:
      tags: [Downloads]
      operationId: getDownload
      summary: Get job progress, resource links, errors, and final result
      description: |
        Returns the current manifest at any stage. A completed manifest is the
        final result. Each chunk includes its observation, status, and URLs.
        Counts include only discovered work; total may grow during discovery.
      responses:
        '200':
          $ref: '#/components/responses/ReadyJob'
        '404':
          $ref: '#/components/responses/NotFound'
  /api/downloads/{id}/events:
    parameters:
      - $ref: '#/components/parameters/Id'
    get:
      tags: [Downloads]
      operationId: streamDownloadEvents
      summary: Stream discovery, readiness, failure, and completion events
      description: |
        Server-Sent Events. Each data payload contains job_id and may contain
        chunk_id, resource URLs, progress, or an error. Event names are
        job.updated, chunk.ready, chunk.failed, preview.ready, preview.failed,
        and job.completed. The first job.updated event provides the current
        manifest, including when connecting to an already completed job.
        job.completed is emitted after all requested work reaches a terminal
        state, including failure. Poll GET /api/downloads/{id} after reconnecting
        to recover the complete state. Disconnecting does not cancel the job.
      responses:
        '200':
          description: Event stream; the connection closes after job.completed
          content:
            text/event-stream:
              schema:
                type: string
              example: |
                event: chunk.ready
                data: {"job_id":"job-123","chunk_id":"chunk-456","fits_cutout_url":"/api/chunks/chunk-456"}

                event: job.completed
                data: {"job_id":"job-123","status":"completed"}

        '404':
          $ref: '#/components/responses/NotFound'
  /api/chunks/{id}:
    parameters:
      - $ref: '#/components/parameters/Id'
    get:
      tags: [Chunks]
      operationId: getChunk
      summary: Download a prepared FITS chunk
      description: |
        A chunk is an internal piece of the requested region for an observation.
        All chunks together cover the requested available data. Metadata must
        explicitly describe missing coverage; a pending resource is not missing.
      responses:
        '200':
          description: Prepared FITS data
          content:
            application/fits:
              schema:
                type: string
                format: binary
        '202':
          $ref: '#/components/responses/PendingResource'
        '404':
          $ref: '#/components/responses/NotFound'
        '409':
          $ref: '#/components/responses/PreparationFailed'
  /api/chunks/{id}/preview:
    parameters:
      - $ref: '#/components/parameters/Id'
    get:
      tags: [Chunks]
      operationId: getChunkPreview
      summary: Get a prepared PNG preview
      description: |
        The preview URL is stable and may be returned before the image exists.
        preview_status or preview.ready determines when it can be displayed.
      responses:
        '200':
          description: Prepared preview image
          content:
            image/png:
              schema:
                type: string
                format: binary
        '202':
          $ref: '#/components/responses/PendingResource'
        '404':
          $ref: '#/components/responses/NotFound'
        '409':
          $ref: '#/components/responses/PreparationFailed'
components:
  parameters:
    Id:
      name: id
      in: path
      required: true
      schema: {type: string, minLength: 1}
    RightAscension:
      name: right_ascension_deg
      in: query
      required: true
      description: ICRS right ascension of the region center, in degrees
      schema: {type: number, minimum: 0, exclusiveMaximum: 360}
    Declination:
      name: declination_deg
      in: query
      required: true
      description: ICRS declination of the region center, in degrees
      schema: {type: number, minimum: -90, maximum: 90}
    Width:
      name: width_arcmin
      in: query
      description: Full angular width in arcminutes, east-west in the local sky plane
      schema: {type: number, exclusiveMinimum: 0, default: 3}
    Height:
      name: height_arcmin
      in: query
      description: Full angular height in arcminutes, north-south in the local sky plane
      schema: {type: number, exclusiveMinimum: 0, default: 3}
    Detector:
      name: detector_array
      in: query
      schema:
        $ref: '#/components/schemas/DetectorSelection'
    Channel:
      name: channel_index
      in: query
      description: Optional spectral channel filter
      schema: {type: integer, minimum: 1, maximum: 102}
  responses:
    ReadyJob:
      description: Current job manifest; preparation may still be in progress
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Download'
    PendingJob:
      description: Job accepted; discovery and preparation continue in the background
      headers:
        Location:
          description: URL of GET /api/downloads/{id}
          schema: {type: string, format: uri-reference}
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Download'
    PendingResource:
      description: Resource exists in the manifest but is still being prepared
      headers:
        Retry-After:
          description: Suggested delay before retrying, in seconds
          schema: {type: integer, minimum: 1}
      content:
        application/json:
          schema:
            type: object
            required: [id, status]
            properties:
              id: {type: string}
              status: {type: string, enum: [pending]}
    NotFound:
      description: Unknown job, observation, or chunk
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
    InvalidRequest:
      description: Invalid coordinates, sizes, filters, or unsupported request size
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
    ArchiveUnavailable:
      description: Archive search is temporarily unavailable
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
    PreparationFailed:
      description: Resource preparation failed; inspect the job manifest for details
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
  schemas:
    DetectorSelection:
      default: all
      oneOf:
        - {type: integer, minimum: 1, maximum: 6}
        - {type: string, enum: [all]}
    SkyQuery:
      type: object
      required: [right_ascension_deg, declination_deg]
      properties:
        right_ascension_deg: {type: number, minimum: 0, exclusiveMaximum: 360}
        declination_deg: {type: number, minimum: -90, maximum: 90}
        width_arcmin: {type: number, exclusiveMinimum: 0, default: 3}
        height_arcmin: {type: number, exclusiveMinimum: 0, default: 3}
        detector_array:
          $ref: '#/components/schemas/DetectorSelection'
        channel_index: {type: integer, minimum: 1, maximum: 102}
        observed_after: {type: string, format: date-time}
        observed_before: {type: string, format: date-time}
    Observation:
      type: object
      required: [frame_id, observation_date, detector_array, release, is_available]
      properties:
        frame_id: {type: string}
        observation_date: {type: string, format: date-time}
        detector_array: {type: integer, minimum: 1, maximum: 6}
        release: {type: string, enum: [DR1, QR3]}
        wavelength_min_um: {type: number}
        wavelength_max_um: {type: number}
        channel_index: {type: integer, minimum: 1, maximum: 102}
        is_available: {type: boolean}
        skip_reason: {type: string}
        header_metadata:
          type: object
          description: Available archive metadata; unavailable metrics are omitted
          additionalProperties: true
    Chunk:
      type: object
      required: [id, frame_id, status, preview_status, image_url, fits_cutout_url]
      properties:
        id: {type: string}
        frame_id: {type: string}
        status: {type: string, enum: [pending, ready, failed, unavailable]}
        preview_status: {type: string, enum: [pending, ready, failed, unavailable]}
        image_url: {type: string, format: uri-reference}
        fits_cutout_url: {type: string, format: uri-reference}
        region:
          $ref: '#/components/schemas/SkyQuery'
        error:
          $ref: '#/components/schemas/Error'
    Download:
      type: object
      required: [id, status, mode, query, observations, chunks, progress, status_url, events_url]
      properties:
        id: {type: string}
        status:
          type: string
          enum: [queued, discovering, preparing, completed, completed_with_errors, failed]
        mode:
          type: string
          enum: [default, zodi_reference_subtracted, epoch_difference]
        query:
          $ref: '#/components/schemas/SkyQuery'
        reference_frame_id: {type: string}
        observations:
          type: array
          description: May be empty while archive discovery is in progress
          items:
            $ref: '#/components/schemas/Observation'
        chunks:
          type: array
          description: Discovered chunks; new entries may arrive during discovery
          items:
            $ref: '#/components/schemas/Chunk'
        progress:
          type: object
          required: [discovery_complete, total_chunks, ready_chunks, failed_chunks, unavailable_chunks]
          properties:
            discovery_complete: {type: boolean}
            total_chunks: {type: integer, minimum: 0}
            ready_chunks: {type: integer, minimum: 0}
            failed_chunks: {type: integer, minimum: 0}
            unavailable_chunks: {type: integer, minimum: 0}
        status_url: {type: string, format: uri-reference}
        events_url: {type: string, format: uri-reference}
        errors:
          type: array
          items:
            $ref: '#/components/schemas/Error'
    Error:
      type: object
      required: [code, message]
      properties:
        code: {type: string}
        message: {type: string}
        retryable: {type: boolean}
