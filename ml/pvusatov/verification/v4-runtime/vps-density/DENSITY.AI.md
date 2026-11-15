# Fixed density resource verification

All three deterministic maximum-shape inputs were run locally and twice inside an isolated VPS container: 32 epochs, 512×512 pixels, default SNR4, 100 peaks/epoch and 100 published candidates. The selected graph, metadata and eleven runtime modules stayed fixed.

| Engineering sources | Result | VPS repeat child wall time | Child peak RSS |
|---:|---|---:|---:|
| 8 | Success, 100 published candidates; candidate-cap warning | 34.85s | 661.95MiB |
| 32 | Explicit linking `workload_limit` | 9.71s | 416.26MiB |
| 100 | Explicit linking `workload_limit` | 10.36s | 417.21MiB |

The complete container, including generator, worker, tmpfs and output/cache accounting, peaked at **679.64MiB** under actual cgroup limits of one CPU, one GiB and no swap. Final `max`, `oom`, `oom_kill` and `oom_group_kill` event counters were zero. The root filesystem and source mounts were read-only; output/tmpfs and an inherited anonymous app-data volume were writable. Production services were untouched.

The first attempt recorded startup cgroup files and child exits but omitted final whole-container peak/events. That attempt remains intact. The separate repeat adds final accounting after every child, with the same fixture bytes, original generator, model and runtime. The original local date-serialization error and its prospective transport-only correction also remain documented in [local evidence](../density-stress/DENSITY-STRESS.AI.md).

[audit.py](audit.py) rehashes inputs, binds host scripts and receipts, verifies all six outcomes, and reproduces exact complete-result equality and all 264 successful-case PNG hashes across local/VPS runs. It is offline and does not load a model or raw images. Independent source/data review confirmed those checks.

These sources are engineering fixtures, despite the trusted preset parser identifier. Published candidate count is neither recovered-source count nor precision. The source-count sweep is not an exhaustive density bound, and timing belongs to these measured one-CPU runs.
