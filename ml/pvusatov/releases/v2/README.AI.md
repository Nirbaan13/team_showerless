# Immutable v2 release snapshot

This is a self-contained copy of all78 original runtime, source, fixtures, model and audit files, created before adding optional v3 runtime-profile support. `snapshot-manifest.json` records every original byte hash. Original freezes, scientific reports, requirements and ONNX metadata are preserved without rewriting their historical paths.

The nested `backend/inference` hierarchy makes the original source references resolve within this snapshot. Run its unchanged tests from the repository root:

```bash
cd ml/pvusatov/releases/v2/backend/inference
python -m pytest
python smoke.py
```

The model remains `spherex-track-rf-v2`, SHA-256 `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9`. This archive is historical and is excluded from the normal runtime image. Active source may evolve separately; never edit this snapshot to make current-source checks pass.
