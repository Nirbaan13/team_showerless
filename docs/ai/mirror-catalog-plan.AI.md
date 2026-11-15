# Persistent mirror metadata catalogue implementation plan

**Goal:** Build and populate a generic, persistent SPHEREx mirror catalogue that serves spatial searches during IRSA outages.
**Architecture:** Keep verified FITS header metadata in the existing SQLite database; add a conservative spherical RTree prefilter and a separate resumable catalogue builder partitioned by release, planning period, processing version and detector. Scala supervises ingestion and independently refreshes progress.
**Tech stack:** Existing Python/Astropy, SQLite RTree, Scala/ZIO, anonymous official S3 HTTPS.
**Spec:** User request to implement the independent metadata catalogue after archive_mirror_index_warming.

## Constraints and review focus

- Preserve populated records and retries; do not replace real images with synthetic data.
- Read bounded FITS headers, never full pixel files during ingestion.
- Checkpoint only after outcomes are durable; capacity/network errors must remain resumable.
- Conservative spatial bounds must retain RA wrap, polar, range and polygon matches.
- An incomplete catalogue must never claim a complete empty result.
- Keep all changes under the backend PR flow; merge is already authorized.

## Tasks

1. Add failing spatial-prefilter tests, implement/backfill RTree rows, preserve exact geometry filtering; run existing mirror tests. Files: backend/python/irsa_mirror.py, backend/tests/test_irsa_mirror.py.
2. Add a separately tested builder in backend/python/irsa_catalog.py and backend/tests/test_irsa_catalog.py. Discover directory partitions, schedule first samples across all partitions before deeper pages, preserve checkpoints and retries, bound workers and process runtime. Root wires its CLI to the existing script.
3. Switch Scala ingestion to catalogue batches and add independent status polling. Configure bounded concurrency and a persistent catalogue budget; preserve subprocess/search limits.
4. Run local Python and Scala checks, obtain independent code review, open and merge PR, wait exact-revision deployment gates. Verify live catalogue growth and searches against real FITS metadata; record actual coverage honestly.

## Source evidence

Official directory structure and releases: https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/
Public mirror: https://irsa.ipac.caltech.edu/cloud_access/
No global independent metadata table was verified; target-specific ObsCore tables are not a general catalogue.
