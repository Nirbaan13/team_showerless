# wise0855: independent post-inference astrometry audit

Result: **RECOVERED**. 1 of 6 returned Ivan candidates passes the frozen criterion.

Eight real W2 visit coadds span 2010-05-04T22:03:56.931551Z to 2024-04-17T00:21:12.868559Z (13.952 Julian years).

Rank 1 matches all 8 candidate epochs; maximum residual 2.886846 arcsec (threshold 4.125 arcsec). Reported motion: 8.173881144 arcsec/year; published total: 8.090339919 arcsec/year.

Exact HTTP response SHA-256: `5f4b099d3968b1f76dc680bb84e0f6febd4dc0bb0554aba419dfd290c7ed4034`.

Read-only external truth SHA-256: `d79d6f0ff1395af128764a1caca2f22bac4e52a8f73d0777edd1499522eec1be`; source: https://arxiv.org/html/1404.6501v1.

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
