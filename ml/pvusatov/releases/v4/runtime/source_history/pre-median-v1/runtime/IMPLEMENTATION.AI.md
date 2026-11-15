# Isolated V4 inference runtime

This directory is a new runtime package. The deployed V3/original source, artifacts and evidence remain unchanged. Runtime integration does not authorize promotion; the coordinator owns final evaluation, resource/integration gates and release selection.

The seven unchanged Python modules (`__init__`, `__main__`, `contracts`, `cli`, `detector`, `prepare`, `render`) are byte copies of the existing runtime. `features.py` is the exact streamed physical extractor SHA256 `8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282`; `model.py` is the exact inference-only loader SHA256 `cd7154e2bbba3595b656c4207e9a6afe890a35e1f12ffa4203ab0b7cf6a74598`. Only the new `pipeline.py` changes runtime behavior. The local fixtures symlink points to `../../../backend/inference/fixtures`; deployment must put those existing fixture bytes at `/app/inference/fixtures` beside the package.

The pipeline validates the bound ONNX artifact, metadata and installed feature contract before opening any image reader. It passes an explicit model directory, default `/app/inference/models`; the exact loader itself is unchanged. Preparation, Gaussian peak proposals, linear linking, shared-median classical comparison and flagged-BLOOM construction use the copied algorithms. Actual request thresholds/speeds/counts remain supported and explicit in result settings, while the verified artifact supplies detector sigma. The same leave-one-out residuals/track pool feed the fixed sigma0.8 physical extractor, actual quality masks and full 30 Float32 score graph. Expected positions, ephemerides and training labels never enter runtime extraction or scoring.

Residual candidates expose the artifact's truthful `score_kind`; forests and sigmoid utility models retain different semantics. The model manifest includes full/selected feature contracts and numerical policy. These are uncalibrated ranking scores. Existing residual SNR and physical feature quantities are proxies under correlated image/residual noise, not photometric flux, posterior probability or calibrated motion significance. BLOOM measurements receive null learned scores and retain flagged-evidence semantics. The existing first three residual/protected-BLOOM publication policy, caps, warnings and rendered evidence remain in place.

The pipeline retains only the significance array from each `filtered_evidence` call. Smoothed/support arrays are discarded between epochs, saving three persistent Float64 image cubes at the largest supported shape relative to the old implementation. A weak-reference regression observed RED with the copied retention behavior and GREEN after this change; numerical significance/evidence values are unchanged. Full 1 CPU / 1 GiB deployment validation remains a separate coordinator gate.

## Verification before source handoff

`test_runtime.py` passes 15 tests. Coverage includes exact source/fixture copies; malformed/missing model before pixel readers; explicit default model directory; malformed field after model verification; 30-feature extraction; finite empty output; actual CLI safe failures; decoded PNGs; protected unscored BLOOM; exact cached Float32 30-feature rows, selected-model score order and scores on all four real presets; D2 rank 1 / D6 ≤4; and a selected-model subprocess from an unrelated working directory that forbids fitting-package imports.

Selected development artifact SHA256 is `c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35`; administrative metadata SHA256 at verification is `472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13`. It is coordinator-selected for future evaluation, not promoted by this integration test.

`verify_development.py` ran the selected artifact plus four real trained research specimens (ExtraTrees, HGB, RankNet, ListNet) on all four development presets. All 20 cases completed, 1,710 PNGs decoded, frame/difference/BLOOM PNG bytes agreed across model families on the same input/proposal settings, and known Vesta evidence stayed unscored. `verification/development-integration.json` SHA256 `17f814c5c1e8a73cccd74503ecbc749fbbc5dc8197ea43b110acebae7f20a998` records every model/metadata/source/fixture/resource hash, family, score semantics, settings, ranks and timings. This local proof is distinct from final scientific and constrained deployment gates.

Pipeline source-stable SHA256: `2b078aede763339b6362e94fa3329deac80687d521ff6579cae608c5a8304ed9`.

Commands from repository root:

```sh
PYTHONPATH=.:ml/pvusatov/backend/inference OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  /home/usatovpavel/edu/UtilsAI/.venv/bin/python -m pytest -q ml/pvusatov/releases/v4/test_runtime.py
PYTHONPATH=ml/pvusatov/releases/v4/runtime OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  /home/usatovpavel/edu/UtilsAI/.venv/bin/python -m ml_inference \
  --request /absolute/request.json --output /absolute/output-directory
```
