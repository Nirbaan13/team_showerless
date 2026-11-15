# Independent blinded coverage-repair implementation review

No material implementation or protocol blocker was found in the reviewed source set. The repair is acceptable for sealing a **new amended freeze and rerunning the fixed comparison**, subject to root's preparation-only audit, external authorization, complete reruns and predeclared blinded equality check. This is not approval to unblind early or promote. No FINAL pixels, scientific cache fields, metrics, scores or ranks were opened by this reviewer.

The amendment explicitly identifies the coverage-informed change, preserves original freeze `1896c55288579151576f8e1c7026f3b57959fa8e6c857fed96817a7807c11e57`, and preserves its failed attempt and blinded complete synthetic output. It fixes the same twelve parents, ninety-six observations, 3,240 native trials and 3,000 synthetic seeds, both original models/metadata, proposals, features, matching, denominators and gates. It accurately describes C13 as its frozen scorer under common amended preparation rather than the unchanged deployed end-to-end system on previously unsupported inputs.

The preparation diff retains an empty requested epoch without changing preceding validation, support thresholds, WCS interpolation, flag maps or the arithmetic for covered frames. It warns explicitly and requires the requested minimum of distinct nonempty physical epochs. The native helper excludes only entirely empty registered frames from its MAD reference; any invalid MAD on a nonempty frame remains fatal. RNG consumption, full time vectors and legacy identities are retained. Empty epochs remain NaN, carry false coverage flags and cannot receive measured candidate epochs. The summary checks these conditions against recorded finite-pixel counts and the blinded preparation audit. Primary paired accounting and promotion-gate code are unchanged.

Independent evidence:

- **12 existing helper/coverage tests pass**: all 270 controlled legacy injections, positive/error cases, FLAGS/footprint emptiness, covered preparation parity, and the selected runtime's explicit empty-frame PNG behavior. The runtime test uses controlled temporary FITS, not FINAL.
- **4 worker-transport tests pass**: bounded builtin error transport preserves original error identity and leaves successful scientific results unchanged; no private exception object crosses the process boundary.
- **21 blinded comparison tests pass**, using toy manifests/caches only. Both completed manifests precede scientific decoding; the projection compares exact ordered values and returns counts/digests rather than outcomes. Unexpected differences fail the check without tolerance relaxation.
- `train04-proof.json` (SHA `c8a152cefd530e0eb639e5701d3f21d08f40986b295da7284803206f5e68684b`) verifies actual TRAIN04's eight prepared image/mask/time arrays bitwise and frame/warning/provenance/grid metadata equal. All 270 real-native-ePSF injection images, coordinates and legacy identity fields are exact. A clearly marked temporary TRAIN-only FLAGS-masked derivative also passes 270 trials while retaining eight identities/times and seven MAD references. Original native files were rehashed unchanged; scratch FITS was deleted. This proof ran no detectors or model sessions, in 4.50 s with 258.5 MiB maximum RSS.
- `toy-validation-proof.json` (SHA `6f6d7e7a65b727f13e9ce0d1ddee293e8e2673a62438cc7637a1f37b58d2cc17`) explicitly rejects zero, one and two usable epochs, accepts three while retaining four physical epochs, and confirms unchanged `invalid_fits` rejection for missing HDUs, wrong dimensions and bad dates.

Reviewed key source SHA-256:

| Source | SHA-256 |
|---|---|
| amended prepare | `27ef087aa19f394eaf16ee19c0801ed6c7557a79a7ea77b3410445363f4624ec` |
| original prepare | `e464287bdd6999f75f8d86d1d5ab8fcc3ad977486fad63871763a3b8518dbbeb` |
| native injections | `dfd829e310a74e5bd446a439af9560386bdfb96f5b01386178e32eed024bcf5b` |
| worker transport | `7b0964db0e8dfdca9fec28ae00f8388c0442c114985b9ff811b0eb0ac6fed45f` |
| frozen preflight | `e4fd5c25b4d126e1f658973fa59e0a1b154f82c85a4ab6f800543d194c03d50e` |
| scene | `179ca1f664707b27980825401f6aa77fbc44d2a412a904e0c0494c49c8d0c089` |
| native runner | `d23be6e67eb94f995044d12dc5bc9d96ad586cf50368a628bd9c650ad966e524` |
| report | `4bf049a45f902a5acb0f951f1ae2e24a8396b086b128942ddb94a15ac51785f0` |
| blinded comparison | `6b7fcd4bd2da63b762af235db645504c036c1497e7e48a7303191d02594938fb` |

The proposal text reviewed has SHA `593a6f5bcf13670cfbda0fb79e78a67663dd8e6a6bbba6ed9c3a613bd2e1d3e0`; amendment metadata at review time has SHA `dd5485897856a762e67bafcdc00a1fcb45c430f556fb2083bda642d1ed1d0b19`. Root must seal the exact final metadata/source closure externally before re-execution.

Limits: empirical parity here covers one actual TRAIN parent plus controlled cases. No amended FINAL preparation counts or scientific rows were personally checked. The original diagnosis establishes one failing parent, not its number of empty epochs. Exact 3,000-field synthetic equality and any available unaffected-native equality remain future checks; they have not been claimed from toy tests. All resource, integration and recovery requirements remain separate mandatory gates.
