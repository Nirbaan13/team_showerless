# Native v3 data expansion, protocol version 2

This is an append-only extension of `ML-NATIVE-V3-DATA.AI.md`. Its original declarations, source manifests, 104 native files, code hashes and audit remain unchanged. The coordinator requested stronger parent-level evidence before any final pixel access: add six development validation parents and six quarantined final parents. The complete declared target becomes eight training, eleven development validation and ten independent final parents.

The declaration `/tmp/spaceapps-v3-native-data/expansion-v2/partition-plan.json` was persisted **before querying the new fields or opening any pixels**. Its SHA-256 is `75dd1751b06852b1f6430ae34a0945456621ca7513b5638a5ede0ec19647d05a`. It binds exact coordinates, split, scientific stratum, preferred detector, metadata selection rule, original source hashes, and acquisition source hash. The source code is `backend/inference/experiments/v3_data/expand_v2.py`.

## Coordinates and scientific strata

Coordinates were selected as fixed Galactic longitudes at latitude zero for crowded-plane stress, and at latitude plus or minus 50 degrees for off-plane fields, then transformed to ICRS. Geometry alone was used to enforce more than eight degrees from every previous and newly declared parent. The actual minimum is 9.2026 degrees. Coordinates were not selected using model scores, candidate counts, pixels, injection outcomes, or recovery performance.

| Parent | Split | Galactic l,b (deg) | ICRS RA,Dec (deg) | Preferred detector |
|---|---|---|---|---|
| validation06 | Development validation | 45,0 | 288.4275759,10.7237033 | 1 |
| validation07 | Development validation | 90,0 | 318.0043815,48.3296372 | 2 |
| validation08 | Development validation | 140,0 | 46.8132814,58.2977051 | 3 |
| validation09 | Development validation | 50,50 | 238.7463378,31.1454092 | 1 |
| validation10 | Development validation | 160,-50 | 35.7948783,6.1519051 | 2 |
| validation11 | Development validation | 280,50 | 178.1156476,-10.2275287 | 3 |
| final05 | Quarantined final | 10,0 | 271.9404223,-20.2900295 | 1 |
| final06 | Quarantined final | 70,0 | 301.8661880,32.4424569 | 2 |
| final07 | Quarantined final | 190,0 | 91.9404223,20.2900295 | 3 |
| final08 | Quarantined final | 0,50 | 225.5362254,2.1950040 | 1 |
| final09 | Quarantined final | 120,50 | 197.6899661,67.0181134 | 2 |
| final10 | Quarantined final | 280,-50 | 44.1650668,-61.1831929 | 3 |

## Metadata-only temporal selection

For each detector, examine metadata windows starting at an exposure with at least three unique physical OBSIDs in its first 1.5 hours. Retain the earliest up-to-four short-cluster epochs. Add evenly spanning available metadata follow-ups to reach at most eight total epochs. Selection priority is: eight epochs spanning at least two hours in a 48-hour window; six or seven such epochs in 48 hours; eight in a 168-hour window; six or seven in 168 hours; otherwise keep the constrained earliest short group and report the missing coverage explicitly. Prefer the declared balanced detector within the best feasible tier, then the earliest physical date. No final field is removed for poor detection or ranking performance.

All twelve requested fields satisfy the first tier: **eight unique native exposures, span at least two hours, and remain within 48 hours**, using their preferred detectors. Thus both six-field sets retain two parents per SWIR detector. Their exact selected exposure metadata were saved before byte acquisition in `expansion-v2/selected-groups.json`, SHA-256 `e206f893d483034a6c596226fd69120c4c1ec3aede1de9ed2a0c47fa7d7bbfac`. Physical OBSIDs do not overlap the original seventeen parents or each other.

New development validation spans are approximately 47.32, 27.77, 45.73, 37.61, 39.21 and 21.32 hours. New final spans are approximately 26.16, 29.50, 42.58, 29.48, 29.49 and 47.40 hours. These are temporal coverage descriptors; fast sources may leave the small native cutout and slow sources may self-subtract. Every evaluation must report all planned trials, actual finite-center/support-eligible subsets, displacement, and preexisting-match ambiguity. No trajectory may be moved into coverage after inspecting a result.

## Primary and secondary final variants

Before any final pixels, the coordinator predeclared the **augmented eight-epoch variants as the primary final experiment where available**, across the original four and new six final parents. Original short clusters are secondary variants. They are correlated derivatives of the same ten sky parents and must never inflate the final sample size. Every version, crop, detector and epoch of each physical OBSID remains in its original parent and split.

New augmented native data live at `expansion-v2/development/<validation-parent>-augmented/` or `expansion-v2/quarantine_final/<final-parent>-augmented/`. Each directory has successful `downloads.json` rows with exact URL, hash, physical OBSID, detector and MJD bounds. `materialize-short` creates same-parent symlink-only secondary manifests beneath the corresponding `variants/<parent>-short/` directory. Original data and the original protocol retain their existing paths and hashes.

All final FITS remain opaque byte streams: download, exact hash, byte count and primary-header signature checks only. No final FITS reader, image array, injection, detector output, feature or model score may be used before the coordinator declares its frozen model, detector/preparation settings, evaluation-source hashes, protocol hash and final source hashes. This data agent does no fitting or final evaluation.

