# Unpromoted V4 feature-performance candidate

This directory is an isolated performance candidate. It is not selected for production and has no Docker, CI, API, deployment, fitting, detector, association-policy, or threshold changes. The existing V3/V4 runtime, model, FINAL results and association-validation records are unchanged.

`runtime/ml_inference/features.py` is the byte-exact original extractor, SHA256 `8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282`. It remains the training/reference source in the model metadata. The ONNX graph and its metadata are copied byte-for-byte, retaining SHA256 `c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35` and `472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13`, respectively.

The actual feature producer is `runtime/ml_inference/fast_features.py`, SHA256 `5ac4716292ba19af8b7ef124aac9c4386d8b501e055d46c898bae70f9a9e2ca6`. It ports the fixed experimental prototype SHA256 `47e3486cc94e65f520244575fc5dee8517ac5aa2e4f84c3f8a70c477df90102d`. Arithmetic is unchanged from that prototype; the differences are the package-relative reference import and descriptive text. It reuses reference map sampling and groups seven residual-photometry reductions by valid epoch count, in blocks of at most 4096 rows. The candidate imports its own relative modules and does not require the repository or research packages at runtime.

`feature_binding.py` compares `producer-manifest.json` with a baked descriptor and hashes both the actual adapter and reference extractor before `prepare()` can read pixels. The unchanged original ranker loader then verifies the original source/contract, metadata and ONNX graph before preparation. The actual adapter is imported lazily after this guard, so a modified adapter is not executed before the check. This is a local immutable-source check, not a cryptographic signature or protection against arbitrary changes to the verifier itself.

Results add exactly one scientific-output provenance entry, `provenance.feature_producer`. It identifies the actual adapter SHA, the reference SHA, feature-contract SHA and implementation lineage, and explicitly states that the model metadata source describes the training/reference implementation. It does not mislabel the original extractor hash as the executing adapter. The unchanged model metadata is preserved in the result's `model` object.

All runtime dependency inputs, the hashed dependency lock, model and preset fixtures are independent copies of the existing V4 release. No dependencies were added. The shared UtilsAI interpreter is used for local verification. Large generated NPZ/PNG/result artifacts are kept outside Git under `/tmp/spaceapps-v4-optimized-cli-20261115`.

Run the candidate tests from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /home/usatovpavel/edu/UtilsAI/.venv/bin/python -m pytest -q \
  ml/pvusatov/releases/v4_optimized_candidate/test_candidate.py
```

The candidate retains the usual `python -m ml_inference --request ... --output ...` entry point when `PYTHONPATH` points to this directory's `runtime`. Supply this directory's `model` explicitly in the request. It has not been wired into any service.

The fixed paired full-CLI benchmark is reproducible with:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /home/usatovpavel/edu/UtilsAI/.venv/bin/python \
  ml/pvusatov/releases/v4_optimized_candidate/benchmark_cli.py \
  --scratch /tmp/spaceapps-v4-optimized-cli-fresh
```

Use a new nonexistent scratch directory. It runs three alternating paired repetitions per case on one pinned CPU with one math thread. Cases are the four existing real presets, the exact existing density-stress8 fixture at 32×512×512, and a small empty engineering negative case. All scientific JSON except the new producer descriptor, candidate scores/IDs/order, resource metadata and every PNG byte are compared in each pair. The density fixture hash must remain the already published `69cb2197506e614edad69cfa72404d1d18a95667eddbbea086dfc12b0c5dbda7`. No new native holdout, FINAL field, training or evaluation cohort is read. Every child has a 300-second timeout and sampled 2 GiB RSS stop; wait4 maximum RSS is recorded. These are local observations rather than a hard cgroup guarantee.

The earlier roughly 1.54× native DEV feature-stage result does not establish a whole-CLI gain. Candidate promotion requires a separate decision; this experiment makes no promotion or sensitivity claim.

Final verification: the candidate and existing V4 runtime/coverage suites pass together, 50 tests in 13.58 seconds. See `Findings.AI.md`, `benchmark-cli-evidence.json` and `verification.json` for exact timings, negative cases, source hashes and test scope.
