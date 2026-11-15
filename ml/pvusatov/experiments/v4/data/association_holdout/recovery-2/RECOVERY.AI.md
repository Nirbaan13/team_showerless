# Native acquisition recovery 2

The bounded retry acquired **0/12 planned parents and 0/96 FITS products**. Five complete metadata responses produced forty metadata-selected exposures, but every corresponding parent failed the original full-parent footprint eligibility rule. Seven fields remained unresolved after both HTTP 502 attempts. No science pixels, models, fits, injections, or quality scores were accessed. Native inference remains unauthorized and unavailable.

The new transport plan was frozen at 2026-11-15 15:27:07 UTC with a 45-minute wall budget ending 16:12:07 UTC. Its SHA256 is `6ac9267b198af4661ed99b0cf4b8fdf8cdda1fe8cf0139035cfc5d69a8a23102`. The retry retained the twelve original coordinates, original query domain and MAXREC 512→4096 completeness rule, metadata selection order/cadence/detector preferences, 438 physical observation exclusions, and the original four-degree s_region vertex-distance bound. It used at most two metadata workers, two attempts per URL, a 90-second request timeout, four product workers, and a 96-file/500 MB product cap. The MAXREC 1 transport diagnostic supplied no selection data. No additional field, time window, or metadata URL domain was introduced.

The original plan `5d58c00b91c0eeaa7518c78917cf0ed49a45e720d66da98a85f51ae120efc107` and seed amendment `15e2636fbc66ee73df2d250b4e1d5a3102cbc805b54cf6874a4d030d833c5853` remain unchanged. Parent seeds are 4110001–4110012, from the amendment; the original plan's 3900001–3900012 values remain superseded. Both declarations are pinned by association freeze `ae981b56f43c8a14cd6dee9ce61c48853ea7c90b63eca8ddcf586e0a3e3dbbdd`. The prior closed acquisition capsule and handoff were preserved.

| Parent suffix | Metadata rows | Selected detector | Selected exposures | Largest s_region vertex distance | Outcome |
|---|---:|---:|---:|---:|---|
| 03 | 219 | D3 | 8 | 4.367766° | Original 4° eligibility bound failed on 2 exposures |
| 04 | 240 | D1 | 8 | 4.190062° | Original 4° eligibility bound failed on 2 exposures |
| 06 | 245 | D3 | 8 | 4.041592° | Original 4° eligibility bound failed on 1 exposure |
| 07 | 234 | D1 | 8 | 4.520727° | Original 4° eligibility bound failed on 5 exposures |
| 10 | 262 | D1 | 8 | 4.275785° | Original 4° eligibility bound failed on 2 exposures |
| 01, 02, 05, 08, 09, 11, 12 | unresolved | — | — | — | HTTP 502 on both attempts; archive coverage unresolved |

The five successful responses had complete QUERY_STATUS OK, without truncation or overflow. Selection used the original functions compiled from hash-checked source without editing those sources. All selections were sealed in `selection.json` before the product phase. The original footprint bound then rejected all five candidates; no alternate exposure, detector, or field was substituted. The eligibility report records every selected s_region and its spherical vertex-distance calculation. These are metadata geometry checks and do not establish pixel quality or sky coverage.

`guarded-handoff.json` is the new externally hashable candidate handoff. Its SHA256 is `a8fe375acd9bf83f5d6cd17c6fbd14eb9677fe9f9d31292c98da349f9b6afd39`. It binds the prospective declarations, new transport plan, sealed selection, byte/header audit, unchanged acquisition sources, all twelve metadata evidence records, and `strict-guard.json`. All twelve parent identities remain in `planned_groups`, with corrected seeds and explicit missing reasons; `groups` is empty. `evaluation_ready` and `inference_authorized` are false. A partial or empty handoff cannot pass the frozen twelve-parent native release guard.

The strict guard replayed the metadata selection, checked exact official SIA parameters and XML column/row completeness, verified source/response hashes, excluded-observation accounting, fixed parent identities, and spatial separation. It returned `PASS_INCOMPLETE_QUARANTINE` with `strict_native_ready=false`. There were no FITS products on which to run the available manual header scanner. Its pixel-read and inference flags remain false.

Raw metadata responses and complete row records remain outside Git at `/tmp/spaceapps-association-native-recovery2`. Repository evidence contains source code, compact JSON, and this document. `publication-manifest.json` lists the publication files and raw metadata hashes. The original zero-parent capsule is not overwritten. A future retry or scientific protocol amendment would require a separate prospective declaration and root authorization; this result makes no no-coverage or recovery-performance claim.
