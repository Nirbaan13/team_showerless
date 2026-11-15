# Controlled injection-ranking figures

These standalone PNG and SVG figures describe the frozen, canonically unblinded comparison. The comparator is the **frozen C13 scorer under shared amended coverage-preserving preparation**, rather than the old deployed end-to-end C13 pipeline. No pixels, model artifacts, score calls, fitting, or new selection were used.

`primary-macro-deltas` shows native K1/K3 gains and synthetic K1/K3 gains in percentage points, using exactly the paired 95% intervals already validated in the frozen report. Native uncertainty clusters all derivatives by their 12 parent fields; synthetic uncertainty uses whole fields. These bars do not introduce new inference.

`native-k1-speed-brightness` and `native-k3-speed-brightness` show descriptive recovery differences. Every cell contains 72 planned trials: 12 native parent backgrounds times six directions, with one truth per trial. Every original competitor remains in its original stable score order. No injection, candidate, coverage category, or low-span trajectory was filtered or recentered. Each matrix retains all 3,240 planned native trials. Both maps use one symmetric color scale. Cells have no new uncertainty intervals and no multiplicity adjustment.

Speed is in pixels per hour. Brightness follows the frozen injection engineering convention: flux is scaled so a typical supported projected ePSF peak equals the requested brightness multiple of the median nonempty-epoch robust MAD reference. It is not calibrated flux, physical source signal-to-noise, or a probability. Fixed passband flux, correlated residual noise, absent injected photon noise, and native D1–3 coverage remain limitations of the underlying experiment.

Finite true-center coverage is not a hard necessary detectability ceiling; nearby valid peaks can recover PSF wings within the fixed matching tolerance. Covered or actual matched truth spans are diagnostic geometry rather than confirmation of physical motion. The figures show controlled injection ranking, not newly discovered objects or real survey sensitivity.

The two CSV files contain exact point values and counts. `manifest.json` binds their hashes, all image hashes, producer source, and frozen input cache/report hashes. The original report remains SHA `15cabb840cb8af95771f3534f2b5adfb18caaff5f0e8b57ed678f858525f7e56` and is unchanged. No gate or release decision is made here.
