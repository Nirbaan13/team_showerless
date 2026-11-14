# SPHEREx motion inference workspace

This namespace contains Pavel's inference implementation, frozen models, fixtures, scientific evaluation, experiments and dedicated backend/frontend integration sources. Previous repository-relative subdirectories are preserved: `backend/inference`, `backend/src`, `backend/docs` and `frontend/src`. Other team members' ML code remains in its existing location.

The currently deployed model is `spherex-track-rf-v2`, SHA-256 `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9`. V3 is development work and has not replaced it. `relocation-manifest.json` records original paths and byte hashes; frozen model and scientific source manifests retain their original content.

From the repository root, run the Python package using the existing scientific environment:

```bash
cd ml/pvusatov/backend/inference
python -m pytest
python -m pytest experiments
python smoke.py
```

Runtime and offline-training dependencies remain separately hash-locked. The laptop's shared scientific interpreter is `/home/usatovpavel/edu/UtilsAI/.venv/bin/python`; the container uses its packaged Python3.12 environment.

Historical offline experiment commands use paths relative to this namespace, so start them here:

```bash
cd ml/pvusatov
PYTHONPATH=backend/inference python backend/inference/experiments/v3_ranker/cache_synthetic.py --help
```

The existing backend sbt build includes this namespace's dedicated Scala/protobuf sources and tests. The existing frontend build includes its dedicated page and API client. Their shared entry points reference these files; there is one maintained copy. Build the backend image from the repository root:

```bash
docker build --file backend/Dockerfile --build-arg APP_REVISION="$(git rev-parse HEAD)" --tag spaceapps-api:local .
```

The installed container layout remains `/app/inference`; HTTP and gRPC interfaces retain their existing names. The server is built and deployed by the existing revision-based CI. Local research caches/native files remain outside git, with acquisition provenance and reproducible scripts under `backend/inference/experiments/`.

Current coordination and the prospective closed-final protocol are in [ML-V3-COORDINATION.AI.md](docs/ai/ML-V3-COORDINATION.AI.md). Training/validation/final parent fields remain separated. A spatial injection match is not a confirmed moving object, and ranking scores are not planet probabilities.
