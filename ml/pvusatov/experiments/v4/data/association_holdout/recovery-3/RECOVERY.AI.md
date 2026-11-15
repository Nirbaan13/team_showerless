# Native acquisition recovery 3: eligibility-order amendment

The bounded acquisition obtained **nine complete parents and 79 header-verified physical exposures**, totaling **319,849,920 bytes**. All twelve original parents remain planned. Parent 08 has seven of eight fixed products because its remaining product returned HTTP 503 twice; parents 05 and 09 remain unresolved after two HTTP 502 metadata attempts each. The strict guard returned `PASS_INCOMPLETE_QUARANTINE` with `strict_native_ready=false`. Native inference remains unauthorized. No science pixels, features, quality scores, models, fits, or injections were accessed.

This is an explicit **metadata-informed scientific protocol amendment**, declared after synthetic unblinding and recovery-2 metadata inspection, before any native pixels or native scores. Recovery 2 first selected eight exposures, then rejected an entire parent if any selected full-parent s_region vertex lay beyond four degrees from the fixed center. Recovery 3 applies that same four-degree metadata eligibility condition before the unchanged detector and temporal selector, and checks the selected eight again afterward. Selected exposure identities therefore change. This is not equivalent to the original selection or a transport-only retry.

The amendment retained all twelve fixed coordinates, the corrected 4110001–4110012 seed reservation, 438 physical observation exclusions, the numerical four-degree footprint bound, preferred detectors and fallbacks, earliest three exposures within 1.5 hours, deterministic spread to eight within 48 then 168 hours, the two-hour span preference, and the original ROI, pixel scale, mask, and transfer caps. No field or exposure was substituted following a product failure, and no bound was relaxed.

The new plan was frozen at 2026-11-15 15:41:39 UTC, before product transfers, with a new 45-minute deadline of 16:26:39 UTC. Its SHA256 is `e9988d03b76f66bb6ccb741e3effd0ca03345787613ba161d46c5364315d2463`. Root was given this digest before acquisition began. It binds the unchanged original cohort declaration, seed amendment, association freeze, previous handoff and selection, exact cached response hashes, wrapper, and unchanged acquisition engine and helper sources.

The five complete recovery-2 responses for parents 03, 04, 06, 07, and 10 were reused byte for byte without network queries. Only the seven unresolved original fields were queried, using the original exact SIA collection/coordinates/radius, MAXREC 512→4096 complete-only rule, two metadata workers, two attempts and a 90-second request timeout. These new metadata requests used `Cache-Control: no-cache`. No TIME restriction or alternate coordinate/cutoff was introduced. Five additional fields returned complete metadata; 05 and 09 remained unresolved. All ten complete responses had QUERY_STATUS OK without truncation or overflow.

All ten eligible selections were sealed before the 80 product transfers. The selection SHA256 is `c927086936acae0f8c13f02cdc105b47d326cef3085df534abb9debbab862a45`. Every selected parent retained its preferred detector, eight distinct physical epochs, a 48-hour window, a span above two hours, and the four-degree bound.

| Parent suffix | Detector | Span hours | Largest selected vertex distance | Complete products | Outcome |
|---|---:|---:|---:|---:|---|
| 01 | D1 | 42.582 | 3.973136° | 8/8 | Complete quarantine |
| 02 | D2 | 24.461 | 3.904812° | 8/8 | Complete quarantine |
| 03 | D3 | 9.915 | 3.843674° | 8/8 | Complete quarantine |
| 04 | D1 | 37.619 | 3.910904° | 8/8 | Complete quarantine |
| 05 | — | — | — | 0/8 | Metadata HTTP 502 twice; unresolved |
| 06 | D3 | 44.111 | 3.874117° | 8/8 | Complete quarantine |
| 07 | D1 | 26.113 | 3.987428° | 8/8 | Complete quarantine |
| 08 | D2 | 45.779 | 3.922465° | 7/8 | One fixed product HTTP 503 twice |
| 09 | — | — | — | 0/8 | Metadata HTTP 502 twice; unresolved |
| 10 | D1 | 29.482 | 3.992728° | 8/8 | Complete quarantine |
| 11 | D2 | 35.918 | 3.846439° | 8/8 | Complete quarantine |
| 12 | D3 | 9.732 | 3.825077° | 8/8 | Complete quarantine |

For the five cached fields, the new selections retained 5/8 old physical observation identities for 03, 4/8 for 04, 6/8 for 06, 1/8 for 07, and 6/8 for 10. `selection-comparison.json` reports every old/new identity and added/removed intersection, along with prefilter counts. The remaining untransferred product is parent 08, detector D2, physical OBSID `2025W47_1A_0738_4`; its exact fixed URL and both failures appear in `byte-header-audit.json`. Failure did not trigger selection changes.

`guarded-handoff.json` has SHA256 `df5e7fb7a20eedfd38db6392eab74b803f25f1ac0583ecbd9fd8e696a8390367`. It binds the amendment, sealed selection, original plan and seed amendment, metadata evidence, header/byte audit, sources, and strict guard. Its `groups` contain the nine complete parents. `planned_groups` retains all twelve identities and all 79 verified exposures, including the seven from partial parent 08; missing evidence remains explicit. Each verified image records its official URL, quarantined path, SHA256, byte count, physical OBSID, detector, real header MJD and UTC midpoint, native header layout, and ROI. Every physical ID is unique and outside the 438 exclusions. Spatial provenance and the original limited full-parent overlap scope remain explicit.

The new guard independently replays the footprint-prefilter and unchanged temporal/detector selector, verifies cached metadata hashes and exact query parameters, checks XML row completeness, compares cached old/new selection identities, rehashes all acquired products, and repeats manual header-only engineering checks. Header checks read HDU headers and skip payloads; full-file reads are hashing only. The guard verifies OBSID, detector, extension layout, celestial WCS header presence, native dimensions, ePSF coordinate frame, and real midpoint against selected metadata. It performs no pixel-quality filtering.

Raw FITS and metadata remain quarantined outside Git at `/tmp/spaceapps-association-native-recovery2/recovery-3`. Repository evidence contains source, compact JSON, and this document; `publication-manifest.json` lists publication and raw hashes. The original and recovery-2 capsules remain unchanged. No available subset authorizes native inference: all twelve parents, a separate root authorization binding the exact external handoff digest, and independent review are still required. This partial acquisition establishes neither missing sky coverage nor recovery performance.