## Resource and audit boundaries

Use the shared science interpreter `/home/usatovpavel/edu/UtilsAI/.venv/bin/python`; no new environment. Acquire at most four HTTP requests concurrently, including documentation downloads. Keep this task within two CPU cores and four GiB RAM and preserve at least ten GiB globally available. Initial verification during acquisition found 47 GiB available. Transient HTTP errors receive bounded retries, and unresolved failures remain explicit rather than invented data.

`audit_expansion_v2.py` writes a separate `expansion-v2/audit-expanded-v2.json`, rechecking all original declaration/audit/handoff hashes, new-field geometric separation, physical OBSID disjointness, exact acquired hashes, and FITS-block signatures. Development-only FITS checks validate mission extensions, detector/ePSF frame, physical OBSID and precise midpoint consistency. Its final branch does not invoke a FITS reader. The prior audit file is never overwritten.

## Verified ePSF orientation chain

This conclusion uses the official physical-coordinate definition, not just a `sky` keyword. The [SPHEREx Explanatory Supplement v2.1](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf), dated 2026-11-10, specifies in section 4.2.3, page 59, equation 24 that the ePSF is evaluated at the **native detector-pixel-center offset from the source**. Sections 4.1.2 and 4.2.3 describe reconstruction from native L2 stellar cutouts and five-times native sampling; the pixel response remains included. Appendix C on page 81 describes `DETCOORD=sky` as the shared SWIR view obtained by flipping MWIR x. It does **not** mean that an ePSF stamp is already ICRS north-up. The official [IRSA ePSF tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/), sections 4.3 and 6.2, supplies the parent-image coordinate mapping and zone lookup.

The correct SWIR chain is therefore: use the native IMAGE WCS to locate the source; map cutout coordinates to parent pixels with CRPIX1A/CRPIX2A for the local ePSF-zone lookup; sample ePSF columns along increasing native x and rows along increasing native y at native pixel centers; then project that native response through the native-to-registered WCS pull map **once**. Rotating a stamp to north-up before that projection would apply an additional unintended rotation. No extra pixel convolution is justified.

`orientation_evidence.py` checks this chain on twelve allowed development frames spanning all three SWIR detectors. It passes an asymmetric marker at native offset (+1,+2) through the same native ePSF sampler and registered-grid pull coordinates used by evaluation, verifies the native marker lands on the expected IMAGE axes, then compares its projected centroid with the independently WCS-transformed expected point. The largest registered centroid difference was **0.02415 pixel**; local WCS Jacobians retain the actual nontrivial rotations. Both IMAGE and EPSF use the common sky/SWIR frame in all twelve probed frames. No detector or ranker is invoked, and no final pixel is accessed.

The machine-readable evidence is `expansion-v2/evidence/orientation-evidence.json`. The exact official PDF is retained at `expansion-v2/evidence/SPHEREx_Expsupp-v2.1.pdf`, SHA-256 `9f3085cea74c6cdb647cc373bef27aaae50e394d348402e68ea2558ea06011cd`, with extracted text beside it. This establishes the documented SWIR coordinate interpretation and numerical implementation consistency. It does not independently validate empirical ePSF shape fidelity or color-dependent flux. MWIR detectors 4–6 remain unsupported here until their flip and zone-coordinate handling are explicitly verified. Final files must still pass detector/frame assertions after the coordinator's freeze before any final injection proceeds.

## Completed acquisition and separate handoffs

The expansion acquired all **96 additional native MEFs**: 48 development validation and 48 quarantined final files. Combined with the unchanged original acquisition, this is **200 native MEFs / 810,074,880 bytes across 29 independent parents**: eight training parents (43 files), eleven development validation parents (77 files), and ten quarantined final parents (80 files). The ten primary final manifests each contain exactly eight physical epochs. Secondary short manifests are symlink-only views of these same parents and add no independent units.

All new files have explicit successful source URLs, byte counts, SHA-256 hashes, physical OBSIDs, detector and physical MJD bounds. The completed audit checks zero physical-OBSID overlap across parents/splits, all original artifact hashes unchanged, and the required new-field separation. All 48 new development validation files pass mission-HDU, detector/ePSF-frame, physical OBSID and precise-midpoint checks. All 48 new final files remain opaque hashed bytes with FITS signature/block checks; their pixels were never opened. All twelve selected groups retain eight planned/acquired exposures and have no temporal feasibility fallback or unreported missing epoch.

`build_expanded_handoff.py` creates three distinct outputs: `expansion-v2/development-handoff-v2.json` contains only the six new development validation parent handles and metadata; `expansion-v2/final-byte-audit-v2.json` contains the ten primary final parent manifests and exact byte hashes, intended only for the coordinator before freeze; and `expansion-v2/data-handoff-v2.json` binds all declaration, audit, source, protocol and orientation evidence hashes. It records the official PDF URL, version/date, pages, exact PDF hash, asymmetric marker source hash, and numerical evidence hash. Creating those metadata files does not authorize final pixel access or freeze a model.
