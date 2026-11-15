# Independent association research

This evaluates the DEV-informed selection in root's immutable `selection-record.json`. It does not change the V4 release, scorer, threshold, runtime, gates or production status. Both policies receive one measured pre-deduplication pool and identical frozen C596 scores. Legacy pruning uses baseline priority; learned pruning uses utility priority. Both retained pools use stable C596 ordering for K1/K3 review. Actual matched-epoch truth spans at least three pixels are descriptive accounting, never a primary-denominator filter or motion confirmation.

Before any new holdout inference, root creates and records an external source freeze:

```sh
python experiments/v4/association_validation/freeze.py --output /absolute/research-freeze.json
python experiments/v4/association_validation/execute.py --freeze /absolute/research-freeze.json --anchor EXTERNAL_SHA --kind synthetic --output /tmp/spaceapps-association-validation/synthetic
```

Paths in these examples are relative to `ml/pvusatov`. Use the existing scientific Python environment. Source modules compile the exact checked bytes rather than timestamp-based caches. The model and feature contract verify before simulator or native readers are called. Four single-thread workers are pinned to at most four CPUs, each with a 1.75 GiB address-space limit, leaving manager headroom within the 8 GiB allowance. All output directories must be under `/tmp/spaceapps-association-validation`; one shared lock enforces an 8 GiB aggregate scratch cap across both domains and portable reports. Prediction timings include separately recorded legacy parity work and are not deployed-runtime benchmarks.

Native data need an additional explicit root release: `--kind native --handoff PATH --handoff-sha256 EXTERNAL_HANDOFF_SHA --authorize-native`. The handoff must contain all twelve predeclared parents, their corrected 4110001–4110012 seed mapping, eight exposures per parent, and ninety-six unique observations outside the 438 exclusions. The original cohort declaration and seed amendment are frozen before synthetic inference. Empty native acquisition remains an unperformed domain; it is never reported as no sky coverage or zero recovery. No native files or metadata selections are read by the synthetic workers.

Run `--kind report --synthetic-manifest PATH [--native-manifest PATH] --output NEW_REPORT_DIR` using the same freeze and anchor. If native acquisition is unavailable, omitting its manifest preserves all 1,620 missing planned injections explicitly and makes the combined report incomplete. Error records remain in the exact identity plan and disable formal primary summaries for that domain. Complete data use whole-parent/whole-field paired 10,000-draw bootstrap intervals, seed 2026111502, with truth-positive macro groups and empty-field workload retained.

Full hypothesis pools and their thirty-feature rows remain in the scratch run directories outside Git, each hash-bound. `portable-fields.jsonl.gz` contains every compact field, including failed fields, all candidates retained by either policy, and every offline spatially matched hypothesis from the full pool. Its first JSON line binds protocol/model/selection/freeze metadata; subsequent lines contain one field each. Historical full-pool paths are provenance strings. No raw image pixels are stored in these evidence files. The report independently recomputes compact spatial labels, matched spans and review-budget counts before publication.
