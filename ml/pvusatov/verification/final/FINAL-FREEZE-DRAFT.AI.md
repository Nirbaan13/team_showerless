# Unsigned final-freeze metadata draft

This preparation binds the already selected candidate and predeclared datasets. It does not authorize execution. `draft-331c6b1/final-freeze.draft.json` has `status="draft"`, `scope="final"`, `authorized_final=false` and `unsigned=true`; the existing runner rejects it immediately, before scientific loading. Neither final runner, a simulator, a FITS reader nor a model runtime was invoked by this builder. Native FITS, ONNX and calibration artifacts were read only as opaque byte streams for SHA-256/size checks. No headers or final pixels were opened.

The source commit supplied by the coordinator is `331c6b170da23809123f18387236a3fac1400a82`. The draft binds all 15 current `run_native.SOURCES` files separately; the new preparation script is additional provenance outside that existing source set. The builder uses the runner's actual `OPTIONS`, `MATRIX` and `versions()` metadata rather than maintaining a second copy. It cannot emit an authorized frozen payload and refuses to replace existing output directories.

Baseline model and metadata come from the self-contained immutable `releases/v2/backend/inference/models/` archive. The selected candidate is the exact published `artifacts/v3-development-candidate/` copy: ONNX `c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204`, metadata `983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04`. Default deployed/runtime weights remain v2. No candidate fitting, reselection or promotion is part of this preparation.

The independent acquisition check reads the original published audit, expanded audit, final byte audit, and the exact eight-row augmented download manifests. It streams all referenced native file paths for byte/hash agreement and maps the physical `obs_id`, excluding detector/version/crop filenames from group identity. The resulting `physical-observation-audit.json` contains all 200 physical observations: 43 train, 77 development validation and 80 final, grouped into 8/11/10 parents. Cross-parent and cross-split physical OBSID reuse is rejected, including reuse through another detector. Multiple short/augmented copies within one parent remain one physical observation. All acquisition publication-index entries and the immutable historical selection-source snapshot are verified against their original hashes; historical documents are not rewritten.

The final parent list is canonical `final01` through `final10`, seeded 2200001 through 2200010. Each parent uses precisely the audited augmented eight observations; the copied JSON manifests preserve original bytes and absolute native-file locations. All newly generated artifacts are under `ml/pvusatov/`; the large opaque native files remain in their existing external `/tmp/spaceapps-v3-native-data/` locations. The region is 6 by 6 arcmin, pixel scale 6.15 arcsec and mask policy `motion`. The two runner profiles are primary minimum speed 0.5 and secondary minimum speed 0.005 pixels/hour, both using those same augmented observations. Historical short exposure variants are separate correlated secondary evidence, not additional independent parents or a different dataset silently substituted by this draft.

Synthetic seeds are exactly 2000000–2001999, with varying PSF and `seed % 3 == 0` extended fields. Calibration-bank SHA-256 is `793e05135438c95b8eaeace21948b34fe2eb49cd581be9e81dfff2b493e08d6d`. The bank was hashed without loading its arrays. Runtime bounds are six workers, one math thread, maximum 32 frames and maximum grid dimension 512.

The bound execution environment is the actual shared science interpreter: Python 3.14.4, NumPy 2.5.3, SciPy 1.18.1, Astropy 8.0.2, ONNX Runtime 1.30.0 and Pillow 12.3.0. Fresh Python 3.12 CI verifies compatibility; it is not the execution environment declared by this local draft. The runner rejects a software-version mismatch. Executing under another environment requires a separately reviewed coherent freeze and provenance, never an unrecorded version edit.

Selection provenance explicitly includes input provenance, the independent profile-bound graph/artifact review, historical selection snapshot/invocation, development export and system validation, the pre-final numerical/output-policy supplement, both original and post-policy real-preset reports, the legacy runtime proof and the coordination protocol. Original source hashes inside historical reports remain historical; current execution sources are separately bound. The comet D6 target's rank 3 to 4 compatibility regression remains in the evidence. The post-policy BLOOM correction did not change model weights, detection, raw scores or first-three residual ordering.

Reproduce a **new unsigned draft only**, from repository root, using an unused namespaced output path:

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
MKL_NUM_THREADS=1 taskset -c 0,1 \
/home/usatovpavel/edu/UtilsAI/.venv/bin/python \
  ml/pvusatov/verification/final/build_freeze.py \
  --source-commit 331c6b170da23809123f18387236a3fac1400a82 \
  --output /absolute/repository/ml/pvusatov/verification/final/unused-draft-directory
```

The coordinator must independently review metadata and byte/source bindings, confirm the required fresh CI and source verification, and decide final authorization. The coordinator can then create a **separate** trusted frozen JSON with an external SHA-256 anchor; this unsigned draft and its history stay intact. This document intentionally supplies no final-execution command. Draft preparation is not permission to open final data.

The four metadata tests passed after the missing audit behavior first failed: cross-parent identity rejection, byte-tampering rejection, same-parent variant deduplication and draft rejection before any scientific discovery. The actual draft also self-checks that the existing runner refuses its exact externally hashed bytes because its status is draft.
