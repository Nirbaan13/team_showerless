# Selected real-preset compatibility diagnostic

This DEVELOPMENT diagnostic compares the single selected v3 candidate with immutable deployed v2 on the existing packaged `comet-d2`, `comet-d6`, `vesta-d3` and `vesta-d6` fixtures. These are four selected views of two known objects, not four independent test fields. No training, refitting, second-model selection, final native observation or final synthetic field enters this work. The coordinator's final gate is unchanged.

The implementation is `ml/pvusatov/backend/inference/experiments/v3_evaluation/evaluate_presets.py`. It requires an explicit reviewed candidate SHA-256 and a matching development `freeze.json`; an unready export fails before a runtime model is loaded. The baseline hash is fixed to `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9`. Existing fixture bytes must match their packaged manifest hashes. The candidate uses every field of `metadata.detector_profile`; the baseline uses the actual production defaults and physical arcseconds/hour-to-pixels/hour conversion.

Both systems use the same production preparation, physical midpoint order, masks, pixel scale and leave-one-out semantics. Only after both detectors and frozen scorers finish does the diagnostic read `expected_xy` for offline labels. Labels are keyed back to prepared physical observation IDs, including explicit rejection of inconsistent duplicate labels. Expected coordinates never enter detection, source preparation or scoring.

Each case records source hashes, object group, detector, physical midpoints and intervals, registered shape, finite/outlier/BLOOM fractions, preparation warnings, and stage wall times. Residual candidates retain their six measured features, model score, stable model/heuristic rank, measured positions and detection flags. Known-target recovery is unique-object recovery before ranking and at identical one-review/three-review budgets. Unmatched real candidates remain unlabeled.

BLOOM tracks retain `score=None`, `model_rank=None` and flagged-source warnings. Their recovery is reported separately from residual-model recovery. The `published` cohort mirrors production's scored-residual order followed by unscored BLOOM evidence and its `max_candidates` cap; published review recovery does not turn a BLOOM track into an RF or ExtraTrees probability. Residual-model, heuristic and published-review endpoints remain separate.

The diagnostic flags loss of baseline residual detection, loss of baseline K1/K3 recovery in residual or published ordering, and a candidate execution failure when baseline succeeds. It reports those regressions honestly; it never chooses another model. The independent native v3 holdout was restricted to SWIR detectors 1–3 and does not establish MWIR D6 generalization. Both D6 cases explicitly carry that scope limitation.

Four unit tests first failed against unimplemented guards and then passed: physical-ID label reordering, inconsistent duplicate rejection, stable-tie/unique-target/unscored-BLOOM review accounting, and rejection of an unready candidate. Candidate scoring ran only after the reviewed profile-bound artifact handoff below.

From `ml/pvusatov/backend/inference`, after that handoff:

```bash
/home/usatovpavel/edu/UtilsAI/.venv/bin/python \
  -m experiments.v3_evaluation.evaluate_presets \
  --candidate-model /absolute/path/to/reviewed-candidate \
  --candidate-sha256 REVIEWED_SHA256 \
  --output /absolute/path/to/preset-compatibility.json
```

The earlier `v3-selected-candidate-export2` captured the diagnostic's scaffold in its historical source inventory before implementation completed. Its inventoried diagnostic hash is `affb3a6e7663b43ef2ccbe4e26e074622cdf9eba4fdef09bc7d3b88edcfa5256`; completed evaluator source hash is `af40c7f77f721506508796125efd0d45fb61497616954c737a268231a9278a69`. The coordinator explicitly chose to retain that export as a historical snapshot rather than rewrite it. Any actual diagnostic result must record its own executed-source hashes and exact artifact hash. A later trusted final freeze must bind the final coherent runtime/profile/source inventory.

## Historical compatibility result before output-policy amendment

The exact reviewed candidate was `v3-selected-candidate-profile-bound`, ONNX SHA-256 `c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204`, metadata SHA-256 `983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04`. Its family is ExtraTreesClassifier, algorithm `motion-extra-v3-sigma08`, and bound detector profile differs from default v2 only by sigma 0.8 versus 1.2. It is the same previously selected cached estimator, not a replacement chosen using these cases.

**There are real compatibility regressions.** The comet D6 target remains detected, but drops from model rank 3 to rank 4 and therefore leaves the three-review budget. In Vesta D3, the known target remains an unscored BLOOM track, but the narrower detector's 112 scored residual tracks push that appended evidence to rank 113, outside the published 100-candidate cap. The baseline retained it at rank 26. These failures are preserved rather than used to choose another model.

