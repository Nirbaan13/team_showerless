# Runtime detector-profile implementation plan

**Goal:** Ensure a validated candidate's deployed feature extraction uses the same immutable filter profile as its scientific evaluation, while preserving a runnable historical v2 release.

**Architecture:** First copy and hash all78 original v2 files into the self-contained `releases/v2/backend/inference` hierarchy, without changing original manifests. Active `model.py` accepts a complete optional profile/family/algorithm tuple only when identical values are embedded in the SHA-verified ONNX artifact. Active `pipeline.py` uses that verified sigma for significance, peaks, shared-reference comparison and published settings. Legacy v2 has no tuple and keeps exactly sigma1.2 and its existing algorithm version. Model weights/default installation remain v2 until the final gate.

**Ownership:** Root owns active model/pipeline tests and legacy-release test anchoring. Exporter owns ONNX property emission; runner agent owns source closure/final tooling; preset agent owns independent development diagnostics. No agent changes the historical snapshot.

**Constraints:** Six float32 inputs and output/class semantics stay unchanged. Supported fixed settings are the existing defaults, with sigma0.8 or1.2. Public user thresholds/speeds remain request options; detector-profile metadata does not silently replace them. External metadata cannot change the filter/family/algorithm without changing artifact bytes/hash. No fitting or closed-data access occurs here.

1. Verify unchanged archive package tests before active source changes; keep an original file-hash inventory.
2. Add failing tests for graph/external profile agreement, legacy fallback, unsupported profile knobs, stripped/mismatched metadata, accurate family and empty behavior.
3. Add a real-fixture pipeline test comparing actual candidate tracks to direct detection with sigma0.8 and asserting reported sigma/version. Expected positions never enter detection.
4. Implement minimal optional profile validation and pipeline routing. Anchor historical freeze verification to the immutable snapshot, while current behavior tests exercise active source.
5. Run active and archive suites/smokes; ask the source owners to regenerate their DEVELOPMENT freeze against the stable core. Include pipeline/render/CLI in the root final source closure before final authorization.

Review focus: metadata stripped from a new graph; profile changed without artifact change; significance rendered with a different sigma than detection; old v2 outputs or job identity changing unintentionally; and a frozen v2 audit being made to pass by rewriting original evidence. Tests and the archive explicitly cover these cases.

The pre-final real-preset diagnostic exposed an output-cap regression for saturated sources under the narrow filter. Bound profiles now protect first3 residual reviews and reserve bounded slots for separate unscored BLOOM evidence; legacy installations preserve their original slicing exactly. The same shared helper is used by the actual pipeline and offline preset accounting. The known VestaD3 source remains published at rank100, and the independent cometD6 K3 regression is retained rather than tuned away. This output policy does not change detector features or forest weights.
