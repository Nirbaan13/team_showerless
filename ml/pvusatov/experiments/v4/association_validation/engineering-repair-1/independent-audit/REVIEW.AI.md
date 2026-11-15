# Independent audit of the repaired fixed-policy synthetic research

The independent numeric audit passes. The repaired run contains all 1,000 reserved synthetic fields, no errors, 1,953 truths, and 271,293 measured hypotheses. Its synthetic accounting agrees exactly with the producer report. The combined research remains incomplete because all 1,620 native trials are missing from this report. These results authorize no production promotion, policy reselection, precision claim, or confirmed-motion claim.

The independently implemented [checker](check.py) imports no producer functions. It reads derived numeric JSON caches, hashes the frozen references, and never reads raw pixels, loads model weights for execution, generates simulations, extracts features, or recomputes learned scores. The audit binds frozen R2 `ae981b56f43c8a14cd6dee9ce61c48853ea7c90b63eca8ddcf586e0a3e3dbbdd`, C596 model `c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35`, and metadata `472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13`.

For every field, the checker verifies the full and compact artifact hashes; contiguous pool indices; at least three distinct matched epochs; integer link identities; peak-index bounds; finite cached ordering scores; and aligned feature rows. It independently reconstructs baseline-priority and C596-priority pair-exclusive pruning, preserving original pool order for priority ties. Both resulting pools are ranked by their cached C596 scores at review budgets one and three, preserving retained order for score ties.

Spatial labels are independently derived from candidate XY positions and each truth path at the candidate's actual epochs. A truth must lie within 1.5 pixels at every candidate epoch; overlapping matches use the smallest mean distance and truth index order for exact ties. The checker recomputes the maximum pairwise truth distance across these actual matched epochs. A span of at least three pixels is descriptive only and never removes truths from the primary denominator. It counts unique truth identities separately for recovered, resolved, and unresolved outcomes, including duplicate candidates for the same identity correctly.

The compact evidence contains exactly the union of both retained pools plus every spatially matched full-pool row. Its full feature-matrix digest, coverage counts, and full-pool recovered/resolved counts match the full caches. All producer strata and whole-field summaries match the independent recount. All 200 zero-truth fields remain in workload accounting; the macro recall denominator contains the 800 truth-positive fields. The 152 zero-hypothesis fields are retained. Both synthetic cohorts coincide because synthetic attribution eligibility is true for every field.

| Independently reproduced outcome | Baseline order | Fixed learned order |
| --- | ---: | ---: |
| Retained candidate rows | 54,372 | 52,924 |
| Unique truths recovered at K=1 | 383 | 450 |
| Unique truths recovered at K=3 | 592 | 731 |
| Unique truths recovered over retained pool | 657 | 812 |
| Resolved truths at K=1 | 319 | 367 |
| Resolved truths at K=3 | 480 | 582 |
| Macro recall at K=1 | 22.3646% | 26.8021% |
| Macro recall at K=3 | 31.0000% | 38.3438% |

The paired macro difference is +4.4375 percentage points at K=1, with 95% interval [3.09375, 5.86484], and +7.34375 points at K=3, with interval [5.78125, 8.96875]. These intervals exactly reproduce 10,000 paired resamples of whole truth-positive fields using NumPy generator seed `2026111502`. Both budgets share the same field resampling indices. They characterize this fixed synthetic evaluation after DEV-informed selection; they do not establish performance on native data.

No cap or error field was discarded. There are zero peak-cap fields. The largest observed workloads are 57,649 link checks against the 2,000,000 limit, 6,043 hypotheses against 50,000, and 24,215 pair operations against 10,000,000. These caps are checked on every complete field. Reconstructing link-search checks themselves would require rerunning peak/link generation; this audit verifies the recorded count and cap rather than rerunning that scientific pipeline. The same distinction applies to cached scores and the producer's legacy parity flags: their bindings and downstream accounting are checked, without independent model inference.

The repair comparison preserves the evidence limit explicitly. The original attempt had 848 `int64` JSON serialization errors and 152 successful zero-hypothesis fields. All 1,000 `case_id`, `seed`, and `kind` identities agree exactly across attempts. The original errors did not retain mode, cadence, or simulation metadata, so cross-attempt equality of those absent values cannot be demonstrated. All full and compact scientific projections for the 152 successes agree exactly, including latent hashes, truth paths, times, metadata, hypotheses, scores, counts, and policy decisions. Only timings, worker RSS, full-pool path/hash references, and any freeze-anchor key are excluded. No full-pool output exists for the 848 original errors; scientific-output equality for those fields is unavailable.

