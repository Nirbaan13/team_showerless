# Native numeric-cache portability proof

This separate wrapper preserves independent checker SHA-256
`5b6105c10bfbdca1ea5e6ba4218d8cc357e3c9d10be2fc52cb527c20bd9bb8ca`.
Use it only after root supplies the closed native run, completed report and sealed
numeric archive. The real native archive has not been audited by this helper
during implementation.

The input archive must preserve these paths:

```text
native-release-1/full/*.json.gz
native-release-1/compact/*.json.gz
native-release-1/run-manifest.json
report-native-release-1/research-report.json
report-native-release-1/portable-fields.jsonl.gz
```

The preparer rejects absolute/traversal paths, links, special files, duplicate
members, unplanned paths and non-numeric files before writing any member payload.
Extraction is bounded to 3,267 files and 8 GiB of declared member bytes. Gzip
numeric records remain opaque during extraction. No raw FITS belongs in this
archive.

```sh
PYTHONDONTWRITEBYTECODE=1 /home/usatovpavel/edu/UtilsAI/.venv/bin/python \
  ml/pvusatov/experiments/v4/association_validation/native-release-1/portable-proof/prove_portable.py \
  --repo-root /path/to/repository \
  --cache-archive /path/to/sealed-native-cache.tar \
  --output-dir /tmp/new-native-portability-proof
```

The output directory must be new or empty. Preparation creates a fresh temporary
repository/cache copy, verifies and copies the frozen 18-source closure, model
and metadata, protocol, selection, calibration, native plan, seed amendment,
R2 freeze, released handoff and exact checker. References retain their historical
absolute paths and original bytes; the child uses the checker's root rebasing.
Model/calibration files are copied and hashed as opaque closure dependencies.

The separate child initializes NumPy, verifies and compiles the exact checker,
then explicitly calls `install_io_guard(args)` before `checker.main()` reads any
audit inputs. It verifies all three built-in denied-read probes and rejects any
additional forbidden read. The guard is a Python open/list audit hook, **not an
OS sandbox**. It permits the relocated repository/cache, proof output and Python
library paths. No producer functions, models, scoring or raw FITS readers run.
The child timeout is fixed at 900 seconds.

Outputs are `archive-member-manifest.json`, `native-recount.json`,
`guarded-child.json` and `portable-proof.json`. They bind archive/member hashes,
copied reference hashes, exact checker/wrapper source hashes, audit digest,
child exit status and all three denied probes. The temporary copy is retained
for inspection. `PASS` is a portability/numeric-recount result; the independent
native audit retains its own `PASS` or `INCOMPLETE` status. This proof does not
authorize inference, promotion or deployment.

Analytic-only tests (no native cache reads):

```sh
PYTHONDONTWRITEBYTECODE=1 /home/usatovpavel/edu/UtilsAI/.venv/bin/python -m unittest discover \
  -s ml/pvusatov/experiments/v4/association_validation/native-release-1/portable-proof \
  -p 'test_*.py' -v
```

The guard test runs the unchanged checker in a child with `/etc/passwd` as its
deliberately forbidden first input. It must fail with `PermissionError` after
the three built-in probes, before reading any freeze, run or report data.
