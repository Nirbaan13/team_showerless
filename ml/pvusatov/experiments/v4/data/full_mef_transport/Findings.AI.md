# One old-TRAIN full-MEF transport validation

The same full MEF preserves the physical product and the requested sky ROI in this predeclared old-TRAIN01 case. It does **not** reproduce the server-cutout preparation exactly. The full file restores 43 usable ROI edge samples clipped by the 70 × 70 server cutout, which changes the per-frame background median and therefore all 3,132 previously finite samples in that frame. Exact stack parity fails and remains a failure; no criterion was relaxed.

This is engineering evidence for one transport substitution. It is not evidence of confirmed motion, a model result, general transport parity, or performance on the two new acquisition failures. No labels, detector, feature extraction, model predictions, fitting, new-native data, holdout data, or FINAL data were read or run.

## Frozen case and acquisition

The selection was the first `native['v4-train01']['input_sources']` entry in the preexisting association-pilot protocol. The frozen plan SHA-256 is `ee35789cf4c24d9ac650735e7c20636e5a9b06b08ac92d4af99c815ea2b4f03e`; it was recorded and sent before HEAD/GET. Selection did not depend on pixels or comparison outcomes.

The full URL was obtained only by removing the original `center` and `size` query parameters. Scheme, host, artifact path, release `dr1`, detector directory `1`, product name and processing token `l2b-v27-2026-226` remain identical. HEAD returned 200 and 59,852,160 bytes, below the frozen 64 MiB per-product limit. One GET succeeded, receiving exactly 59,852,160 bytes, below the 70 MiB traffic limit. No second request, object substitution, new observation query or frame selection occurred. Raw FITS remain in `/tmp/spaceapps-full-mef-transport-old-train01/`, outside Git.

The unchanged V4 preparation source has SHA-256 `27ef087aa19f394eaf16ee19c0801ed6c7557a79a7ea77b3410445363f4624ec`. Both calls use the same original eight old-TRAIN observations, center `(228.745009, -69.43558622)` degrees, 6 × 6 arcminute requested region, 6.15 arcsecond north-up TAN pixels, and `motion` mask policy. The intervention replaces only the first file path, its transport URL and its checksum; the remaining seven inputs and all physical/frame identifiers are unchanged. The resulting grid is 8 × 59 × 59 in both calls. Source snapshots are included for inspection; execution uses the exact protected current V4 source.

## Identity, native data and geometry

Both FITS headers report `OBSID=2026W07_2A_0437_1`, detector 1, `MJD-AVG=61085.840265391`, `DATE-AVG=2026-02-14T20:09:58.930`, software `VERSION=7.0.5` and units `MJy / sr`. The software version is distinct from the product processing token in the archive path. All prepared physical metadata, ordered times, frame IDs and grid headers match exactly after excluding the expected input checksum, size and access-URL differences.

The full science HDUs are 2040 × 2040; the cutout science HDUs are 70 × 70. Both retain EPSF and wavelength-table extensions. The cutout corresponds to full-array zero-based offset `(220, 1037)`. At WCS-corresponding integer native pixels, IMAGE, VARIANCE and ZODI arrays are bitwise equal; FLAGS values are exactly equal. The FLAGS comparison arrays have different endian representations after advanced indexing, so that comparison is not described as bitwise equal. FITS BITPIX/scaling metadata agree.

The merged science headers differ only in NAXIS and primary/alternate CRPIX origins; celestial reference values, PC matrix, SIP distortion and physical metadata agree. Native coordinate differences after removing the known offset reach `2.842170943040401e-14` pixels in x and `2.291500322826323e-13` pixels in y. The pixel-to-world/inverse-WCS rounding diagnostic reaches `1.651596903684549e-08` pixels and is reported separately from the direct same-sky inverse-WCS comparison.

## Observed preparation differences

| Quantity | Actual comparison |
|---|---|
| Full packet finite samples | 24,236 cutout; 24,279 full |
| First-frame finite samples | 3,132 cutout; 3,175 full |
| Added/lost usable samples | 43 added; zero lost |
| NaN/finite mask differences | 43; all in the replaced first frame |
| Common finite image values differing | 3,132 |
| Centered image maximum absolute difference | 0.0001349492123257079 MJy/sr |
| Centered image maximum symmetric relative difference | 1.0, including near-zero median-centered values |
| Common projection before background subtraction | Max absolute 2.8625990466935036e-12 MJy/sr; max relative 1.2290308402013771e-12 |
| OUTLIER mask | Bitwise equal across all 27,848 samples |
| BLOOM mask | Bitwise equal across all 27,848 samples |
| Relative times | Bitwise equal; match the preexisting protocol exactly |
| Other seven prepared images | Bitwise equal |

All 43 added usable samples lie outside the cutout's native interpolation domain; none lies inside it. Requested grid positions span cutout coordinates x `[-1.8586856126458313, 71.74187261818979]`, y `[-1.8753773202202537, 70.03283081540805]`, versus native bounds `[0,69]`. Thus the coverage difference is geometric clipping, not merely floating-point noise. Inside the cutout domain, support differences reach only `1.7763568394002505e-13`; the usable mask does not change there.

The background median changes from `0.20171496173405234` to `0.20158001252377597` MJy/sr, a full-minus-cutout delta of `-0.00013494921027637496`. After diagnosing that median shift, the remaining centered common-pixel discrepancy reaches `2.8622937353617317e-12` MJy/sr, consistent with the independently measured interpolation roundoff. This diagnostic does not overwrite the original stack or redefine parity.

The full-MEF route is scientifically faithful to the same product and requested ROI in this case, while producing measurably different coverage and background normalization from this particular server cutout. The preparation returns finite signal for additional requested positions rather than changing the requested region. This finding supports using the same-artifact full product as an explicitly recorded transport fallback, with provenance and coverage differences retained; it does not establish universal equivalence or any scientific candidate claim.

## Integrity and resources

Every original eight-frame file, association protocol, V4 runtime Python source, and V4 model-directory file has the same SHA-256 before and after validation. The model files were hashed only; no model was loaded. Observed peak RSS was 640.36 MiB. Scripts set a 2 GiB address-space limit and configure numerical libraries to at most two threads. The download used the declared first attempt within the frozen timeout/traffic policy.

`frozen-plan.json`, `download-ledger.json`, `results.json` and `difference-diagnosis.json` retain numerical counts, maxima, headers, identities, checksums and exact source URLs. No raw or prepared pixel arrays are written to this directory. `validate_transport.py` is the pre-GET frozen executable; `diagnose_differences.py` is a separately hashed post-observation explanation of the already measured discrepancy. Re-running the acquisition script intentionally refuses to reuse or overwrite the existing full artifact.
