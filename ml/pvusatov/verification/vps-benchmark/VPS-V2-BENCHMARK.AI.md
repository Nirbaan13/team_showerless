# Bounded VPS benchmark of immutable v2

Measured on **2026-11-14 at 21:13 UTC** on the authorized VPS. Exactly three sequential fresh containers used the image already running as the backend. No production container was entered, restarted or changed; no production data was attached, no ports were published, and no candidate model or final observation was uploaded or opened.

The pinned image was `sha256:23f2802cc22e0eb8f60f7c8ef6465cb0ac1a45918c577fd74803b433b37fc608`, with revision `f2b786457760fe5321de6346232523dda8b906d5`. Every probe verified model `spherex-track-rf-v2`, SHA-256 `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9`, and its packaged real-preset fixture hash before execution.

| Packaged real preset | Frames / grid | Computed candidates | Python child wall time | Python child CPU, user + system | Python child peak RSS |
|---|---|---:|---:|---:|---:|
| comet-d6 | 4 / 256×144 | 10 | 1.334 s | 1.325 s | 171.40 MiB |
| comet-d2 | 3 / 104×76 | 2 | 1.124 s | 1.124 s | 169.88 MiB |
| vesta-d3 | 3 / 222×174 | 26 | 1.385 s | 1.384 s | 171.39 MiB |

All three returned successful finite JSON with the correct model hash, computed ranked tracks and existing output resources. Their selected known-object fixtures are development/recovery cases, not representative independent survey fields. No expected coordinates entered detection or ranking.

## Measurement and enforced bounds

The measurements above come from the sole inference Python subprocess **inside each container**, using `time.perf_counter()` around its complete CLI execution and Linux `resource.getrusage(RUSAGE_CHILDREN)`. They include Python startup, imports, preparation, detection, ranking, rendering and result publication. Peak RSS is the child's `ru_maxrss` in KiB converted to MiB; it is not SSH-client or Docker-CLI memory. CPU values include child user and system time. Docker-command wall times, recorded separately, were 1.899, 1.572 and 2.021 seconds.

Each probe used `--rm --network none --read-only --cpus=1 --memory=1g --pids-limit=128` and a dedicated `/tmp` tmpfs of 268,435,456 bytes. Inside-container cgroup checks verified `cpu.max=100000 100000`, `memory.max=1073741824`, and `pids.max=128`; mount information confirmed the 256 MiB tmpfs. No host-data bind mounts were requested. Python/ONNX math thread limits came from the immutable image environment.

Python was **3.12.3**; NumPy 2.5.3, SciPy 1.18.1, Astropy 8.0.2, ONNX Runtime 1.30.0 and Pillow 12.3.0. The evidence also retains cgroup peak charged memory, page faults, context switches and block I/O. Cgroup charged memory and per-process RSS have different shared-page accounting and should not be conflated.

Every ephemeral container exited normally and was removed by `--rm`; the final run-label check found **zero leftover containers**, and no forced cleanup was needed. The production container ID, pinned image and healthy state matched before and after all probes. This check does not claim an exclusive or otherwise idle host.

## Reproduction and artifacts

From the repository root, using the authorized external SSH key and strict known-hosts file:

```bash
/home/usatovpavel/edu/UtilsAI/.venv/bin/python \
  ml/pvusatov/verification/vps-benchmark/run_ssh.py \
  --output /tmp/v2-vps-benchmark.json
```

The driver launches three new sequential ephemeral probes. `--key` and `--known-hosts` can point to the corresponding authorized external files; no credential contents are stored here. It pins the image running at the start and validates its exact revision tag. A future deployment may have a different image ID, so preserve this evidence when comparing another frozen environment.

`container_probe.py` contains the minimal in-container measurement. `remote_runner.py` performs read-only image/container inspection and bounded `docker run`; it never uses `docker exec`. `v2-vps-benchmark.json` is the full machine-readable evidence, including exact source hashes and environment limits. `benchmark-manifest.json` inventories the published probe, evidence and report bytes.

These are three small preset executions under one-CPU/one-GiB limits. Host page caches were uncontrolled, and the probes do not establish cold-cache latency, statistical tail latency, concurrency capacity, worst-case 32-frame/512×512 cost, or v3 performance. No model fitting or production-service request was performed.
