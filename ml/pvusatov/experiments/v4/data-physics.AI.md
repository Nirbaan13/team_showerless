# V4 native pre-registration injection validation

The fixed TRAIN-only experiment confirms engineering consistency between a native IMAGE overlay before immutable production preparation and the historical registered-image injection, for the sampled phases, masks, edges and trajectories. It does **not** validate calibrated photometry, real-object precision, physical motion confirmation or complete detector/noise realism. No model, detector, fitting or FINAL pixels were used.

`data/physics_validation/plan.json` was declared before any native overlay outcome, SHA-256 `8f7ae2a66172df19648f74148f5485c31e0f7c0ae1b6d36b4a65e394556bbdd3`. The fixed inputs are new `v4-train01`, `v4-train02`, `v4-train03` (D1–D3), eight actual exposures each. Seven stationary cases cover four fractional native phases, a native cutout edge, a masked interior and mixed-mask boundary. Moving cases use 0.01/0.1/1/10 registered pixels/hour in directions 0°/45°/90° at the actual physical midpoints, without recentering when sources leave coverage. Amplitudes are 3/12/48 times the median original native robust MAD, with actual values retained in the records.

The independent builder does not call the old sampler/projector. It uses the full celestial TAN-SIP WCS, reconstructs the alternate-A linear cutout-to-parent WCS, selects the documented local native ePSF zone, and samples the ePSF on integer native IMAGE centers at the actual fractional phase. Normalization uses the full untruncated native lattice; crop and mask losses are retained. This surface-brightness amplitude is a **discrete native-pixel sum in MJy/sr**, not calibrated point-source flux.

Each trial copies the original MEF, changes only IMAGE data to true float64 (`BITPIX=-64`) and marks the primary header as a research derivative with original SHA-256. Non-IMAGE arrays, physical OBSIDs, all celestial/alternate/SIP WCS and midpoint metadata remain unchanged. CHECKSUM/DATASUM are regenerated and verified on every HDU; original and derivative file hashes are recorded truthfully. Original archive bytes are rechecked and never overwritten. Derived FITS are deleted after every trial, leaving only manifests and measurements. The deterministic science arrays can be regenerated; FITS checksum-comment timestamps need not reproduce identical file bytes across runs.

| Predeclared stage | Trials executed/planned | Derivative epochs | Runtime errors | Maximum absolute prepared-delta difference |
|---|---:|---:|---:|---:|
| Stationary | 63/63 | 504 | 0 | 3.842e-11 MJy/sr |
| Moving stress | 108/108 | 864 | 0 | 4.379e-11 MJy/sr |

All 1,368 independent zone choices agree with the old comparator, and every tested original frame has SIP. All non-IMAGE arrays, prepared finite/outlier/BLOOM masks, physical observation identities and timestamps were preserved. All scratch FITS were deleted. Native crop retention spans 0–1 across the full stress study; masked stationary response retention reaches 0.232. These losses were measured rather than renormalized away.

Preparation subtracts an epoch median. The stationary study measures a median-shift constant as large as 0.001251 MJy/sr; its prediction differs from the actual constant by at most 1.710e-13. Thus the faithful comparator is the existing **add response, then subtract median** route. Comparing directly with an uncentered response would retain this measurable constant.

The raw moving-stage maximum relative L2 difference remains **1.0** in the original results. It comes from nine exactly zero-response comparisons after the source leaves coverage: the old route's extra median subtraction changes values by at most 6.939e-18, with a median residual of 3.469e-18, while the native route has zero source delta. Across the 744 positive registered-response epochs the maximum relative L2 difference is 4.491e-11; the stationary maximum is 9.009e-11. These are explicitly labeled engineering diagnostics, not revised gates or a hidden exclusion from the original maximum. Moving has 120 zero registered-response epochs, including 81 with no native-crop response and 39 with native response outside the usable registered footprint. Every planned comparison remains recorded.

The [official SPHEREx Explanatory Supplement](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf), version 2.1 dated 2026-11-10, pages 13 and 29, describes IMAGE as calibrated surface brightness and VARIANCE as calibrated variance combining noise contributions. Its verified PDF SHA-256 is `9f3085cea74c6cdb647cc373bef27aaae50e394d348402e68ea2558ea06011cd`; orientation evidence uses pages 52/59/60/74/81 and [IRSA's PSF tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/). Actual new TRAIN headers confirm IMAGE/ZODI `MJy / sr` and VARIANCE `MJy2 / sr2`. A verified per-pixel electron conversion was not established here, so **no shot noise is added and VARIANCE is unchanged**. There is no assumed Poisson conversion, detector saturation/flag update, throughput/SED correction or absolute point-source calibration.

Reusable helpers are `data/physics_validation/native_overlay.py`: `native_response` independently constructs a native response from a guarded development path and known sky coordinate; `write_derivative` writes and audits a truthful research FITS. `run_validation.py` supplies the fixed stationary/moving sky trajectories and invokes immutable `prepare`. The old `project_response` is used only as a comparator. Coordinates remain injection/evaluation truth, never detector/model inputs. Original stage files refuse overwrite. Future studies require a new prospective plan/output location rather than rewriting these results.

Evidence:

- Stationary summary SHA-256: `ee2a441cc68d358d69188347bb7be0b361c8569dd61bb81f42dfdad627460557`.
- Moving summary SHA-256: `841e768ad39a0cc8bc6668156deef7dcf4e76696dbc9d459f5271d3c541726f4`.
- Raw records and invocation source/input hashes: `results-{stationary,moving}.jsonl` and `invocation-{stationary,moving}.json`.
- Preserved-result interpretation: `analysis.json`, SHA-256 `d6a9650c32a6523e04d7803118cf463e80d40f810f16a1365ea872e4cf81c639`.

Four meaningful helper tests first failed and then passed: native axis ordering, phase/edge normalization, actual float64/checksum/non-IMAGE preservation, and quarantine rejection before a reader. The cohort's original four acquisition/header tests also pass. Frozen V3 files and V4 FINAL quarantine remain unchanged.
