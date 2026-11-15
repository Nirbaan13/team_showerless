# Portable scored audit capsule

This bundle preserves every planned FINAL field: 3,240 native injections over 12 parent backgrounds and 3,000 synthetic fields. It supports independent recovery, clustered uncertainty, geometry, coverage, and stratum accounting without raw FITS files, model artifacts, `/tmp` caches, or evaluation-source imports.

Run from any directory with Python and NumPy installed:

```bash
python /path/to/portable-audit/verify.py --deny-external-inputs --probe-denial
python -m pytest /path/to/portable-audit/test_verifier.py -q
```

The gzip JSON retains candidate IDs, original order, measured epochs/coordinates, truth paths and times, matches, both frozen score vectors, matched geometry, coverage, attribution flags, speed/brightness, controls, and provenance. All 6,240 fields remain; it is not a sample or a summary-only table. Large six-/30-column feature matrices are omitted and separately bound by canonical decoded-matrix SHA-256 hashes, together with original source-cache hashes and per-field projection hashes. Their values and model predictions are not recomputed or claimed verified here.

The exact canonical report, freeze, unblinding record, and scientific-equality proof are local files. Historical absolute paths inside them are provenance strings; the verifier never opens those referenced paths. Canonical report `15cabb84…`, freeze `1225e2de…`, candidate graph `c596f66f…`, and candidate metadata `472a3db4…` are explicitly bound. No graph or model metadata file needs to be downloaded.

The scored gzip payload `d2f27669…` is independently pinned in the verifier. Resealing the local manifest and per-field projection hashes cannot authorize changed scores, even when candidate ranks and all report metrics remain unchanged.

The verifier independently sorts scores stably, counts unique nonnegative truth identities within the original K1/K3 budgets, reconstructs spatial matching and truth spans, and reproduces native parent / synthetic field bootstrap intervals with 10,000 paired draws and seed 20261115. It preserves the report's original field-level finite-center cohort semantics and labels per-truth geometry as descriptive rather than a necessary detectability ceiling. UNKNOWN controls are workload, not survey precision negatives.

The external-input denial proof copies this directory to an unrelated temporary location and runs only that copy. After interpreter/NumPy initialization, a Python audit hook rejects file opens and directory enumeration outside the copied bundle; an intentional `/etc/passwd` attempt must be denied. This is a transparent Python I/O guard, not an operating-system sandbox claim. Portable success therefore does not depend on raw caches, models, original repository code, or final data paths. The proof records its exact manifest/verifier hashes.

The comparison remains frozen C13 versus frozen V4 scorers under shared coverage-preserving amended preparation. The amendment was coverage-informed while scientific outputs were blinded; exact synthetic equality preceded canonical unblinding. This bundle neither changes primary results nor authorizes promotion, fitting, reselection, or new model scoring. Runtime and integration evidence remain separate.
