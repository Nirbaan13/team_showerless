# Development artifacts and immutable source lineage

`v3-development-candidate` is the single selected ExtraTrees/sigma0.8 candidate, SHA-256 `c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204`. It is an exact copy of the reviewed export, including every132-model development outcome, parity diagnostics, numerical-failure history, input/source manifests and resource probes. The installed default remains v2. A development freeze does not authorize closed final data or production promotion.

The candidate creation inventory contains hashes of some then-in-progress, unexecuted runner/diagnostic sources. That history is preserved, not rewritten. The root's separate trusted final freeze must bind the completed evaluation/runtime sources; it is authoritative for final execution. The original weighted graph is unchanged by the profile/family/version property binding.

`v3-selection-source` preserves all19 exact files used by the original development-selection invocation, with their original relative paths, hashes and invocation record. This historical source is separate from later runtime/evaluation guards. It is not another maintained application copy.

`v3-selected-input-provenance.json` retains cache-header provenance and public native URLs/byte hashes. Raw native FITS and large fitting caches remain outside git and are never treated as independent derivatives. `v3-selected-output-policy-parity.json` explicitly scopes numerical parity to ordered K1/K3 and unreserved residual top100: the disclosed ULP swap can change residual membership at quota99 after reserving unscored BLOOM evidence. Final recovery is measured using the actual ONNX artifact, not sklearn approximations.

Known development tradeoffs remain visible in the preset report: cometD6 moves from model rank3 to4, while heuristic rank1 stays available. The generic output policy preserves saturated-source evidence within the bounded list without assigning it a learned score. No second model was selected using these diagnostics or final data.
