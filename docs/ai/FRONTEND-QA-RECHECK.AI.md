# Frontend QA repair ledger

Source: draft PR23 and its19 findings, checked against main40cf5da and the live
VPS. WhatsApp Space Apps Challenge messages through2026-11-15T19:54+03 confirm
frontend fixes had been claimed and ML subsequently deployed. Each finding is
retested independently; an earlier claimed fix is not accepted as evidence.

Repairs proceed in QA number order. Isolated Chromium is used because the shared
MCP Firefox profile cannot start. Browser tests exercise the real React app and
mock only HTTP dependencies for reproducible acquisition/error states. They block
public submission/vote/comment writes. Production verification follows deployment.

| Finding | Current status | Evidence / action |
|---|---|---|
| QA-001 | Fixed locally | Reproduced on40cf5da with existing browser regression: archive errors still became synthetic data. Removed synthetic discovery and restored real job lifecycle, image error states, real stack artifacts and cancellation. Build and all13 browser regressions pass; production recheck follows release. |
| QA-002 | Fixed locally | Three browser regressions pass: failed/empty measurements cannot export generated values; retry clears old data; CSV keeps only returned channels/MJD. No target-name molecule inference or synthetic curve fallback. |
| QA-003 | Pending | Cross-target frame identity; Ceres homepage removal already landed |
| QA-004 | Pending | Passive discussion must not submit |
| QA-005 | Previously fixed, verify | PR26 deployed the missing ML HTTP service |
| QA-006 | Pending | Acquisition availability and explicit errors |
| QA-007 | Pending | Processing artifact/mode availability |
| QA-008 | Pending | Detector/artifact agreement |
| QA-009 | Pending | Canvas overlay transforms |
| QA-010 | Pending | Scientific HUD and cursor metadata |
| QA-011 | Pending | Catalogue failures/empty results |
| QA-012 | Pending | Dossier permalink/reload |
| QA-013 | Pending | Mobile playback hit targets |
| QA-014 | Pending | Persisted consensus consistency |
| QA-015 | Pending | Remove unsupported channel selection |
| QA-016 | Pending | Distinct UTC visit labels |
| QA-017 | Pending | Compact readable HUD/labels |
| QA-018 | Pending | Actual model/provenance and score meaning |
| QA-019 | Pending | Declination validation |
