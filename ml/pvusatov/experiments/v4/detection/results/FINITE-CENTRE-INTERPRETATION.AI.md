# Finite-centre diagnostic interpretation

This is an interpretation correction supported by a controlled development counterexample. It changes no cached values, sources, candidate generation, scoring, primary denominator or promotion gate. Active final snapshots and geometry code remain immutable; no actual final pixels or outcomes were inspected.

`geometry_capability` counts epochs whose rounded true centre lands on a finite image pixel, then reports the truth span over that subset. These are useful, explicitly defined engineering diagnostics. They are not strict necessary conditions for detection and must not be presented as a mathematical upper detectability ceiling. A source's PSF can illuminate neighbouring finite pixels while its centre is masked; a measured offset peak can still satisfy the declared 1.5 px matching radius.

The fixed counterexample uses engineering seed 3803003, three 40×40 independent Gaussian-noise images, times 0/1/2 hours, a normalized Gaussian PSF sigma 0.8 and known simulation amplitude 300. True positions are (12,20),(16,20),(20,20); exactly each centre pixel is set to NaN. The unchanged detector receives only images/times and its standard sigma 0.8/SNR4 settings. It returns one matching measured track at (11,20),(16,21),(21,20), maximum true offset 1 px. No model is loaded and no truth coordinates are passed to candidate generation.

The finite-centre diagnostic therefore reports zero finite centre epochs and `geometrically_testable=False`, while an actual matched track exists with an 8 px truth span over its three matched epochs. This disproves the strict necessary-condition/ceiling interpretation. It does not establish real-data sensitivity or calibrated astrometric confidence.

The 3 px span constant is also an explicit engineering diagnostic threshold, not a fundamental limit of motion observability. This counterexample makes no new claim about calibrated subpixel astrometry. Retain the original allplanned and common-attribution metrics, and separately report actual matched-epoch truth/measured spans with their declared definitions. Do not reclassify unresolved spatial recovery as confirmed motion.

Reproducible numeric/source evidence: `finite-centre-diagnostic-counterexample.json`, SHA256 `6591aba07acf4467f7ac8d969a55fc5d020ad237e05d7aa0581e85dd1b9d2482`. It records generator settings, exact candidates, source hashes, diagnostic values and absence of model/final access. This erratum is separate from scientific data/method changes; no frozen file is corrected in place.
