# Conditional native-variance propagation

Under the explicitly conditional assumption of independent Gaussian native-pixel errors with the supplied calibrated VARIANCE, registration creates substantial neighboring-pixel covariance. In 72 fixed TRAIN patches, the exact amplitude-plus-constant template uncertainty is **1.002–1.392 times** its registered-diagonal approximation (median **1.295**). This is an engineering result under that input assumption, not measured instrument covariance or a calibration factor for the current global-MAD feature proxies.

The plan was fixed before outcomes: `data/physics_validation/variance_propagation/plan.json`, SHA-256 `54a4e8c243d7bb44aad61944d723f8527fa19fb316de02010420544feab54394`. It uses all eight physical exposures from each of new TRAIN01/02/03, D1–D3: **24 frames in three sky parents**. Three patch categories are fixed: fractional-phase center, registered ROI edge, and the nearest declared mixed-support boundary. All 72 planned patches were available. Each frame has 2,048 conditional draws, 49,152 frame draws total, from fixed parent/epoch seeds. These draws are not independent astronomical fields or training examples.

For native valid mask m, raw bilinear weights w and accepted support s, the normalized registration matrix is A_ri = w_ri m_i / s_r; rows with support below 0.995 or outside native coordinates are unusable. Full TAN-SIP coordinates and constant-zero boundary behavior match immutable production preparation. The correct covariance is:

```text
C = A diag(native_VARIANCE) A^T
Var(registered_r) = sum_i A_ri^2 V_i
Cov(registered_r, registered_s) = sum_i A_ri A_si V_i
```

Linear interpolation of variance uses first-power weights and is a different quantity. Here its per-frame median overstatement of the correct registered diagonal is about **2.4×**. Production preparation uses VARIANCE as a validity mask; this study separately evaluates uncertainty propagation. Neighboring registered horizontal-pixel correlation medians are about **0.268–0.308** under the diagonal-native assumption.

A fixed sigma-0.8 Gaussian template plus a constant background is fit by weighted least squares using the correctly propagated registered diagonal. The amplitude estimator a has zero response to a constant. Its true conditional variance is aᵀCa; its diagonal approximation omits off-diagonal terms. The global median recentering is applied explicitly to every realization and removed through this nuisance fit, not ignored.

| Detector | Fixed patches | Minimum σ ratio | Median σ ratio | Maximum σ ratio |
|---|---:|---:|---:|---:|
| D1 | 24 | 1.002 | 1.277 | 1.392 |
| D2 | 24 | 1.146 | 1.318 | 1.376 |
| D3 | 24 | 1.082 | 1.312 | 1.379 |

Monte Carlo sample variances support the analytic propagation: **70/72 marginal 95% intervals** contain the analytic value; the largest variance discrepancy is **2.62 Monte Carlo standard errors**. Patches share draws and can overlap, so this is not an independent-binomial global hypothesis test. Median recentering changes fitted amplitudes by at most **1.943e-15**. The explicit signal operator agrees with immutable prepare to **7.106e-15**. Three additional truthful conditional native-FITS spot checks also agree to at most **7.106e-15** and are deleted afterward.

The [SPHEREx Explanatory Supplement](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf), verified version 2.1 dated 2026-11-10, pages 13/29, and actual TRAIN headers establish IMAGE units MJy/sr and VARIANCE units (MJy/sr)². No gain/electron conversion, new source Poisson realization or detector-physics covariance is inferred. Original VARIANCE, FLAGS, ZODI, EPSF, WCS and physical observation metadata remain unchanged in conditional copies. Those copies are explicitly research perturbations rather than extra physical observations. There is no claim about real-object precision, calibrated significance, absolute point-source flux, saturation updates or nonlinear/shared leave-one-out temporal residual covariance. No model, detector, training or FINAL input is used.

`operators.py` is reusable for exact masked bilinear covariance and affine nuisance-estimator calculations. `run_study.py` fixes all inputs, seeds and counts, records every frame and source hash, and refuses to overwrite outputs. A first attempt encountered a Python-list reporting TypeError before any frame/aggregate publication; `attempt01-reporting-error/` preserves its exact source, invocation and log. The fix only uses array absolute values for formatting; the same plan, operators and seeds were rerun. Its toy full-frame regression went red→green. Four further analytic tests cover squared/cross weights, mask/boundary behavior, invalid native variance and median-nuisance cancellation.

Summary SHA-256: `4741f5c38ecd5e8466e02216f2a69b049c25c38acacd095f829b99d1dac36d8c`. Detailed per-frame/patch statistics are in `results.jsonl`; invocation/source hashes and the complete publication manifest remain alongside it. The previous native-source injection study, its outputs, V3 files and V4 FINAL quarantine remain unchanged.
