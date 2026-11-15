# Maximum-shape density engineering probe

The fixed runtime completed the eight-source workload with an explicit incomplete-search warning. The 32- and 100-source workloads returned the bounded CLI error `workload_limit`. Maximum accepted image dimensions therefore do not imply that every source density completes.

| Generated moving sources | CLI outcome | Wall seconds | Child peak RSS, MiB | Published candidates |
|---:|---|---:|---:|---:|
| 8 | success; candidate cap reached | 21.9706 | 661.234 | 100 |
| 32 | `workload_limit`, exit 2 | 3.8219 | 417.730 | none |
| 100 | `workload_limit`, exit 2 | 4.0729 | 417.738 | none |

These are **local wait4 child RSS measurements**, not Docker/cgroup peaks or a hard 1 GiB guarantee. One CPU affinity and one math thread were enforced. No case required the sampled 1 GiB RSS stop or 300-second timeout. The error cases have finite error JSON and retain stderr stages; they were not successful model rankings. Generated source counts are not detected source counts: the eight-source case produced many review proposals and explicitly reported `candidate_cap_reached_search_incomplete`.

All cases use 32×512×512 float32 images, deterministic seeds `4200000+source_count`, independent Gaussian engineering noise σ=0.05, and normalized discrete Gaussian stamps of σ=0.8 and amplitude 50. Sources start on a 10×10 grid with 40-pixel separation, follow `(x0+t,y0+0.2t)` at 32 hourly epochs, remain inside the image, and never wrap. No instrument flux/noise calibration or recovery/sensitivity claim is made. Actual CLI settings remain `min_snr=4`, `max_candidates=100`, `max_peaks=100`, with the unchanged remaining defaults and selected artifact. The trusted preset parser identifier `comet-d2` is only a transport mechanism; these inputs are synthetic engineering fixtures, not comet observations.

The first eight-source fixture attempt was rejected before detection because hourly NumPy timestamps lacked the required ISO seconds. Its original plan, runner snapshot and failed proof are retained. Before any corrected run, `plan-v2.json` prospectively recorded the serialization-only correction; images, seeds, paths, options and model were unchanged. A timestamp regression test now exercises the actual Astropy ISOT parser. No runtime, model, default or case was changed in response to the density outcomes.

Selected graph: `c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35`. Metadata: `472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13`. Plan v2: `82b9e11bddae88e43737b62e6fa343fc368ca4cfbd58c472325c225b8be2c331`. The plan and every case bind all eleven runtime source hashes. Temporary NPZ inputs and PNG outputs are deleted after byte hashing; source, requests, actual result JSON, logs and resource-hash metadata remain published. No FINAL or Ceres images were accessed.

`portable.py` accepts a read-only runtime bundle and external output directory. It validates exact source-set, graph and metadata hashes before running the unchanged generator/runner through explicit filesystem aliases. Example for the separately controlled VPS container:

```sh
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python /probe/density/portable.py --runtime /probe/inference \
  --model-dir /probe/inference/models --output /evidence/density
```

Place `portable.py`, `probe.py` and `plan-v2.json` together in `/probe/density`. A new output directory is mandatory. The wrapper does not run Docker or alter services; the host must independently record its actual CPU, memory/swap, mount, network, UID and OOM evidence. Temporary fixtures use `/tmp`; account for tmpfs and the generator parent in the **whole-cgroup** memory total. A 512 MiB tmpfs ceiling is a capacity ceiling, not preallocated memory. The receipt labels local RSS separately from host cgroup evidence.

Four generator/date tests pass, including path separation/no-wrap and discrete flux. This is an engineering stress test, not a worst-case proof, scientific validation bank, additional holdout or model-selection criterion.

The broader unchanged V4 runtime/coverage suite plus these four tests passed **34 tests** with `PYTHONPATH=ml/pvusatov/backend/inference`. An initial launch omitting that existing package path reported one import failure in `test_runtime_median_function_is_the_verified_prototype_without_math_edits` (33 passed); correcting only the launch environment made all 34 pass.

The external-output wrapper was actually replayed locally. All three NPZ byte hashes and outcomes matched; the successful case's candidates, scores, settings, model and warnings were exactly equal. Its eight-source repeat took 144.385 seconds wall versus 17.884 seconds child CPU, with 661.480 MiB child peak RSS; the large waiting component is not attributed to a specific cause or treated as a speed comparison. Repeated 32/100-source cases returned the same `workload_limit` in 3.937/4.189 seconds, respectively. No monitor stop occurred. `portable-local/` preserves these separate proofs and equivalence receipt; repeated runs are not additional scientific evidence. The receipt SHA is `5e9520467df7b67a5cd7ca213f1ba4693c61c2c6af74b36fe89c00a8f51623ca`.