The checker verifies all 18 preserved source snapshots, five preserved artifacts, and 1,152 opaque original output hashes. Across the two frozen source graphs, only the runner changes. Its complete text differs exactly by replacing `links=[list(link)for link in links]` with `links=[[int(epoch),int(index)]for epoch,index in links]`. Every other frozen source and non-source freeze field agrees, including policies, model references, protocol, seeds, and caps. The original incomplete aggregate was opened before repair, so this is not a fully blinded repair. Source-level invariance and equality of 152 successful empty pools cannot prove equality of unavailable nonempty original outputs.

Machine-readable results, per-field full/compact hashes, all 152 scientific projection hashes, and input digests are in [audit.json](audit.json). [SHA256SUMS](SHA256SUMS) binds the current review, checkers, audit outputs, and archive member manifest. The original four audit artifacts are preserved byte-for-byte under [source_history/v1](source_history/v1/SHA256SUMS). The producer's portable compact file is digest-bound and is verified to contain exactly the 1,000 audited compact fields. Repeating the full audit requires the immutable numeric full and compact caches at their manifest paths or explicitly rebased locations; the compact file alone omits suppressed unmatched hypotheses and cannot reconstruct full-pool pruning.

The checker now accepts `--repo-root` and `--cache-root`. These options replace only the original repository and `/tmp/spaceapps-association-validation` prefixes when opening files. Every reference's original provenance path and expected digest remain unchanged. No hash, preservation, or scientific-accounting check is skipped. Repository rebasing applies to frozen source/model/protocol and associated reference files; cache rebasing applies to full, compact, run-manifest, and producer report evidence.

A fresh-copy portability proof passes independently of the original repository and cache inputs. [prove_portable.py](prove_portable.py) copies only the hash-bound frozen reference files, preserved first-attempt snapshots, and checker into a fresh repository tree; it extracts the numeric cache archive into a separate fresh tree. Its child initializes NumPy, installs a Python audit hook for `open`, `os.listdir`, and `os.scandir`, explicitly rejects attempted reads of the original repository protocol, original cache run manifest, and `/etc/passwd`, then successfully audits all 1,000 fields and 271,293 hypotheses using the fresh trees. Runtime library paths remain permitted for Python/NumPy lazy imports. This Python I/O guard is instrumentation, not an operating-system sandbox, and does not claim to constrain native-code system calls. Preparation necessarily reads the original authorized inputs to construct the fresh copy; the child recount denies those inputs.

The exact numeric-cache tar is `/tmp/association-audit-portability-input.tar`, SHA-256 `928f1f8824fa8575c11087d74aa3b3901b9f5f5a1bb1d1172f89f0f873b8131c`, 107,970,560 bytes. It contains all `synthetic/`, `synthetic-repair-1/`, and `report-repair-1/` numeric evidence, including the 1,152 first-attempt opaque outputs, both attempts' run manifests, all repaired full/compact caches, and the producer portable report. [archive-member-manifest.json](archive-member-manifest.json) records all 3,156 file members, byte sizes, and digests. Existing gzip members are retained as exact bytes inside the uncompressed tar. [portable-proof.json](portable-proof.json) binds the archive, preparation code, copied references, child command and successful exit, rejected reads, and [portable-recount.json](portable-recount.json). The fresh recount reproduces the same scientific summaries and scientific projection hashes as the direct audit. Model predictions and hypothesis generation are not rerun.

Reproduction from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /home/usatovpavel/edu/UtilsAI/.venv/bin/python \
  ml/pvusatov/experiments/v4/association_validation/engineering-repair-1/independent-audit/check.py \
  --repair ml/pvusatov/experiments/v4/association_validation/engineering-repair-1 \
  --run /tmp/spaceapps-association-validation/synthetic-repair-1/run-manifest.json \
  --report /tmp/spaceapps-association-validation/report-repair-1/research-report.json \
  --output /tmp/independent-association-audit.json
```

The checker needs only NumPy and the Python standard library, enforces a four-GiB address-space limit and 900 CPU-second limit, and uses one math thread. It performs no acquisition, scoring, fitting, simulation, or production mutation.

For a relocated copy, append `--repo-root /path/to/repository --cache-root /path/to/extracted/cache` and give the corresponding relocated `--repair`, `--run`, and `--report` arguments. To repeat the guarded fresh-copy proof:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /home/usatovpavel/edu/UtilsAI/.venv/bin/python \
  ml/pvusatov/experiments/v4/association_validation/engineering-repair-1/independent-audit/prove_portable.py \
  --repo-root /path/to/repository \
  --cache-archive /path/to/association-audit-portability-input.tar \
  --output-dir /tmp/repeated-portability-proof
```
