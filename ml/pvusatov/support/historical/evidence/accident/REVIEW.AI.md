# accident: independent post-inference astrometry audit

Result: **Not recovered among the returned 20 candidates**. 0 of 20 returned Ivan candidates passes the frozen criterion.

Eight real W2 visit coadds span 2010-02-13T16:52:36.440687Z to 2024-02-14T00:00:30.324672Z (13.999 Julian years).

The unchanged response contains a returned subset. Its full comparison counts are {"leave_one_out": 24, "shared_median": 21}. This audit makes no recovery claim about candidates omitted from the response and does not infer why the object is absent.

Exact HTTP response SHA-256: `a5e2d096e016a5a8e443df5a7678f60471f26f48ce6e8f8611e46d43ffc1980e`.

Read-only external truth SHA-256: `84ac70de2413ff49176c7bd8f146e18227ba72197b3f0586da6385cbccb0a211`; source: https://arxiv.org/html/2106.13408.

Truth is used only in this separate audit, after the completed blind response. Actual sky_deg is checked against the returned target WCS and published positions propagated to each real UTC midpoint. No detector, selection, ranking, training, image changes, parallax fit, or motion fit occurs here. Source bytes, actual dates, residuals, and all 32 declared raw-asset checksums are in recovery-audit.json.

The source snapshot records observed local development files for unfrozen local QA; it is not an executed-image attestation.

- Known historical objects and fixed preselected fields/epochs; not an unbiased search or population completeness estimate.
- The matching threshold is fixed at 1.5 pixels (4.125 arcsec), with at least three points and every returned point required to pass.
- Native W2 visit coadds are not individual exposures; actual mission gaps and visit time intervals remain.
- Artifact/outlier/bloom masks unavailable; inverse variance and coverage do not establish absence of artifacts.
- No per-epoch PSF homogenization or independent stellar centroid refinement; resampling covariance not represented.
- Published linear motion used without fitted parallax, perspective acceleration, or new astrometric fitting.
- Reported proper motion is the existing Ivan inference value converted with 8766 hours/year; no audit fit is performed.
- This is a targeted known-object recovery check, not a new discovery or proof that every returned candidate is astrophysical.
