# Portable frozen-snapshot audit

Run from any checkout, using Python with NumPy installed:

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
MKL_NUM_THREADS=1 python ml/pvusatov/verification/final/audit_snapshot.py
```

The audit is read-only and prints JSON. `--namespace /absolute/checkout/ml/pvusatov` optionally identifies another checkout; it does not change datasets, models or gates. Failures exit nonzero. No FITS reader, inference model, simulator or original absolute input path is opened. Namespace suffix translation maps frozen source/artifact references to the current checkout without rewriting any historical JSON. Original run-manifest paths are resolved solely through the immutable snapshot index.

The actual audit passed for all **46 files / 62,727,329 bytes**, both immutable model artifacts and original metadata, all **15 scientific sources**, and the four externally recorded summary/test sources. It verifies freeze `2bb68024e0101164f7628074b23e82f07f91480fd5161208e2031c05942dfb75` and summary `3c0be474cc46488b159e72ebf56fd7a0862fea614a5d1de77c45925143386b9b`. Candidate ONNX remains `c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204`; its original metadata remains `983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04`.

All four primary/secondary native/synthetic paired model reports were recomputed from archived candidate labels/scores using the frozen `paired.py`. Every reported count, recall, cohort denominator, macro difference and bootstrap interval matches the published model reports. Integer/structural comparisons are exact; floating comparisons allow absolute/relative `1e-12` for platform rounding. The primary recovery gate also matches; this audit grants no promotion authorization. Native reports retain 2,700 derivatives clustered in ten parents; synthetic reports retain 2,000 fields and 3,998 truths.

**Scope limit:** 59 of the freeze's 69 hashed references translate to published namespace files and verify. Ten historical `original_downloads_manifest` references remain external and are explicitly listed as unverified; their exact published manifest copies are verified separately. Native FITS bytes, the original execution environment, network retrieval, rendering, detector inference and model export are not recreated. This is a portable source/model/cache/aggregate audit, not a claim that the entire original observation experiment can run offline from this snapshot.

`test_summary_portable.py` exercises the important summary rejection guards using published native/synthetic cache fixtures. Only in-memory copies of internal package/model paths are translated; the original externally hash-bound `test_summarize_results.py` remains unchanged and requires its historical external development fixture. CI should explicitly omit that historical file and run the replacement guards, without silently skipping test failures:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q ml/pvusatov/verification/final \
  --ignore=ml/pvusatov/verification/final/test_summarize_results.py
```

A separate relocated namespace copy passed **30 tests and 21 subtests** and the full portable audit from a different working directory. Its audit JSON was byte-identical to the original-checkout audit, demonstrating independence from the old checkout and original `/tmp` data locations. This copy test is relocation evidence; the coordinator's fresh Python 3.12 CI remains separate evidence. The recorded local replay used Python 3.14.4. The original evidence and all frozen source/model/data/provenance files remain unchanged.

Actual audit evidence is `snapshot-audit-results.json` alongside this document; source and snapshot hashes, verified counts and explicit external-reference limits are included in that JSON.
