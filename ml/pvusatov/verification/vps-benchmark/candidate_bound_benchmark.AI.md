# Frozen c13 candidate: profile-bound VPS CLI follow-up

One authorized follow-up probe completed at **2026-11-14T22:31:33.395914+00:00**, after root deployed revision **`5867ff8ac88087acb36cbfdb168b6d2299fef97a`**. The exact current backend image was pinned by immutable ID **`sha256:a7a09a3f08074570110dfe1dbb714d378047ea1bb3ca19f278ba2a08c4aa64c7`**. Production container/image/revision and **healthy** status were identical before and after this probe. The earlier old-image numeric evidence remains unchanged; the image changed between probes through root's independent CI rollout, not through either probe.

The same frozen model **`c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204`** and metadata **`983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04`** were mounted read-only at `/candidate`. Only these files and the frozen parity-reference JSON were uploaded. No final data/features/labels were uploaded, read or used, and no fitting or model reselection occurred.

**New profile binding passed.** A private metadata copy claiming sigma1.2 against the graph's embedded sigma0.8 was rejected with `embedded detector_profile does not match metadata`. The image's `model.py` SHA was **`f4b6a329c49a771fab6c51941697fd0fcd80a673e894b8c4afa6cec63e5a0083`**. Python was3.12.3; NumPy2.5.3, SciPy1.18.1, Astropy8.0.2, ONNX Runtime1.30.0 and Pillow12.3.0. All3,584 parity rows passed rtol=2e-6/atol=2e-6, maximum absolute error **5.96342266568e-07**.

Twenty warmed1,000-row score batches measured **11.59ms median**, **13.68ms p95**, and 17.41ms maximum. Numeric-process Linux VmHWM was **137.08MiB**. These score-only measurements exclude preparation/detection/rendering and do not establish cold-cache or concurrent capacity.

## Actual packaged-development CLI executions

Each fresh Python child invoked the unchanged `ml_inference.__main__` entry point via a `runpy` wrapper solely to capture that child's Linux VmHWM at exit. Standard `--request/--output` arguments and trusted request `model_dir=/candidate` were used; the production global model directory was untouched. Every result verified c13 artifact identity, **ExtraTreesClassifier**, full sigma0.8 profile, `motion-extra-v3-sigma08` algorithm version and the artifact-bound BLOOM output policy. Every published resource existed and decoded as a valid PNG. No scientific module or scoring function was monkeypatched.

| Packaged development case | Frames | Published candidates | Complete child CLI wall time | Actual child VmHWM | Verified PNG resources | Known-target result, offline only |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| comet-d2 | 3 | 1 | 1.152 s | 192.17 MiB | 8 | model #1 |
| comet-d6 | 4 | 36 | 1.408 s | 193.32 MiB | 80 | model #4 |
| vesta-d3 | 3 | 100 | 1.557 s | 193.10 MiB | 209 | BLOOM #100 |
| vesta-d6 | 3 | 18 | 1.322 s | 193.33 MiB | 45 | BLOOM #18 |

All four fixed CLI executions completed before expected positions were loaded. Offline labels were joined by physical observation ID only afterward, with a1.5-pixel match tolerance. These are four selected views of **two known objects**, not four independent survey fields. Other real tracks remain unknown, never negative labels. Both Vesta targets remain BLOOM-only with **null ML scores** and null residual SNR; VestaD3 is now published at slot100. The cometD6 target remains rank4, retaining the documented K3 tradeoff against the earlier v2 rank3 diagnostic; this is not hidden or used to select another model.

The four child runs totaled 5.440s and verified 342 PNG resources. Timings include child startup/imports, actual preparation, detection/linking, ranking, rendering and atomic result output. They exclude HTTP/gRPC/API queues/browser work. Page-cache state and other host load were uncontrolled. The separate remote `docker_wall_seconds` field also includes three-file staging decode/write, so it is not a pure inference metric.

## Isolation and cleanup

Exactly **one follow-up ephemeral container** ran with `--rm`, networknone, read-only root, read-only `/candidate`, one CPU,1GiB memory,128 PIDs and a256MiB `/tmp` tmpfs. Inside-container cgroups and mounts verified the limits. Whole-probe parent VmHWM after the four children was 178.92MiB; child values above are separate current-process VmHWM, not inherited rusage. Cgroup peak charged memory was 286.35MiB and has different shared-page accounting.

The container exited normally and was removed; no forced cleanup was required, **zero containers remained**, and dedicated host staging plus all private `/tmp` case outputs were deleted. No production `docker exec`, service restart, global model overwrite or frozen scientific source/data/provenance edit occurred.

This evidence establishes the reviewed artifact's numeric/resource compatibility and the new runtime's actual CLI behavior on these four packaged DEVELOPMENT cases. It is **not** a final scientific evaluation, a survey-precision estimate, a real-planet probability claim, an API/UI end-to-end check or a worst-case workload guarantee. Root owns final metrics and promotion.

`candidate_bound_container_probe.py`, `candidate_bound_run_ssh.py` and the unchanged shared `candidate_remote_runner.py` are the exact producers. Full evidence is `candidate_bound_vps_benchmark.json`; `candidate_bound_manifest.json` inventories source/report bytes. Reproduction from the namespace root uses:

```bash
/home/usatovpavel/edu/UtilsAI/.venv/bin/python \
  verification/vps-benchmark/candidate_bound_run_ssh.py \
  --candidate-dir backend/inference/models/experiments/v3-selected-candidate-profile-bound \
  --output /tmp/candidate-bound-vps-benchmark.json
```
