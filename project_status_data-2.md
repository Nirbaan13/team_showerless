# 📊 Project Status & Data Summary: SPHEREx Sky Explorer

## 1. Project Objective & Scope

* **Mission:** Build a public-facing web tool for NASA’s SPHEREx mission to display multi-epoch near-infrared sky cutouts across 102 spectral bands, enabling users to track celestial changes over time (such as moving comets, asteroids, brown dwarfs, stars, and cosmic transients).

* **Target Coordinates:** Support for custom coordinate input ($RA$, $Dec$, $FOV$) and pre-configured NASA benchmark targets:

  * **Barnard’s Star:** $RA\ 17\text{h}\ 57\text{m}\ 48.498\text{s}$, $Dec\ +04^\circ\ 41'\ 36.1139''$

  * **Epsilon Indi B:** $RA\ 22\text{h}\ 04\text{m}\ 10.595\text{s}$, $Dec\ -56^\circ\ 46'\ 58.239''$

  * **WISE 0855:** $RA\ 08\text{h}\ 55\text{m}\ 10.831\text{s}$, $Dec\ -07^\circ\ 14'\ 42.53''$

  * **Variable/Transient Targets:** `RW Aurigae` and `R Draconis`

## 2. Repository Architecture & Deployment Status

* **Tech Stack Composition:** TypeScript (Frontend), Python / FastAPI (Backend), Docker, Shell scripts, CSS, and HTML.

* **Repository Structure (`team_showerless`):**

  * `/frontend`: Interactive sky viewer, timeline controls, dual user views, mobile volunteer view, verification feed, and embedding features.

  * `/backend`: FastAPI endpoints handling targeted IRSA/SPHEREx query routines, range/polygon/deep observation lookups, metadata/equipment endpoints, motion search, and live image cutout generation.

  * `/ml`: Machine learning tracking and classification modules.

  * `/ops` & `compose.yaml`: Containerized environment configuration.

  * `.github/workflows`: CI/CD automation pipelines for continuous deployment.

* **Live Deployment:** Hosted on cloud infrastructure (`144.124.238.101` / `35.159.162.202`), with the frontend available on port `8080` and backend Swagger documentation at `/docs`.

## 3. Data Processing & Pipeline Implementation

* **Targeted Archive Queries & Live Cutout Retrieval:**

  * Bypasses full-sky FITS downloads by utilizing SPXQuery and IRSA range, polygon, and deep observation (`observationsDeep`) endpoints.

  * Live frontend integration actively pulls and renders real cutout images from NASA/IRSA archives, supplemented by metadata, equipment, and `/api/motion/search` endpoints (`d50f070`).

* **Background & Noise Subtraction:**

  * Subtracts Zodiacal light (`ZODI`) model.

  * Subtracts median reference sky.

  * Applies `FLAGS` masking to filter out bad pixels, cosmic rays, and instrumental anomalies.

* **Detector Array Resilience:** Organizes data by observation date across detector arrays ($1\text{--}6$). Implements automatic frame-skipping logic when a coordinate lacks coverage across all detectors, preventing playback crashes.

* **Known Object Catalogue & Verification:**

  * Built-in **Known Object Catalogue** fetches already-cataloged objects at queried coordinates across multiple space agency databases to prevent duplicate discoveries.

  * Paired with an interactive **Verification Feed** for human-in-the-loop candidate confirmation.

## 4. Empirical Testing & Validation Results

* **Comet Detection Benchmark:** Tested on four real SPHEREx observation images containing **Comet 3I/ATLAS**.

* **Accuracy:** The detection pipeline successfully located the comet in every frame within $0.54$ pixels of its predicted trajectory.

* **Ranking:** Ranked $1\text{st}$ out of $25$ candidates using baseline tracking and $2\text{nd}$ using a Random Forest classifier trained on simulated data.

* **Frontend ML Integration:** Machine learning detection overlays and backend `.api/observations` hooks are integrated into the web viewer for end-to-end testing.

## 5. UI/UX & Advanced Features

* **Dual User & Mobile-Responsive Views:**

  * Tailored interfaces separating complex scientific tools from a simplified, accessible layout for volunteers and citizen scientists.

  * Dedicated mobile-specific responsive design enabling volunteers to inspect and verify sky cutouts directly from smartphones.

* **Live Demo Resilience:** Built-in offline auto-fallback mechanisms in the frontend to ensure continuous uptime during network interruptions or API timeouts.

* **Sharing & Embedding:** Stateful URL generation encoding view parameters ($RA$, $Dec$, area size, detector, subtraction mode, frame) along with a one-click `<iframe />` embed snippet.

* **Data Health Panel:** Diagnostic interface displaying per-frame metadata (date, detector, wavelength, percentage of flagged pixels) with transparent explanations for skipped frames.

* **Spectral Analysis (Stretch Goal):** 102-band flux-vs-wavelength extraction (`WCS-WAVE`) to analyze material composition (carbon, silicate, water-ice templates).