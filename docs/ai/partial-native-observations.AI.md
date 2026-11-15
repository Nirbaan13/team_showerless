# Preserve usable native observations after a partial download

## Confirmed incident

On 2026-11-15, the production Barnard's Star Band 2 download
`b5c05e89-0f9d-445d-9b08-daaff423a762` completed with 36 ready native FITS
chunks out of 37. The remaining file failed with `archive_http_error: Archive
returned HTTP 503`. The global `archive_mirror_partial` entry was a warning
that the mirror index was incomplete, not a statement that the 36 files were
unusable.

The frontend discarded every observation because one chunk was not ready and
displayed the coverage warning before the actual file error. Even if the
frontend had submitted the download, the analysis service would reject both a
failed sibling and a download exceeding its 32-frame input limit.

## Change

`POST /api/analyses/motion` accepts an optional `frame_ids` list with a native
`download_id`. It must contain 3 to 32 distinct frame IDs belonging to that
completed download. Every selected chunk must be ready; unknown, failed,
foreign, duplicate, oversized, preset, and processed-input selections are
rejected. No filesystem path or external URL can be supplied by this field.

Legacy requests without `frame_ids` retain the existing strict all-frames
behavior. Analysis snapshots lease the selected native files through the
existing cache mechanism. The result records selected IDs and total/ready
counts in `provenance.input_selection`; omitted frames are disclosed in result
warnings. The request, and therefore the durable deduplication key, includes
the explicit selection.

The viewer waits for a terminal download, then selects ready frames. For more
than 32 ready frames, it sorts by available observation timestamps and samples
up to 32 evenly spaced list positions, retaining both time endpoints. Failed
or unavailable siblings never enter the selection. Fewer than three ready
frames remain an error, with the actual file cause and ready/total counts.
Coverage, excluded-file, and sampling warnings remain visible beside the field
after successful image analysis. This does not represent a partial archive as
complete coverage.

## Verification

Regression tests reproduce the 36-ready / 37-total case and the insufficient
ready-frame case through the actual frontend/API boundary. Scala tests cover
JSON validation, native ownership/readiness, strict default behavior, and a
32-frame subset from a 37-frame download, including provenance and warnings.
Controlled protocol fixtures establish contract behavior; they are not
scientific evidence. Production verification must use the real cached Barnard
FITS and verify the resulting image resources separately.

The original frontend baseline already had five failing tests: two removed
model-provenance text assertions and three spectrum-tab click failures. These
are recorded separately from this fix's regressions.