| Development case | Residual candidates, v2 → candidate | Known residual target model rank | Residual K1 / K3, v2 → candidate | Known unscored BLOOM evidence in published list |
|---|---:|---|---|---|
| comet-d2 | 2 → 1 | 1 → 1 | yes/yes → yes/yes | No BLOOM target |
| comet-d6 | 10 → 36 | 3 → 4 | no/yes → no/no | No BLOOM target |
| vesta-d3 | 25 → 112 | Not recovered as residual by either | no/no → no/no | rank 26 retained → rank 113 excluded |
| vesta-d6 | 7 → 17 | Not recovered as residual by either | no/no → no/no | rank 8 retained → rank 18 retained |

The comet target remains heuristic rank 1 in both detectors for both comet cases. Its uncalibrated model score increases from 0.6415 to 0.8180 in D6 while its rank worsens, illustrating why score magnitudes are not calibrated object probabilities or directly comparable model quality. Both Vesta known targets are BLOOM-only evidence here and receive **no model score**. Candidate Vesta D3 reaches the 100-peak cap in two epochs and the published-candidate cap, so its search/output limitations are explicit. No cap is reached in the other three cases.

The actual spans are approximately 3.220 hours for comet D2, 8.077 hours for comet D6, and 26.064 hours for both Vesta views. Preparation/detection/scoring used those physical midpoints and the same motion masks. Local component detection/scoring wall times (seconds) were:

| Case | V2 detection / scoring | Candidate detection / scoring |
|---|---:|---:|
| comet-d2 | 0.0106 / 0.00044 | 0.0098 / 0.00049 |
| comet-d6 | 0.0816 / 0.00067 | 0.0897 / 0.00189 |
| vesta-d3 | 0.0476 / 0.00084 | 0.0707 / 0.00295 |
| vesta-d6 | 0.0390 / 0.00080 | 0.0417 / 0.00080 |

These component timings exclude process startup, rendering, network retrieval and API queueing; they are not VPS latency or worst-case service claims. The separate bounded VPS report covers immutable v2 only.

Detailed scores, heuristic ranks, positions, detection flags, exposure metadata, intervals, masks, source hashes and costs are retained in `experiments/v3_evaluation/results/preset-compatibility.json`, SHA-256 `6f98ce350160be88aa783aabf334a08f60020d1836d7e44c0dc25ffb0b9d48dd`. The compact `preset-compatibility-summary.json` derives published target presence using the explicit residual-then-BLOOM cap rule. All unmatched real identities remain unknown. Final native/synthetic data were not opened, no fitting or reselection occurred, and the root final gate is unchanged.

## Post-policy compatibility diagnostic

Before final data access, the coordinator amended the generic published-list policy for artifact-bound profiles. The shared runtime helper `select_review_entries` protects the first three ordered residual candidates, reserves remaining capacity for flagged unscored BLOOM tracks, and fills remaining residual slots. Models without a bound profile retain the exact legacy list slice. No detector, feature, score, weight or selected estimator changed. The diagnostic calls that same helper on unlabelled records; expected-position labels are joined only afterwards.

The new four-case run uses the same `c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204` candidate. Vesta D3 now publishes 99 residuals and its known BLOOM track at review rank 100, with `score=None`. Its residual count remains 112 and both peak-cap and published-cap flags remain explicit. Comet D2 remains model rank 1; comet D6 remains rank 4 versus v2 rank 3 and still fails the three-review compatibility endpoint. Vesta D6 retains its unscored BLOOM at rank 18 versus v2 rank 8. No replacement model was selected using these results.

All residual records, measured features, model scores and raw ranks in both systems across all four cases equal the original negative report exactly. That original detailed report, compact summary and historical manifest remain unchanged. Their historical source hashes describe the earlier implementation; the new source/policy hashes are recorded separately, rather than rewriting the old manifest. Historical manifest paths beginning `backend/` are relative to the namespaced `ml/pvusatov/` root.

The post-policy detailed report is `experiments/v3_evaluation/results/preset-compatibility-post-policy.json`, SHA-256 `06ffe5003f627e2842c55d43ee59e701551593cfc063265ee21763b68eb6bd88`. Its new compact summary uses actual selected `published.model_entries` for target presence and review ranks. Its separate post-policy manifest binds the current evaluator, tests, shared helper source, documentation and reports. This is still development evidence on two known objects; D6 generalization and the unchanged final gate retain their earlier limits.

Independent policy review covered 1,728 combinations of residual count, BLOOM count and capacity: exact legacy slice, bounded output, protected first-three residual prefix, stable residual order, no duplicates, unscored BLOOM and unchanged uncapped lists. The root policy/profile suite passed 13 tests; combined with the five diagnostic tests, 18 passed. The diagnostic regression verifies that both model and heuristic publication call the shared helper with unlabelled original records. Final native and synthetic fields remained closed throughout.
