# Independent native association comparison

This is research evidence for the fixed `learned_pair` policy against `legacy` using the same C596 ranker and the same complete hypothesis pool. It does not change the deployed association policy, detector threshold, feature extractor, model, or production release. Production promotion remains explicitly unauthorized by this experiment's protocol.

The closed combined report is `research-report.json`, SHA256 `de5d58cad4a95647b60dd6279f34461b80ae0970d34da9ef5c06ddc5dc24ad18`. The native manifest is `native-run-manifest.json`, SHA256 `b6b4f4a06fe54c3fa5e87498303c0daa21d8fa3d078860f81898c464d4d06e4a`. Historical synthetic-only checkpoints remain unchanged.

## Retrieval results

Counts are injected truths retrieved in the first one or three ranked candidates. They are spatial associations to known injected trajectories, not confirmed astronomical discoveries.

| Cohort | Truths | Independent sampling units | K1 legacy → learned | K3 legacy → learned |
|---|---:|---|---:|---:|
| New native, all planned | 1,620 | 12 parent fields | 304 → 400 | 316 → 467 |
| New native, common attribution subset | 1,615 | Same 12 parents | 304 → 400 | 316 → 467 |
| New synthetic | 1,953 | 1,000 fields, 800 with truth | 383 → 450 | 592 → 731 |

Native all-planned macro recall differences are +5.926 percentage points for K1 (paired parent bootstrap 95% interval +1.111 to +11.235) and +9.321 points for K3 (+4.259 to +15.000). Common-attribution differences are +5.966 points (+1.151 to +11.334) and +9.366 points (+4.304 to +15.046). Five trials are excluded only from that additional common-attribution analysis because either policy already retained a spatial match in the uninjected control. All 1,620 remain in the primary all-planned denominator.

Synthetic macro differences are +4.438 points for K1 (+3.094 to +5.865) and +7.344 points for K3 (+5.781 to +8.969). Every interval uses 10,000 paired group-bootstrap draws with seed 2026111502. The native sample size is twelve independent parents; the 1,620 injections are correlated within those parents.

## Motion interpretation and workload

The descriptive resolved category requires at least three pixels of actual truth displacement across the epochs matched by a candidate. It never filters the primary denominator and is not confirmation of real motion. Native resolved K1 changes only 232 → 233; resolved K3 changes 241 → 261. Of the net +96 native K1 recoveries, +95 are unresolved; of the net +151 K3 recoveries, +131 are unresolved. Synthetic resolved K1 changes 319 → 367 and K3 changes 480 → 582.

Native injection retained rows change 131,473 → 130,345; control rows change 950 → 942. Control truths are unknown, so these are workload counts, not false-positive counts or precision. There are zero failed injections and zero peak-cap trials. The injection hypothesis total is 6,304,448; control hypotheses are accounted for separately by the independent auditor.

The producer records 5,132.30 prediction CPU-seconds, including 951.38 legacy-parity CPU-seconds that it also identifies separately. These are instrumentation totals, not separately measured standalone policy latencies. Fewer retained rows do not establish an end-to-end speedup. The separate optimized runtime candidate also remains unpromoted because its paired full-CLI benchmark did not establish a meaningful overall acceleration.

## Provenance and limits

The R2 exact-source freeze is `ae981b56f43c8a14cd6dee9ce61c48853ea7c90b63eca8ddcf586e0a3e3dbbdd`; released native handoff is `6005fd136cdab828cac9c786c18fce2c4977289924f7ff94df3a3ddf92671abb`. Handoff and execution authorization were committed and pushed at `1e28731` before native inference. The policy was selected after a separate development pilot, then fixed before this new synthetic/native comparison. The first synthetic attempt had a JSON serialization defect; its incomplete aggregate was inspected before the arithmetic-preserving R2 repair. The repair must not be described as fully blinded.

Native acquisition amendments followed synthetic unblinding but preceded scientific pixel access to these twelve native parents. They preserve the original parent centers, reserved seeds, exclusions, footprint bound and scientific code. Inputs are 94 server cutouts plus two full original MEFs after cutout transport failures. Old development transport checks found additional edge support and a shifted background median, so full-MEF preparation byte parity is not claimed. Both policies receive the same mixed inputs. See the preserved acquisition chain and `../RELEASE.AI.md`.

The full numeric cache is published outside Git as six bounded release assets to avoid adding 1.48 GB to repository history. `numeric-cache-manifest.json` binds all 3,267 numeric members, six parts and the complete archive SHA256 `78fd49b821c58e891b9bd05c24f63a42edf2d66e3f682399d5d8d1a0d7936173` (1,482,526,720 bytes). It includes every full/compact native record, the closed manifest, combined report and portable fields. It contains no raw FITS. Exact-source independent and relocated guarded audits are recorded separately; their results must be consulted before treating the recount as verified.

Both recounts passed for all 1,632 records and 6,349,758 hypotheses, including controls. The original independent audit SHA256 is `82e8d3e2b37c0899a3142a299055465f4c93dbd2e6404aa6070ed9652705d833`; the relocated portability proof SHA256 is `3e00b8774cdd4cf334c4adf0fd087368f55ecf19ed6254f41289fe7045542771`. The root verification confirms every audit field agrees except elapsed time and peak RSS. The fresh child explicitly rejected the original repository, original cache and `/etc/passwd` probes before its recount. This is Python I/O instrumentation rather than an operating-system sandbox. See `../independent-audit/` and `../portable-proof/evidence/`.
