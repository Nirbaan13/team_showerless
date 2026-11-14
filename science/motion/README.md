# SPHEREx Motion Review

Motion Review displays moving objects from real NASA/IPAC IRSA calibrated exposures: 3I/ATLAS (QR2) and (4) Vesta (DR1). The app ships a generated bundle and needs no runtime connection to IRSA.

## Run the demo

From the repository root:

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open **Motion Review → (4) Vesta · D3 → Difference image** and switch between the three timestamps. The bright ring around the dark core shows the wings of the saturated source. The green marker follows the centroid of its flagged core. **BLOOM mask** shows the exact data used by that tracking method. **Stack the evidence** compares fixed and moving stacks on the same scale. **Export candidate JSON** includes timestamps, ICRS coordinates, ranks, and per-detection quality information. For the comet, try **3I/ATLAS · D2 → Difference image** and switch between **Heuristic** and **Random Forest**.

## Reproduce the analysis

Install Python dependencies `numpy scipy scikit-learn` (the Random Forest run used scikit-learn 1.6.1). Run:

```sh
python science/motion/review.py \
  science/motion/cases/december-d6.npz science/motion/cases/december-d2.npz \
  science/motion/cases/vesta-d6.npz science/motion/cases/vesta-d3.npz \
  --compare-random-forest --output frontend/public/motion/review.json

python -m unittest discover -s science/motion -v
```

The included NPZs hold reprojected pixels and quality masks. To rebuild them, install Astropy and download the exact IRSA cutouts from [observations.csv](cases/observations.csv), grouped by series and saved by observation ID with a `.fits` extension. Run `prepare_fits.py` once per series:

| Series | `--center RA DEC` | `--shape WIDTH HEIGHT` | Extra option |
| --- | --- | --- | --- |
| december-d2 | `167.204 5.147` | `104 76` | |
| december-d6 | `166.79 5.29` | `256 144` | |
| vesta-d3, vesta-d6 | `223.025 -11.992` | `222 174` | `--include-bloom` |

For example:

```sh
python science/motion/prepare_fits.py cutouts/vesta-d3/*.fits \
  --center 223.025 -11.992 --shape 222 174 --retain-outliers \
  --include-bloom --ephemeris science/motion/cases/observations.csv \
  --output science/motion/cases/vesta-d3.npz
```

The pipeline subtracts zodiacal foreground, applies the detector quality mask, and resamples to a shared ICRS TAN grid at 6.15 arcsec/pixel. Each exposure gets a background reference from other frames with valid coverage. A Gaussian filter renormalizes around masked pixels, requires at least 80% support, and identifies positive residual peaks. The tracker links approximately linear paths over three or more exposures. The heuristic uses track length, median residual S/N, and fit error. The Random Forest learns on 80 simulated fields, then reranks the exact same real residual candidates. It cannot recover a track missing from that candidate list.

For saturated sources, a separate pass links the centroids of connected `BLOOM` regions with at least six pixels. This uses the existing SPHEREx FITS quality flag; measurements from saturated pixels never enter flux detection. The bloom mask stack is visual evidence of alignment, not a brightness measurement. The residual stack is a visual check with no calibration as formal significance.

## Results on the selected fields

| Object and detector | Frames | Shared median | Heuristic, per-frame reference | Random Forest, same tracks | BLOOM centers | Max offset from IRSA |
| --- | ---: | --- | --- | --- | --- | ---: |
| 3I/ATLAS · D6 | 4 | #1 / 25 | #1 / 10 | #3 / 10 | — | 0.54 px |
| 3I/ATLAS · D2 | 3 | No tracks | #1 / 2 | #2 / 2 | — | 0.60 px |
| (4) Vesta · D6 | 3 | No match | No match | No match | #1 / 1 | 0.28 px |
| (4) Vesta · D3 | 3 | No match | No match | No match | #1 / 1 | 0.38 px |

Vesta moved about 49 arcsec/hour over 26 hours. The maximum offset from [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) as seen from Earth's center is 2.13 arcsec on D6 and 1.61 arcsec on D3. [The Horizons positions](cases/vesta-horizons.csv) use the FITS exposure midpoints and astrometric ICRF RA/Dec (observer table, `COMMAND='4;'`, `CENTER='500@399'`, `TLIST_TYPE='JD'`, `QUANTITIES='1'`, `ANG_FORMAT='DEG'`). This cross-check uses a different observer location from SPHEREx.

Comet D6 was also ranked first by the heuristic in each of four runs that omitted one exposure. Retaining the `OUTLIER` pixels was necessary for the residual detector to recover the comet on the selected fields. Vesta's separate pass uses the `BLOOM` flag, so the residual mask choice does not affect it.

Ephemerides were used to select demonstration fields and to label matches **after** detection and ranking. Matches fall within 1.5 px in every linked exposure. Unmatched tracks remain unreviewed. These selected exposures of two known objects are a repeatable recovery check. They do not estimate survey recall, false positive rate, or performance of a model trained on real labels.

Data from NASA/IPAC IRSA. [SPHEREx 3I/ATLAS observations](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html) · [IRSA lookup for Vesta exposures](https://caltech-ipac.github.io/irsa-tutorials/most-queries/) · [SPHEREx FITS documentation](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/).
