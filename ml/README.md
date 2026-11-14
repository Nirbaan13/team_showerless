# 3I/ATLAS interim result

Open `spherex-result.png` to see the four aligned exposures. Read the panels left to right, top to bottom. Rings mark detections from the top-ranked track. `candidate-example.json` gives the exposure IDs, UTC midpoints, sky coordinates in ICRS degrees, and the offsets from the published ephemeris. It is sample data for review and integration.

From the extracted folder, run `python3 demo_spherex.py` with NumPy and SciPy to reproduce the PNG and terminal output. Run `python3 benchmark.py --spherex` with scikit-learn to compare both rankings on the real exposures.

On these four exposures of the known comet, the track ranked first out of 25 with baseline scoring, with a maximum offset of 0.54 pixel. This run retained pixels flagged OUTLIER. Random Forest was trained on simulated fields and ranked the same track second out of 25 on the real exposures. This is a test on one known object.

Source: NASA/IPAC IRSA SPHEREx Quick Release 2, DOI 10.26131/IRSA652. Observation table and download links: https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html
