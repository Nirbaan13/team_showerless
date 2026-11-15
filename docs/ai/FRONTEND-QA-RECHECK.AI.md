# Frontend QA repair ledger

Source: draft PR23 and its19 findings, checked against main40cf5da and the live
VPS. WhatsApp Space Apps Challenge messages through2026-11-15T19:54+03 confirm
frontend fixes had been claimed and ML subsequently deployed. Each finding is
retested independently; an earlier claimed fix is not accepted as evidence.

At the user’s request, remaining repairs proceed in descending QA number order, starting at QA-019. Before each item, compare current main and team updates to avoid duplicating work. Isolated Chromium is used because the shared
MCP Firefox profile cannot start. Browser tests exercise the real React app and
mock only HTTP dependencies for reproducible acquisition/error states. They block
public submission/vote/comment writes. Production verification follows deployment.

| Finding | Current status | Evidence / action |
|---|---|---|
| QA-001 | Fixed locally | Reproduced on40cf5da with existing browser regression: archive errors still became synthetic data. Removed synthetic discovery and restored real job lifecycle, image error states, real stack artifacts and cancellation. Build and all13 browser regressions pass; production recheck follows release. |
| QA-002 | Fixed locally | Three browser regressions pass: failed/empty measurements cannot export generated values; retry clears old data; CSV keeps only returned channels/MJD. No target-name molecule inference or synthetic curve fallback. |
| QA-003 | Fixed locally | Retired Ceres deep link (including detector=2) produces no image draws, frames or candidates. Removed the unverified Ceres image/candidate sequence; unknown preset IDs cannot fall through to generated defaults. Verified packaged 3I/ATLAS remains functional. |
| QA-004 | Already fixed in main, verified | Browser opens a server-qualified 12-vote discussion, advances 20 seconds, and observes zero POSTs with explicit Dispatch still awaiting a click. Existing passive read-only flow retained; QA-014 removed name-based counts and simulated votes. |
| QA-005 | Fixed locally; production route check pending | ML container is healthy and direct port 8001 registry returns real persisted rows. Reproduced frontend 501: Nginx sent registry/discussion requests to retired Scala routes. Isolated Nginx test now passes 13 routing checks; reconnect persisted registry/discussion while native catalogue/image APIs and publication guards retain Scala routes. Added CI and release HTTP probes. Public Hostinger additionally returned SPA HTML for API paths; a same-origin streaming PHP proxy and Apache rewrite retain VPS processing, status codes and resource bytes, with isolated Apache/PHP integration coverage and public release probes. |
| QA-006 | External incident persists; UI handling fixed | Fresh bounded IRSA acquisition cb555dfe-6bff-410c-ac13-ccfad2229df5 failed with archive_http_error / HTTP 502 / retryable=true and no fabricated chunks. Retrying identical parameters created a new job 73d36d2b-4456-437b-85b2-01cc9507b8a9, confirming errors are not permanently deduplicated; that retry also failed with archive_timeout / retryable=true. UI error/retry regression is covered by QA-001/002. Successful fresh IRSA acquisition remains unverified while upstream fails. |
| QA-007 | Fixed locally | Two browser regressions pass: missing difference stays unavailable and Zodi deep links cannot reuse aligned pixels. Layer controls require the corresponding published artifact; removed CSS-only zodiacal subtraction. |
| QA-008 | Fixed locally | Seven browser regressions pass: unsupported detectors clear pixels and tracks, D2/D6 select distinct actual review frames, and all-detector links cannot relabel D6. Removed asynchronous D6 fallback for D2, stale cross-detector candidates and fake composite contrast; All Bands disabled without a composite artifact. Reconciled concurrent main2663ad5 detector coverage UI using actual loaded frame counts; legacy alias/candidate-only links preserve target and detector after hydration. |
| QA-009 | Already fixed in main, verified | Browser records actual canvas transforms for every candidate before/after zoom and pan. All markers retain identical image transforms; main already balanced per-candidate save/restore. |
| QA-010 | Fixed locally | Browser regression verifies actual frame ID/time/dimensions/coverage and requested field coordinates, with WCS and photometry explicitly unavailable. Removed invented fixed celestial grid/PSF/flux/calibration, cursor sky projection and angular ruler; native pixel ruler/cursor account for rendering scale. Existing compact metadata checks also pass. |
| QA-011 | Fixed locally | Three browser checks pass for outage, true empty results, separate Gaia/SIMBAD identities, missing magnitudes and clearing matches on refresh/field change. Removed coordinate-generated sources, invented Gaia IDs, fake cross-identification and indefinite cached fallback; expose per-provider failure/partial status. |
| QA-012 | Already fixed in main, verified | Browser opens PX-000004 directly, reloads without changing identity, and copies a permalink retaining candidate=PX-000004. Existing URL state fix retained. |
| QA-013 | Already fixed in main, verified | Real Chromium taps at 390×844: Play lies above fixed navigation, changes to Pause, advances the visit, and Next remains clickable. No competing layout fix. |
| QA-014 | Fixed locally | Three browser checks pass: registry errors expose no seed records; zero votes and missing checks stay zero/pending in list+dossier; discussion reads the same persisted identity/consensus and has no simulated peer votes. Removed local success on failed record/vote writes. Live legacy routing currently returns 501; handled under QA-005. |
| QA-015 | Fixed locally | Browser regression passes. Removed 102-channel slider, molecular quick-picks and unused selected-channel state; detector controls explicitly describe the image granularity. |
| QA-016 | Already fixed in main, verified | Browser test selects all four actual 2025-12-14 visits (11:01, 12:39, 17:33, 19:06 UTC); each label/title and active frame agrees. No second implementation. |
| QA-017 | Fixed locally | Browser checks at 1500×1000 and 390×844 pass: metadata starts collapsed, expands on demand, and zoom remains clickable. Catalogue labels opt in; only selected candidate names show by default, with the full selected name in metadata. |
| QA-018 | Fixed locally | Two browser regressions pass: stored review selection starts no inference or timed ML progress; live results display server model ID/family/SHA and score meaning, preserving server rank. Removed percent probability styling, fabricated default score/speed, and unused generated stack images. |
| QA-019 | Fixed locally | Main already rejected Dec 91; retained that fix. Two browser checks pass. Reject malformed whole values instead of parseFloat prefixes; document RA wrapping; accessible field errors. |


## Combined verification

After the remaining repairs, the production frontend build and all 44 Chromium
browser regressions passed together. Oxlint exits successfully with existing
React warnings. The isolated Nginx suite passes all 13 native/ML routing cases.
QA-006 remains an external acquisition incident: a fresh successful IRSA download
has not been demonstrated. Release revision and live routing checks follow merge.
