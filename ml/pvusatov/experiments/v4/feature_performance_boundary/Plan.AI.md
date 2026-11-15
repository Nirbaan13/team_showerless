# Feature block boundary engineering parity implementation plan

> Execution: inline, within this new directory. Explicit task authorization supersedes skill confirmation/commit defaults.

**Goal:** Exercise the existing research prototype's untested 4096-row grouping boundary against the immutable original extractor, without promotion or scientific evaluation.

**Architecture:** Deterministic numeric image stacks feed real immutable `Candidate` records with measured SNR, shape ratios, and fitted geometry. Both unchanged extractors receive identical inputs. The unchanged C596 runtime scorer supplies score and complete stable-order comparisons, solely as engineering diagnostics on the explicitly different producer.

**Constraints:** Original SHA8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282; prototype SHA47e3486cc94e65f520244575fc5dee8517ac5aa2e4f84c3f8a70c477df90102d. No labels, held-out or FINAL reads, fitting, runtime/cache/model changes, commits, deployment, or performance-promotion claim. One pinned CPU, math threads1, address space <=8GiB, elapsed <=30 minutes. Shared UtilsAI interpreter. Large matrices remain in memory; compact results only in this directory.

**Frozen inputs before generation:** Cartesian product of epoch counts8/16; boundary group sizes4095/4096/4097/8192/8193; scenarios `finite_noise`, `signed_quality`, `finite_support` (30 cases). Per scenario/epoch seed is 3810000+100*epochs+scenario_index. Shape is64x64; irregular increasing times; sigma=.8. Finite noise has changing per-epoch Gaussian noise. Signed quality adds deterministic spatial/epoch background and both boolean quality masks. Finite support additionally masks the first three rows, makes the final epoch entirely NaN, and the penultimate raw epoch constant zero. Paths exclude only the empty epoch; their interior residual support is independently checked. Each case appends four measured controls: two edge paths (missing patch support), and two shorter interior paths (3/4 epochs). Empty pools for both epoch counts are additional controls.

**Representation:** Paths are engineered sampling locations, not detections claimed from real fields. All path coordinates are finite and bounded; sampled raw intensities and robust frame noise provide actual measured SNR (zero for a constant frame), smoothed intensity ratios provide shape proxies; least squares supplies RMS/speed. No injected source positions or labels are consumed. Each Candidate's six inherited features must be finite. No unsupported observed-science or sensitivity claim follows from these numeric fixtures.

**Review focus:** Homogeneous groups must actually reach each declared size in returned diagnostics; remainders after both4096 and8192 must survive; all30 F64/F32 columns must match by bits including signed zero; stable ordering must include every tie/row; empty and missing photometry retain explicit diagnostics. Source and model metadata hashes checked before/after.

- [ ] Add unique-basename tests for measurement validity, boundary remainder/tie-order parity, and empty pool/missing-support controls. Establish a failure for the missing harness before implementing it.
- [ ] Implement `boundary.py` with deterministic measured fixture construction, independent input/support validation, original/prototype whole-contract comparison, and actual C596 scoring. Preserve every mismatch without tolerance or trimming.
- [ ] Freeze protocol/source/model hashes before generating any input. Execute all30 main cases plus2 empty controls, incrementally save compact JSON, retain errors and differences as negative results.
- [ ] Run the declared tests and inspect complete result coverage/hashes. Write English findings and evidence index with limitations and exact command.
