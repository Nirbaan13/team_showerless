# SPHEREx motion inference workspace

This namespace contains Pavel's inference implementation, frozen models, fixtures, scientific evaluation, experiments and dedicated backend/frontend integration sources. Previous repository-relative subdirectories are preserved: `backend/inference`, `backend/src`, `backend/docs` and `frontend/src`. Other team members' ML code remains in its existing location.

The backend image packages the final-tested experimental `spherex-track-extra-v3` from `releases/v3/model`, SHA-256 `c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204`. Its sigma-0.8 detector profile, ExtraTrees family and algorithm version are bound into the graph. The baseline model in `backend/inference/models` remains v2 for historical offline evaluation; its complete original source/model release is archived in `releases/v2`. `relocation-manifest.json` records original paths and byte hashes. Shared application/build files contain only the required integration glue for this namespace.

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

Verify the selected release explicitly from the repository root:

```bash
python ml/pvusatov/releases/v3/smoke.py
python ml/pvusatov/verification/final/audit_snapshot.py
```

The first command runs the actual selected model against archived real exposures and decodes its PNG resources. The second checks the published source/model/cache hashes and recomputes FINAL aggregates without original `/tmp` paths or FITS. Original hash-bound summary tests retain historical external DEVELOPMENT prerequisites; portable equivalents run in CI.

FINAL primary recovery (unchanged single selected model): native 10 parent fields / 2,700 correlated injections, top3 367 → 437; synthetic 2,000 independent fields / 3,998 truths, top3 674 → 831. Native top1 uncertainty includes zero, and the narrower detector increases candidate/CPU burden. These are injection recovery results, not real precision. See [FINAL scientific results](verification/final/FINAL-SCIENTIFIC-RESULTS.AI.md), [independent review](verification/final/FINAL-INDEPENDENT-AGGREGATE-REVIEW.AI.md), and [release card](releases/v3/README.AI.md).

The installed container layout remains `/app/inference`; HTTP and gRPC interfaces retain their existing names. The server is built and deployed by the existing revision-based CI. Local research caches/native files remain outside git, with acquisition provenance and reproducible scripts under `backend/inference/experiments/`.

Current coordination and the prospective closed-final protocol are in [ML-V3-COORDINATION.AI.md](docs/ai/ML-V3-COORDINATION.AI.md). Training/validation/final parent fields remain separated; FINAL has completed with frozen outputs and no subsequent refit or reselection. A spatial injection match is not a confirmed moving object, and ranking scores are not planet probabilities.
