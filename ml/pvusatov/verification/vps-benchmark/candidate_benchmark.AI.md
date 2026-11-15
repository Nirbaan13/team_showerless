# Frozen c13 candidate: bounded VPS numeric/resource probe

One ephemeral probe completed at **2026-11-14T22:16:04.519437+00:00** on the explicitly authorized VPS. It uploaded only the frozen candidate ONNX, metadata JSON and exported parity-reference JSON. No native FITS, final data, object labels or expected target coordinates were uploaded or opened. No model fitting, production `docker exec`, service restart or production model overwrite occurred.

The probe pinned the exact running backend image **`sha256:6df625fa2845fdd7004c98d7149489776585680859237aa409aca193a670331a`**, revision **`5d9f117e19a7a010503db655259466cf36c22dfa`**. Production container `5d4d2b477b6429edd357801b956ff36c5c006ce125e6198f6a31f79484d4e041` remained the same, with identical image/revision and **healthy** state before and after the probe. These are two observations; they do not assert an exclusive or idle host. This probe did not control unrelated CI deployments.

| Check | Measured result |
| --- | --- |
| Frozen model | `c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204` |
| Metadata | `983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04` |
| Parity reference | `53bb2b7aefc79d7b5a17613a25eb0a365a221fc34008d0d87decf6792ee3b89f` |
| Numeric parity | All **3,584 six-feature rows pass**, rtol=2e-6 and atol=2e-6 |
| Maximum absolute score error | 5.96342266568e-07 |
| Runtime loader/session creation | 132.57 ms |
| Warm batch | 1,000 rows, three warmups, **20 measured repetitions** |
| Median / p95 / maximum batch wall time | **14.12 / 19.27 / 20.97 ms** |
| Numeric-process peak RSS | **136.17 MiB**, current Linux process VmHWM |
| Whole probe peak RSS | 174.82 MiB, including the subsequent loader-capability check |

The main numeric/latency measurements cover scoring already computed features. They do not include FITS preparation, source detection, linking, rendering, Python startup, SSH transfer or Docker startup. The reported remote `docker_wall_seconds` field begins after staging-directory creation and also includes decoding/writing the three allowed staged files; it is not a pure inference latency. Host page caches and background load were uncontrolled. Twenty repetitions do not establish statistical tail latency, concurrency capacity or worst-case workload cost.

Inside-container cgroup/mount checks verified **one CPU**, **1 GiB memory**, **128 PIDs**, a **256 MiB /tmp tmpfs**, **network none**, a read-only root filesystem and a read-only `/candidate` bind. The Docker container used `--rm`. Exactly one probe container ran; it exited successfully, required no forced cleanup, left **zero containers**, and its dedicated host staging directory was deleted. Numeric memory uses `/proc/self/status` VmHWM, not inherited `getrusage` high-water. Cgroup charged memory is recorded separately and has different shared-page accounting.

Python was **3.12.3**. Runtime packages were NumPy **2.5.3**, SciPy **1.18.1**, Astropy **8.0.2**, ONNX Runtime **1.30.0** and Pillow **12.3.0**. The image's `/app/inference/ml_inference/model.py` SHA-256 was **`3e9cabef0b68c60c154ee91cc51a54aeccbab3339b52a2b2aa21f06c7d8881c5`**.

**Scope: pure ONNX numeric/resource compatibility only.** The currently running image lacks the new artifact-bound detector-profile capability: it accepted a private `/tmp` metadata copy whose sigma1.2 profile conflicted with the graph's embedded sigma0.8 profile. The original candidate files remained read-only and unchanged. Consequently this evidence does **not** establish sigma0.8 preparation/detection behavior, new-pipeline end-to-end compatibility, packaged-object recovery or final scientific performance. Root owns the newer runtime rollout and final evaluation.

Reproduction from the namespaced directory, with authorized external SSH credentials and strict existing known-hosts verification:

```bash
/home/usatovpavel/edu/UtilsAI/.venv/bin/python \
  verification/vps-benchmark/candidate_run_ssh.py \
  --candidate-dir backend/inference/models/experiments/v3-selected-candidate-profile-bound \
  --output /tmp/candidate-vps-benchmark.json
```

`candidate_container_probe.py`, `candidate_remote_runner.py` and `candidate_run_ssh.py` are the exact new producer files. `candidate_vps_benchmark.json` retains full timings, limits, hashes, capability evidence and cleanup checks; `candidate_manifest.json` inventories this report and the evidence. Existing baseline benchmark files and every root-frozen scientific input remain untouched.
