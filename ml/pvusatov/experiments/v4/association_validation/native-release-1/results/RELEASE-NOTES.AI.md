Fixed C596 association research across twelve new native parent fields, 1,620 native injections, twelve controls and 1,000 synthetic fields. This prerelease preserves numeric evaluation evidence; the deployed association policy and model remain unchanged.

Native K1 retrieval changes 304 → 400 and K3 changes 316 → 467. Most net gain is unresolved under the matched three-pixel span diagnostic: resolved K1 changes 232 → 233 and K3 changes 241 → 261. Read `RESULTS.AI.md` and the independent review for parent uncertainty, acquisition amendments, repair history and workload limits.

All 1,632 native records and 6,349,758 hypotheses passed an exact-source independent recount and a second recount from relocated roots with the three original/outside read probes denied. No raw FITS, scoring or model fitting is required for these numeric audits.

Download all six `native-numeric-cache.tar.partNNN` assets and `numeric-cache-manifest.json`. Verify each part's byte count and SHA256 against the manifest before concatenating in numeric order. The resulting uncompressed tar must be exactly 1,482,526,720 bytes with SHA256 `78fd49b821c58e891b9bd05c24f63a42edf2d66e3f682399d5d8d1a0d7936173`. The manifest also binds all 3,267 member files. The Git checkout contains the frozen source closure, checker, safe extraction/proof wrapper and instructions under `ml/pvusatov/experiments/v4/association_validation/native-release-1/`.

Run `portable-proof/prove_portable.py --repo-root /path/to/checkout --cache-archive /path/to/native-numeric-cache.tar --output-dir /tmp/new-native-proof` with Python, NumPy and one math thread. Source/model/calibration bytes are checked as opaque dependencies; raw image pixels and inference are never executed by the recount.
