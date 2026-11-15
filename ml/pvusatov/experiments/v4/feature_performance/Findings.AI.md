# Feature-performance research, DEV only

The experimental grouped reductions reduced CPU time by about35% on three fixed native DEV full-hypothesis pools. All30 float32 columns were bitwise identical on the six declared replay cases; float64 values, candidate IDs, missingness diagnostics, C596 scores, and complete score order also matched exactly. This is bounded research evidence, not global numerical equivalence or a runtime promotion. The original843 extractor, selected model, released runtime, and association-validation closure remain unchanged.

The prospective protocol is `protocol.json` (SHA256 b892b5772b014450565513cba2a9df6472531e31d3f45b8ca416ee93be72992b). Profiling precedes optimization. Fixed TRAIN01 control atSNR4 produces8030 measured hypotheses. Original extraction takes4.364 process-CPU seconds unprofiled; cProfile records7.751 seconds. Map sampling uses0.140 profiled seconds(1.8%). There are68305 median calls using2.884 cumulative seconds and16060 repeated Candidate.features calls using1.889 cumulative seconds. The profile supports reducing per-track reductions rather than rebuilding map sampling or memoizing spatial points.

`prototype.py` inherits original map sampling. It groups seven residual-photometry reductions by usable matched-epoch count, in blocks of at most4096 rows. It validates the immutable measured Candidate features once and reuses their six values. Weighted astrometry, coherent dot products, other common-epoch statistics, masks, candidate identifiers and diagnostic construction retain the reference arithmetic. Missing photometry remains explicit, with the same diagnostics and validity flags.

The prototype honestly emits its own `feature_source_sha256`, a separate `reference_feature_source_sha256`843 binding, and an experimental producer label. It does not claim the selected model's843 source binding for new code. No artifact metadata is altered. C596 scoring here is a parity diagnostic on these explicitly distinct experimental inputs.

The fixed benchmark uses three existing TRAIN packets and replays only old DEV synthetic seeds3806000/1/2. Replayed images must match the earlier pilot image hashes before extraction. It draws no new evaluation/holdout/FINAL field and consumes no truth labels. Three alternating reference/prototype repetitions run on one pinned CPU, with math threads1.

| Fixed old DEV case | Hypotheses | Original median CPU seconds | Prototype | Speedup |
|---|---:|---:|---:|---:|
| TRAIN01 control |8030|5.02309|3.26395|1.539×|
| TRAIN03 control |5113|3.28311|2.13025|1.541×|
| TRAIN01 speed1/direction0/brightness3 |8454|5.53251|3.60636|1.534×|
|3806000|0|.000322|.000399|.807×|
|3806001|15|.049303|.045205|1.091×|
|3806002|716|.638875|.398296|1.604×|

All22328 rows across all six planned cases have identical float64 values and float32 bits. IDs, full per-candidate diagnostics, semantic metadata, C596 score vectors and full rank order are identical. Empty-pool overhead is worse and is retained as a negative result. Maximum observed processRSS is220.18MiB for this sequential replay process; this is not an isolated reference-versus-prototype memory comparison or a worst-shape production guarantee. Groups reach2805 rows here, so the4096-row block boundary is not exercised by these real pools. No claim is made for other platforms, larger groups, arbitrary dynamic ranges or future model families.

Two meaningful parity tests cover signed/masked images, partially unsupported patches, an empty epoch, mixed candidate lengths, explicit missingness, and an empty candidate pool. Both pass after implementation. No scientific or ranking differences were observed in these tests or the six replay cases. The prototype is not copied into runtime, substituted into any cache, or used for model fitting or policy selection.

`benchmark-v1.json` contains timings, exact matrix hashes, differences, provenance and outcomes for every declared case. Its measured plan is preserved byte-for-byte at `source_history/benchmark-plan-v1.json`. Root requested a unique pytest basename after measurement, so `test_prototype.py` was renamed to `test_feature_performance.py` with unchanged bytes. `test-path-provenance.json` records this administrative move and the current `benchmark-plan.json` resolves the new test path; producer and benchmark source bytes are unchanged. The old test source is retained as noncollectable text. Two tests were rerun under the unique basename and passed.

The benchmark computation finished before the hard work deadline. Its handoff was delayed past that deadline; no new exploratory measurements or source promotion were performed afterwards. Final activity was limited to the required test basename correction, evidence documentation and source-stable handoff.
