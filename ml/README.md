# 3I/ATLAS interim result

Open `spherex-result.png` to see the four aligned exposures. Read the panels left to right, top to bottom. Rings mark detections from the top-ranked track. `candidate-example.json` gives the exposure IDs, UTC midpoints, sky coordinates in ICRS degrees, and the offsets from the published ephemeris. It is sample data for review and integration.

From the extracted folder, run `python3 demo_spherex.py` with NumPy and SciPy to reproduce the PNG and terminal output. Run `python3 benchmark.py --spherex` with scikit-learn to compare both rankings on the real exposures.

On these four exposures of the known comet, the track ranked first out of 25 with baseline scoring, with a maximum offset of 0.54 pixel. This run retained pixels flagged OUTLIER. Random Forest was trained on simulated fields and ranked the same track second out of 25 on the real exposures. This is a test on one known object.

Source: NASA/IPAC IRSA SPHEREx Quick Release 2, DOI 10.26131/IRSA652. Observation table and download links: https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html

## Live motion search

Run the ML service and frontend from the repository root in two terminals:

```sh
python -m pip install -r ml/requirements.txt
PYTHONPATH=ml python -m uvicorn service:app --host 127.0.0.1 --port 8001
```

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open **Motion Review → Live archive search**. For a known recovery case, enter RA 223.025°, Dec −11.992°, D3, 23 arcmin, and August 4–5, 2025 UTC. Keep **Retain OUTLIER pixels** checked and select **BLOOM centers** to inspect the track of (4) Vesta. The live search returns unreviewed candidates and does not use an ephemeris to rank them.

The same workflow is available as `POST /api/motion/search`:

```sh
curl --json '{"ra_deg":223.025,"dec_deg":-11.992,"detector":3,"size_arcmin":23,"start_date":"2025-08-04","end_date":"2025-08-05"}' \
  http://localhost:8001/api/motion/search
```

The service searches NASA/IPAC IRSA DR1 and QR3 for calibrated spectral images and aligns cutouts on a common ICRS grid. Search one detector at a time across up to seven UTC dates and 2–30 arcmin. It samples up to eight visits and uses one exposure per visit. It reports skipped downloads or frames with limited coverage, requires at least three usable visits, and returns up to 25 candidates per method along with full counts. Zero candidates is a successful result. Missing coverage and archive errors return separate errors. The detector passband varies across pixels and exposures even within one detector, so residual tracks require review. The live search uses heuristic ranking for residuals and a separate pass for saturated sources. The saved observations still include the experimental Random Forest comparison.

`docker compose -f compose.services.yaml up --build` also runs the workflow through the frontend reverse proxy. For a standalone ML image, use `docker build -f ml/Dockerfile .` from the repository root.
