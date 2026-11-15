# Versioned V4 inference runtime

This is an isolated runtime package. V3/original source and model artifacts remain unchanged. The coordinator owns final scientific evaluation, constrained deployment gates and promotion; runtime proofs do not authorize release.

Six modules remain exact copies of the prior runtime: `__init__`, `__main__`, `contracts`, `cli`, `detector`, `render`. The streamed extractor is the exact `features.py` source SHA256 `8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282`; the inference-only `model.py` is exact source `cd7154e2bbba3595b656c4207e9a6afe890a35e1f12ffa4203ab0b7cf6a74598`. Changes to the new runtime comprise the V4 pipeline, the numerical-equivalence median helper, and the coordinator-owned partial-coverage preparation amendment.

The local fixtures symlink targets `../../../backend/inference/fixtures`. Deployment must copy those existing fixture bytes to `/app/inference/fixtures` beside the package. The model directory is passed explicitly, default `/app/inference/models`; the exact model loader is unchanged.

## Behavior and score semantics

The pipeline validates artifact bytes, external/embedded metadata, actual graph topology and installed feature source before any image reader. The verified artifact supplies detector sigma. Actual request thresholds/speeds/counts remain supported and explicit in result settings. Ordinary measured Gaussian peaks and linear tracks form the proposal pool; no joint-template fitted hypotheses are converted into measured peaks or six-feature rows.

The same leave-one-out residuals and measured track pool feed the fixed sigma0.8 physical extractor with actual outlier/BLOOM masks. The graph scores full 30 Float32 input rows and internally selects its declared feature subset. Target coordinates, ephemerides and labels never enter extraction or scoring. Candidates expose the actual artifact `score_kind`; forests and sigmoid utility models retain different semantics. These are uncalibrated ranking scores. Residual/physical SNR, covariance and chi-square quantities remain proxies under correlated image noise.

BLOOM evidence retains null learned scores, flagged-evidence semantics and the existing first-three-residual/protected-BLOOM publication policy. The shared-median classical comparison, caps and rendered evidence remain unchanged. Only significance maps are retained between epochs; unused smoothed/support maps are discarded, with a RED→GREEN memory-retention regression.

The median helper sorts finite Float64 values once per pixel and derives each removed epoch's central order statistics. Non-Float64 input and exceptional columns (zeros, subnormals, extreme magnitudes) retain exact legacy arithmetic. Exceptional work runs before allocating sort buffers; an all-exceptional stack returns directly through the reference implementation. The function body is exactly the separately tested prototype; the runtime wrapper uses relative imports and omits its research benchmark CLI.

The preparation amendment retains an unusable acquired epoch as a correctly shaped all-NaN image with its original identity/time, warns, and requires the requested minimum number of useful observations overall. Covered-input arrays, metadata and scores remain bitwise unchanged. The old prepare source `e464287b…` is preserved under `source_history/pre-coverage-v1`; this amendment was made without final score/outcome inspection.

## Current source inventory

| File | SHA256 |
|---|---|
| pipeline.py | `1d4a7793f89f190cb580c2b9da7defdf2c6ecc864842d3173ceb9c099dda19b0` |
| median_reference.py | `353f4d0a7b6032d18158df99cf90fa992d3cb0bfc714c96e50c05e75c4b18a2e` |
| prepare.py | `27ef087aa19f394eaf16ee19c0801ed6c7557a79a7ea77b3410445363f4624ec` |

The selected graph is `c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35`; administrative metadata at verification is `472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13`. No fitting, model reselection or detector/ranking-policy change accompanies the median scheduling improvement. Frozen final evaluation snapshots use their declared original implementation and remain immutable.

## Verification

Combined verification passed 139 tests:112 median parity/resource-scheduling tests, 22 runtime tests and 5 preparation-coverage tests. Runtime tests include model rejection before pixel access; explicit default directory; malformed graph/field; finite empty results; selected-model CLI from an unrelated working directory with fitting imports forbidden; source/fixture preservation; exact cached full 30 rows/order/scores; D2 rank1 / D6≤4; protected unscored Vesta; and direct before/after Float64 feature-bit, candidate-ID, full-result and PNG-byte parity on all four presets.

`verification/development-integration-bundle3.json` SHA256 `6a25738e14dabb968fc31502be0c657c3a012b1e57cbf56542706fa0b4cb5048` records selected C596 plus four real trained family specimens on 20 preset cases, 1,710 decoded PNGs, actual model/metadata/source/fixture/resource hashes and timings. All case records except wall time and every PNG byte agree with the original pre-median runtime. `verification/bundle3-byte-parity.json` binds this comparison, source inventories and tests (SHA256 `46cc48e83e18929396dbc4b209b0d8886ca6bcbdf132477b77bba2f8bb1e6cb8`).

Standalone 32×512×512 ordinary residual output hashes match exactly:22.05 s/609.12 MiB legacy versus 0.666 s / 300.09 MiB sorted;12% mask case34.65 s / 569.38 MiB versus 1.260 s / 299.59 MiB. These are stage measurements, not whole-pipeline speedups. An initial fallback regression retained sort buffers around the reference calculation (827.68 MiB); the corrected all-zero case is 607.71 MiB versus 607.82 MiB legacy, while a half-zero case is 429.70 MiB versus 607.84 MiB, with exact output-byte hashes. Proofs are under `experiments/v4/detection/results/median-reference-maximum-v2.json` and `median-exception-resource-v2.json`.

The actual selected-model nonempty 32×512×512 CLI completed with one measured 32-epoch track and 66 resources at 638.01 MiB peak child RSS. Local wall times vary with background workload: the fresh old/new runs were 38.39/38.90 s. A further sequential helper+worker CPU pair observed 94.97→43.31 CPU seconds (worker wall 93.03→38.25 s); identical fixture-generation CPU is included on both sides. These observed local measurements do not claim a universal latency ratio or a hard cgroup memory guarantee. The coordinator owns the new 1 CPU / 1 GiB VPS gate.

Earlier sources/proofs remain under `source_history/pre-median-v1`, `pre-coverage-v1`, `pre-exception-scheduling-v1` and `maximum-probe-v1`; previous published proof bytes are preserved.

```sh
PYTHONPATH=.:ml/pvusatov/backend/inference OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  /home/usatovpavel/edu/UtilsAI/.venv/bin/python -m pytest -q \
  ml/pvusatov/releases/v4/test_runtime.py ml/pvusatov/releases/v4/test_coverage.py
PYTHONPATH=ml/pvusatov/releases/v4/runtime OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  /home/usatovpavel/edu/UtilsAI/.venv/bin/python -m ml_inference \
  --request /absolute/request.json --output /absolute/output-directory
```
