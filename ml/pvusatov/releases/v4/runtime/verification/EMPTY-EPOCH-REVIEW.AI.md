# Read-only empty-epoch amendment review

Reviewed the coordinator-owned native injection helper and its controlled tests without opening final pixels or outcomes. No source edits were made.

Helper SHA256: `dfd829e310a74e5bd446a439af9560386bdfb96f5b01386178e32eed024bcf5b`.
Test SHA256: `d2d78ecfb92495e41a3e80e17f7a3798f79c65bf7564c426ad56f3ccb5cbe0f9`.
Runtime prepare SHA256: `27ef087aa19f394eaf16ee19c0801ed6c7557a79a7ea77b3410445363f4624ec`.

The helper preserves the original RNG sequence, origins, velocities, all eight times/positions and all270 planned derivatives. It excludes only wholly nonfinite images from the background-MAD reference. A nonempty image with zero, invalid or nonfinite MAD fails normalization instead of being silently omitted; fewer than three valid references also fails. The per-image median recentering skips wholly blank images, retaining their NaNs. Response normalization and its declared legacy fallback remain unchanged, so this amendment does not constitute a new brightness policy or fitting operation.

Seven controlled tests passed in1.02s. They verify byte-identical images/identity fields for all270 nonempty trials; retained blank epochs with seven references; exactly three useful epochs; rejection of invalid nonempty noise; and unchanged supported-response fallback behavior. These tests use toy arrays/stub responses and read no actual final files or model scores. The separate runtime coverage tests verify retained physical identities/times and a rendered black zero-coverage frame.

No new material blocker found in this limited review. The original infrastructure failure, amended source freeze and allplanned failure accounting remain the coordinator's provenance responsibility; no score-based model/detector change is supported by this review.
