# ML service image source scope

The service image previously copied the entire `ml/` tree. Its Dockerfile-specific
ignore file also excepted parent directories such as `!ml/`, which can re-include
their descendants through Docker's parent matching. The image now copies exactly
20 runtime files, and the ignore file excepts only those files. Research and
training directories, published numeric evidence, caches, and tests remain in the repository.

The runtime includes `service.py`, its local detector and catalogue modules, the
existing deployment smoke script, requirements, and the benchmark JSON/NPZ/PNG.
The five `science.motion` modules remain because live search imports their
detector, preparation, review and ranker functions. All four existing motion case
NPZs, both case CSVs, and deployment compose are preserved. This change does not
alter application code, dependencies, workflow files, scientific math, or the
deployment protocol.

Tracked input sizes measured with Git object metadata at deployed baseline
`195996740890f0e94d1d54522fe9bb6a01c7dae0`:

| Source scope | Before (bytes) | After (bytes) |
| --- | ---: | ---: |
| `ml/` copied sources | 348,919,928 | 732,881 |
| All copied sources, including motion and compose | 350,460,022 | 2,264,572 |

These are tracked source byte counts. They do not measure Docker build context
transfer, installed dependencies, compressed image layers, or deployment time.
No Docker build or VPS change was performed locally. Docker CI and the deployment
of the merged revision remain the integration checks.

Verification used `/home/usatovpavel/edu/UtilsAI/.venv/bin/python` (Python 3.14.4):

```bash
/home/usatovpavel/edu/UtilsAI/.venv/bin/python -m unittest discover -v -s ml/pvusatov/tools/ml_image_scope -p test_scope.py
/home/usatovpavel/edu/UtilsAI/.venv/bin/python ml/pvusatov/tools/ml_image_scope/scope.py --baseline 1959967
```

All five tests pass. They reject directory/glob/research COPY sources, missing
local imports and required runtime assets, and broad/parent ignore exceptions.
The functional test stages exactly the Dockerfile's COPY files under a temporary
`/app` equivalent, isolates `PYTHONPATH`, and runs the unchanged
`smoke_deployment.py --check-runtime`. This reads the existing packaged runtime
assets and starts a real local HTTP server using disposable SQLite databases.
It passed with four catalogue rows and one recovered synthetic track. No new
holdout or FINAL data is accessed by these checks. This is a runtime source
closure check, not a substitute for the Python 3.11 container build.

`scope.py` intentionally supports only this Dockerfile's simple explicit COPY
syntax and exact ignore exceptions; it is not a general Dockerfile interpreter.
Use `--stage /new/path` to reproduce the isolated file layout before running its
smoke script.

Docker's [COPY reference](https://docs.docker.com/reference/dockerfile/#copy),
[ignore-file documentation](https://docs.docker.com/build/concepts/context/#dockerignore-files),
and [official pattern matcher](https://github.com/moby/patternmatcher/blob/main/patternmatcher.go)
describe file copying, exception ordering, and parent-path matching.
