# 🚀 SPHEREx Time-Domain Sky Explorer

[![NASA Space Apps Challenge](https://img.shields.io/badge/NASA_Space_Apps-2026-0B3D91?style=for-the-badge&logo=nasa&logoColor=white)](https://www.spaceappschallenge.org/)
[![Status](https://img.shields.io/badge/Status-Active_Hackathon_Build-success?style=for-the-badge)]()
[![Stack](https://img.shields.io/badge/Stack-TypeScript_%7C_FastAPI_%7C_Docker-3178C6?style=for-the-badge)]()

> **A public-facing web tool that transforms NASA SPHEREx near-infrared sky cutouts into aligned, noise-cleaned time-lapse movies—empowering anyone to spot moving objects and cosmic transients over time.**

---

## 🌌 Challenge & Problem Statement

> *"Since 2025, NASA’s SPHEREx mission has been mapping the entire sky every six months in 102 bands of near-infrared light, returning images of more than a billion objects. Comets, asteroids, stars, brown dwarfs, and even new planets reveal themselves by shifting position between images, but no one person can sift through all that data alone. Your challenge is to create a public-facing web tool to display images of the sky from SPHEREx mission, making it easy for anyone to quickly see how they change over time."*

### Our Solution
Instead of forcing users to download massive FITS archives, **SPHEREx Time-Domain Sky Explorer** queries targeted sky cutouts directly from NASA/IRSA, subtracts background zodiacal light, masks cosmic rays/bad pixels, and animates multi-epoch frames into an interactive celestial movie.

---

## 🏗️ Repository Architecture

| Directory / File | Tech Stack | Role & Current Status |
| :--- | :--- | :--- |
| **`/frontend`** | TypeScript, CSS, HTML (`~89%`) | Interactive sky viewer, timeline controls, and offline auto-fallback (`ebe181f`). |
| **`/backend`** | Python, FastAPI (`~3.5%`) | Range & polygon observation endpoints for targeted IRSA/SPHEREx queries (`5e29a49`). |
| **`/ops` & `compose.yaml`** | Docker, Shell (`~6%`) | Containerized environment for local and cloud deployment. |
| **`.github/workflows`** | GitHub Actions | Automated CI/CD pipeline deploying directly from `main` to VPS (`a29e044`). |

---

## 📋 Feature Roadmap & Outline Tracker

*Team members: Check off items (`[x]`) directly in GitHub as features are merged into `main`.*

### I. Coordinate Input & Target Selection
- [x] **Area & Polygon Selection:** Backend endpoints support range and polygon observation queries.
- [ ] **Preset NASA Benchmark Targets:** One-click buttons for NASA's test coordinates:
  - **Barnard’s Star:** `RA 17h 57m 48.498s` | `Dec +04° 41′ 36.1139″`
  - **Epsilon Indi B:** `RA 22h 04m 10.595s` | `Dec −56° 46′ 58.239″`
  - **WISE 0855:** `RA 08h 55m 10.831s` | `Dec −07° 14′ 42.53″`
  - **Variable / Transient Stars:** `RW Aurigae` and `R Draconis`
- [ ] **Known Object Cross-Check:** Query external catalogs at observation timestamps to flag known objects vs. new moving candidates (retaining manual human confirmation).

### II. NASA Archive & Data Optimization
- [x] **Targeted Cutouts (No Full-File Downloads):** Query specific regions via IRSA / SPXQuery without downloading full-sky FITS files.
- [ ] **Grouping & Caching:** Organize cutouts by observation date and detector array (`1–6`); cache coordinate queries for rapid repeat playback.

### III. Image Alignment & Time-Lapse Movie Engine
- [ ] **Background & Noise Subtraction:** Subtract Zodiacal light (`ZODI`) model $\rightarrow$ subtract median reference sky $\rightarrow$ mask bad pixels and cosmic rays via `FLAGS`.
- [ ] **Missing Detector Resilience:** Gracefully skip missing frames when a sky coordinate lacks coverage across all 6 SPHEREx detector arrays.
- [ ] **Playback Controls:** Play, pause, scrub frames, and filter by observation date.

### IV. UI/UX, Sharing & Data Transparency
- [x] **Live Demo Resilience:** Offline auto-fallback implemented in `/frontend` to prevent crashes during API timeouts.
- [ ] **Minimalist UI & Smooth Zoom:** Clean aesthetic (inspired by *GoBitsNBytes* & *Zooniverse*) with smooth celestial zooming (*WorldWide Telescope* style).
- [ ] **Share & Embed Links:** URL state encoding (`RA`, `Dec`, area size, detector, frame) + one-click `<iframe />` embed snippet.
- [ ] **Data Health Panel:** Display per-frame metadata (date, detector, wavelength band, `%` flagged pixels) and explain skipped frames.

### V. Stretch Goals (102-Band Spectroscopy & ML)
- [ ] **102-Band Spectral Plotter:** Extract flux vs. wavelength (`WCS-WAVE` extension) for user-selected moving objects.
- [ ] **Material & Anomaly Classification:** Compare extracted spectra against carbon, silicate, and water-ice templates (Random Forest / Autoencoder).

---

## 🤝 Team & Workflow

* **Team Members:** Nirbaan Singh (`@Nirbaan13`), Usatov Pavel (`@UsatovPavel`), SB321 (`@ShastaEdmundson`)
* **Updating This Document:** Click the **Edit (`✏️`)** icon in the top-right corner of this file on GitHub whenever you complete a feature or push a major update so the whole team stays synced.

<details>
<summary><b>🕒 Recent Development Changelog (Click to expand)</b></summary>

- **`ebe181f`** — Added offline auto-fallback to `/frontend` to guarantee site uptime during demos.
- **`5e29a49`** — Documented range and polygon observation endpoints in `/backend`.
- **`6d30d90`** — Moved service into `/backend` and marked generated documentation.
- **`a29e044`** — Bootstrapped FastAPI CI, Docker Compose, and automatic VPS deployment from `main`.
</details>