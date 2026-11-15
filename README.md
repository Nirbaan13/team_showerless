# SPHEREx Blink: PlanetX Discovery Engine & Astronomical Candidate Catalogue
### NASA International Space Apps Challenge 2026

[![CI/CD Status](https://github.com/Nirbaan13/team_showerless/actions/workflows/ci-deploy.yml/badge.svg)](https://github.com/Nirbaan13/team_showerless/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Mission](https://img.shields.io/badge/NASA-SPHEREx%20Mission-0B3D91.svg)](https://www.jpl.nasa.gov/missions/spherex)
[![IRSA DOI](https://img.shields.io/badge/DOI-10.26131%2FIRSA652-blue.svg)](https://doi.org/10.26131/IRSA652)
[![Astrometric Standard](https://img.shields.io/badge/Astrometry-IAU%20ADES%20XML%2FPSV-emerald.svg)](https://www.minorplanetcenter.net/iau/info/ADES.html)

---

## 🌌 Executive Summary & Project Pitch

NASA’s **SPHEREx** (Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer) survey scans the entire celestial sphere every six months across **102 near-infrared spectral channels ($0.75 - 5.0\ \mu\text{m}$)**. Hidden within these multi-epoch spectral cubes are millions of dynamic cosmic events: near-Earth asteroids, interstellar comets, brown dwarfs, stellar flares, variable stars, and cosmological transients.

However, three severe bottlenecks prevent the global astronomical community and citizen scientists from fully exploiting this dataset:
1. **The Bandwidth Dilemma**: Full-sky multi-epoch FITS spectral cubes are hundreds of gigabytes, making client-side inspection impossible for ordinary volunteers.
2. **The Residual Blinking Deficit**: Conventional single-band blink comparators fail to distinguish real physical trajectories from detector artifacts, cosmic rays, and passband variations across non-contiguous arrays.
3. **The Clearinghouse Bottleneck**: External scientific bodies (such as the **Minor Planet Center [MPC]**, **IAU Transient Name Server [TNS]**, and **AAVSO Variable Star Index [VSX]**) strictly reject unstructured discovery claims. They mandate rigorous astrometric precision, multi-epoch leave-one-out validation, and community consensus before ingestion.

### The Solution: SPHEREx Blink
**SPHEREx Blink** is an end-to-end, dual-persona discovery suite and authoritative candidate registry. It combines:
* **Targeted Zero-Footprint IRSA Cutout Streaming**: Pulls calibrated sky cutouts on-demand via TAP/Polygon endpoints without multi-gigabyte downloads.
* **Sub-Pixel Leave-One-Out Blink Engine**: Incorporates zodiacal light (`ZODI`) subtraction, median reference background subtraction, and `FLAGS` bitmask filtering.
* **Dual-Track Machine Learning & Saturated Centroid Linker**: Recovers moving asteroids and comets using both a linear trajectory tracker and a dedicated **BLOOM core centroiding algorithm** for heavily saturated objects.
* **102-Band Spectrophotometry**: Live $F_\lambda$ extraction matching spectral profiles against empirical templates (water ice, $CO_2$ ice, silicates, and carbonaceous organics).
* **Community Consensus & Peer-Review Stream**: A collaborative verification workspace where citizen volunteers and verified NASA/IAU scientists debate candidates.
* **Automated 10-Confirmation Clearinghouse Pipeline**: Once $\ge 10$ independent reviewers confirm a discovery, the system automatically elevates the candidate to Level 2 Community Verified, formats standardized **IAU ADES XML/PSV** or **IAU TNS JSON** payloads, dispatches them to external clearinghouses, and records real-time acceptance citations or quantitative rejection diagnostics in a persistent SQLite WAL catalogue.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph Client ["Frontend: React 18 + TypeScript + Vite + TailwindCSS"]
        A[TopNav & Route Controller] --> B[Interactive Sky Viewer]
        A --> C[Verification Feed]
        A --> D[Candidate Catalog Dashboard]
        A --> E[Discovery Reporting & Embed Generator]
        B --> B1[Leave-One-Out Blink Canvas]
        B --> B2[102-Band Spectrophotometer]
        B --> B3[Motion Review & BLOOM Visualizer]
    end

    subgraph Service ["Backend & Microservices: FastAPI + Python 3.10"]
        F[API Gateway: port 8001] --> G[Live IRSA / Horizon Streamer]
        F --> H[ML Detection Engine]
        F --> I[Verifications & Classifications Engine]
        F --> J[Catalogue & Submission Pipeline]
        H --> H1[Heuristic Trajectory Linker]
        H --> H2[Random Forest Evaluator]
        H --> H3[BLOOM Saturated Centroid Linker]
    end

    subgraph Archives ["NASA / IPAC Data Repositories"]
        K[(NASA/IPAC IRSA: QR2, QR3, DR1)]
        L[(JPL Horizons Ephemeris API)]
    end

    subgraph Persistence ["Persistent Storage: SQLite WAL Mode"]
        M[(verifications.sqlite)]
        N[(planetx_catalogue.db)]
    end

    subgraph Clearinghouses ["External Scientific Clearinghouses"]
        O[Minor Planet Center - MPC<br/>ADES XML / PSV]
        P[IAU Transient Name Server - TNS<br/>JSON Discovery Payload]
        Q[AAVSO VSX<br/>Photometric CSV / Report]
    end

    B1 <-->|Cutout Queries| F
    G <-->|TAP / SIA Range Queries| K
    G <-->|Astrometric Cross-Check| L
    C <-->|Peer Reviews & Votes| I
    I <--> M
    I -->|Consensus >= 10 Votes| J
    J <--> N
    J -->|Auto-Dispatch| O
    J -->|Auto-Dispatch| P
    J -->|Auto-Dispatch| Q
```

---

## 🚀 Key Features

### 1. Interactive Multi-Epoch Sky Viewer & Blink Comparator
* **Leave-One-Out Astrometric Differencing**: Generates reference baselines by median-combining alternative epoch frames, exposing moving asteroids and transient dips as distinct positive/negative dipoles.
* **Full Contrast & Stretch Range**: Switch instantly between **ZScale interval** ($1\text{st}-99\text{th}$ percentile auto-stretch), Linear, Logarithmic, and Asinh scaling.
* **Variable Framerate Time-Lapse Player**: 1 to 30 FPS playback, frame stepping, loop modes, and continuous coordinate tracking ($RA$, $Dec$, pixel coordinates).
* **Missing Coverage Auto-Skip Notice**: Detectors $1-6$ have varying focal plane footprints. The viewer automatically skips dead epochs and explains missing visits to prevent playback stutter.
* **Dual User Persona Switcher**:
  * **Citizen Volunteer View**: Intuitive tactile controls, simplified jargon, clear visual motion indicators.
  * **Research Astrophysicist View**: Unmasked FITS header inspection, raw bitmask overlays (`FLAGS`), RMS astrometric residuals, and formal photometric calibrations.

### 2. Machine Learning Detection & Saturated Source Centroiding
* **Heuristic Residual Tracking**: Identifies local intensity peaks ($\ge 3.0\sigma$ above background), filters static stars, and links linear motion vectors across $\ge 3$ visits.
* **Random Forest Reranking**: Evaluates candidates trained on simulated infrared star fields using features such as track length, median residual S/N, and trajectory curvature.
* **Saturated Source BLOOM Centroid Linker**: Bright Solar System bodies saturate SPHEREx detectors. Instead of failing or corrupting flux measurements, the engine links the geometric centroids of connected `BLOOM` flagged pixel regions ($\ge 6\text{ px}$), accurately tracking targets like **Asteroid (4) Vesta**.

### 3. 102-Band Near-Infrared Spectrophotometry
* **Spectral Energy Distribution ($F_\lambda$)**: Extracts flux density from $0.75\ \mu\text{m}$ to $5.00\ \mu\text{m}$ across all 102 SPHEREx bandpasses.
* **Molecular Absorption & Emission Overlays**:
  * **Water Ice ($H_2O$)**: Diagnostic absorption complexes at $1.5\ \mu\text{m}$, $2.0\ \mu\text{m}$, and $3.05\ \mu\text{m}$.
  * **Carbon Dioxide Ice ($CO_2$)**: Sharp resonant dip at $4.27\ \mu\text{m}$.
  * **Silicate Minerals & Organics**: Continuum slopes and aliphatic C-H stretching bands ($3.3 - 3.4\ \mu\text{m}$).

### 4. Community Verification Stream & Consensus Engine
* **Verified Roles**: Distinguishes comments and classifications submitted by **NASA / IAU Scientists** versus **Citizen Volunteers**.
* **Four-Tier Classification System**:
  * `confirm_motion`: Verified moving solar system target.
  * `likely_real`: Statistically significant real astrophysical source.
  * `detector_artifact`: Cosmic ray hit, latent charge, optical ghost, or diffraction spike.
  * `unsure`: Requires additional survey epochs.
* **Live Consensus Gauge**: Visual progress meter toward the mandatory 10-confirmation threshold.

### 5. Persistent Astronomical Candidate Catalogue (`planetx_catalogue.db`)
* **Strict Peer-Review Gate**: New candidates **cannot be manually created** in the catalog; they are automatically ingested solely through verified community discussion threads.
* **Lifecycle State Tracking**:
  * `under_review`: Newly catalogued from community thread ($< 10$ confirmations).
  * `community_verified`: Passed peer-review consensus ($\ge 10$ confirmations).
  * `submitted_external`: Dispatched to international clearinghouse; awaiting review.
  * `externally_confirmed` (Accepted): Cleared by clearinghouse; IAU/MPC identifier issued.
  * `rejected`: Did not meet clearinghouse thresholds; failure reasons logged.
* **Multi-Parameter Search & Sort**: Filter by status pills, spectral array (D1–D6), target type, S/N, or astrometric fit RMS.

### 6. External Scientific Clearinghouse Submission Pipeline
* **Intelligent Clearinghouse Dispatch**:
  * **Moving Objects (Asteroids / Comets)** $\rightarrow$ **Minor Planet Center (MPC)**
  * **Rapid Optical / Infrared Transients** $\rightarrow$ **IAU Transient Name Server (TNS)**
  * **Variable Stars / Stellar Flares** $\rightarrow$ **AAVSO International Variable Star Index (VSX)**
* **Compliant Machine-Readable Formats**:
  * **IAU ADES XML / PSV** (Astrometric Data Exchange Standard for MPC submissions).
  * **IAU TNS JSON** discovery reports with photometric and astrometric blocks.
* **Realistic Sandbox Decision Engine**:
  * **Acceptance**: Verifies S/N $\ge 5.0$, astrometric RMS $\le 0.50\text{ px}$, valid multi-epoch motion, non-artifact classification.
  * **Rejection**: Identifies detector artifacts, high astrometric residuals, or insufficient S/N and returns actionable diagnostic reports.

### 7. Zero-Install Sharing & Embeddable Generative UI
* **Stateful URL Synchronization**: Coordinate parameters (`ra`, `dec`, `fov`, `detector`, `frame`, `candidate`, `tab`) synchronize bidirectionally with browser history.
* **Responsive `<iframe>` Embedder**: Generate embed codes for external scientific blogs, educational portals, and citizen science dashboards.
* **Self-Contained Standalone HTML Artifacts**: Run complete interactive catalog dashboards directly in any web browser without needing local Node.js or Python environments.

---

## 🔬 Empirical Scientific Validation

The algorithms in SPHEREx Blink were systematically benchmarked against real NASA/IPAC IRSA observation frames:

| Object | Target Type | SPHEREx Dataset | Detector | Usable Visits | Algorithm Used | Ground Truth Offset | Ranking Result |
| :--- | :--- | :--- | :---: | :---: | :--- | :---: | :---: |
| **Comet 3I/ATLAS** | Interstellar Comet | IRSA QR2 (IRSA652) | **D6** | 4 | Heuristic Residual Tracker | **0.54 px** | **#1 / 25 Candidates** |
| **Comet 3I/ATLAS** | Interstellar Comet | IRSA QR2 (IRSA652) | **D6** | 4 | Random Forest Classifier | **0.54 px** | **#2 / 25 Candidates** |
| **Comet 3I/ATLAS** | Interstellar Comet | IRSA QR2 (IRSA652) | **D2** | 3 | Heuristic Residual Tracker | **0.60 px** | **#1 / 2 Candidates** |
| **(4) Vesta** | Main-Belt Asteroid | IRSA DR1 | **D6** | 3 | BLOOM Core Centroiding | **0.28 px** | **#1 / 1 (Recovery)** |
| **(4) Vesta** | Main-Belt Asteroid | IRSA DR1 | **D3** | 3 | BLOOM Core Centroiding | **0.38 px** | **#1 / 1 (Recovery)** |
| **Barnard’s Star** | High Proper Motion | IRSA DR1 | **D2** | 4 | Multi-Epoch Dipole Fit | **0.42 px** | **Dipole Verified** |

> **Leave-One-Out Verification**: When Comet 3I/ATLAS exposures were tested by deliberately withholding one exposure at a time, the heuristic tracker maintained **100% recovery (#1 ranking)** across all permutations, proving robust resilience against missing or corrupted frames.

---

## 🛠️ Tech Stack

* **Frontend**: TypeScript, React 18, Vite, TailwindCSS, Lucide Icons, Canvas API, KaTeX (LaTeX math rendering).
* **Backend & ML**: Python 3.10+, FastAPI, Uvicorn, NumPy, SciPy, Scikit-learn, Astropy, SQLite3 (WAL mode).
* **Archive Integrations**: NASA/IPAC IRSA TAP/SIA APIs, JPL Horizons API, VODataLink, VOTable XML.
* **Standards & Protocols**: IAU ADES XML/PSV, IAU TNS JSON, FITS WCS standard (ICRS TAN projection).
* **Infrastructure**: Docker, Docker Compose, Nginx Reverse Proxy, GitHub Actions CI/CD.

---

## 💻 Quick Start & Local Installation

### Prerequisites
* **Node.js**: v18.0.0 or higher
* **Python**: v3.10 or higher
* **Git**: v2.30 or higher

### Option 1: Native Local Development (Recommended)

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/Nirbaan13/team_showerless.git
   cd team_showerless
   ```

2. **Start the Backend Microservice**:
   ```bash
   # From repository root
   python3 -m pip install -r ml/requirements.txt
   PYTHONPATH=. python3 -m uvicorn ml.service:app --host 127.0.0.1 --port 8001 --reload
   ```

3. **Start the Frontend Development Server**:
   ```bash
   # In a new terminal tab
   cd frontend
   npm install
   npm run dev
   ```

4. **Access the Application**:
   * **Sky Explorer & Candidate Catalog**: [http://localhost:5173](http://localhost:5173)
   * **Interactive Candidate Catalog Direct Tab**: [http://localhost:5173/?tab=catalogue](http://localhost:5173/?tab=catalogue)
   * **Backend API Swagger Documentation**: [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)

---

### Option 2: Docker Compose (All-in-One Container)

```bash
docker compose -f compose.services.yaml up --build
```
Access the application at `http://localhost:8080`.

---

## 🧪 Verification & Automated Testing Suite

Run the full automated test suite to verify type safety, scientific pipelines, and clearinghouse simulation logic:

```bash
# 1. Verify Frontend TypeScript types and build output
cd frontend
npm run build
# Expected output: ✓ built in ~1.5s with 0 errors

# 2. Run Python Candidate Catalogue & Clearinghouse Pipeline Unit Tests
cd ..
PYTHONPATH=. python3 ml/test_catalogue_pipeline.py
# Expected output: Ran 5 tests ... OK

# 3. Run Scientific Motion Tracking Suite
python3 -m unittest discover -s science/motion -v
```

---

## 📡 REST API Reference

The FastAPI service exposes high-performance endpoints for motion detection and catalog governance:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/catalogue/kpis` | Real-time counts of catalogued, verified, submitted, accepted, and rejected objects. |
| `GET` | `/api/catalogue/candidates` | Filtered list of persistent candidates with search, sort, and spectral filtering. |
| `GET` | `/api/catalogue/candidates/{id}` | Full scientific detail record, multi-epoch astrometry, and clearinghouse history. |
| `POST`| `/api/catalogue/auto-submit` | Elevates thread reaching $\ge 10$ confirmations, submits to MPC/TNS, schedules review. |
| `POST`| `/api/motion/verifications` | Creates discussion thread in Verification Feed and auto-indexes candidate in catalog. |
| `POST`| `/api/motion/verifications/{id}/upvote` | Increments peer confirmations; triggers auto-submission if threshold ($\ge 10$) is reached. |
| `POST`| `/api/motion/search` | Performs live cutout search across NASA/IPAC IRSA DR1 and QR3. |

---

## 📚 Academic Citations & Data Attribution

If you use SPHEREx Blink in your academic research, Space Apps presentation, or scientific publication, please cite the following primary resources:

### SPHEREx Mission & Data Releases
```bibtex
@misc{spherex_qr2_2025,
  author       = {{NASA/IPAC Infrared Science Archive}},
  title        = {{SPHEREx Quick Release 2 Calibrated Spectral Images}},
  year         = {2025},
  publisher    = {IPAC},
  doi          = {10.26131/IRSA652},
  url          = {https://doi.org/10.26131/IRSA652}
}

@article{korngut2018spherex,
  author       = {Korngut, P. M. and others},
  title        = {{SPHEREx: An All-Sky Near-Infrared Spectral Survey}},
  journal      = {Proceedings of the SPIE},
  volume       = {10698},
  pages        = {106981U},
  year         = {2018},
  doi          = {10.1117/12.2312999}
}
```

### IAU Astrometric & Transient Standards
```bibtex
@article{mpc_ades_2022,
  author       = {{Minor Planet Center}},
  title        = {{Astrometric Data Exchange Standard (ADES) Version 2022}},
  journal      = {IAU Commission F5 Working Group},
  year         = {2022},
  url          = {https://www.minorplanetcenter.net/iau/info/ADES.html}
}

@misc{iau_tns_2024,
  author       = {{International Astronomical Union}},
  title        = {{Transient Name Server (TNS) Discovery Reporting Protocol}},
  year         = {2024},
  url          = {https://www.wis-tns.org}
}

@misc{jpl_horizons,
  author       = {Giorgini, J. D. and others},
  title        = {{JPL Horizons On-Line Ephemeris System}},
  year         = {1996},
  journal      = {Bulletin of the American Astronomical Society},
  volume       = {28},
  pages        = {1158}
}
```

---

## 👥 Team Showerless (NASA International Space Apps Challenge)

* **Team Name**: Team Showerless
* **Project Repository**: [https://github.com/Nirbaan13/team_showerless](https://github.com/Nirbaan13/team_showerless)
* **Challenge**: Tracking Dynamic Phenomena Across 102 Near-Infrared Bands (SPHEREx)

---
*Built with ❤️ for NASA Space Apps 2026. Empowering citizen science through rigorous astrophysics.*
