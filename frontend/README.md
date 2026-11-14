# SPHEREx Sky-Viewer — Citizen Science & Candidate Discovery

Modern, editorial celestial viewer and candidate triage tool built for the **NASA Space Apps Challenge ("Planet X and SPHEREx")**. 

Designed to process multi-epoch infrared sky cutouts across SPHEREx's 102 spectrophotometric channels ($0.75 - 5.00\,\mu\text{m}$), enabling volunteers and researchers to blink epochs, spot moving objects (brown dwarfs, Planet 9 candidates, asteroids), flag transients (supernovae, variable stars), and export verified discovery reports.

---

## Quick Start for Teammates

### 1. Clone & Run Locally
```bash
git clone https://github.com/Nirbaan13/team_showerless.git
cd team_showerless/frontend
npm install
npm run dev
```
Open **[http://localhost:5173](http://localhost:5173)** in your browser.

### 2. Production Build
```bash
npm run build
```
Build output is saved to `frontend/dist/`.

---

## Backend Integration & OpenAPI Alignment

The frontend is aligned with Paul's OpenAPI 3.1.0 specification at [`backend/docs/openai/openapi.yaml`](../backend/docs/openai/openapi.yaml):

- **Archive Search**: `POST /api/observations/search`
- **Data Preparation Modes**:
  - `GET /api/observations/default` (Calibrated)
  - `GET /api/observations/zodi-reference-subtracted` (Zodiacal light subtracted)
  - `GET /api/observations/epoch-difference?reference_frame_id=...` (Temporal difference)
- **Asynchronous SSE Streaming**:
  - `GET /api/downloads/{id}/events` — streams realtime `chunk.ready`, `preview.ready`, and `job.completed` events
- **Previews & FITS**:
  - `GET /api/chunks/{id}/preview` (rendered PNG)
  - `GET /api/chunks/{id}` (FITS binary)

Client service implementation: [`frontend/src/services/spherexBackendApi.ts`](./src/services/spherexBackendApi.ts).

---

## Key Features

1. **Editorial Minimalist Interface**: Clean typography, high contrast, warm cream and charcoal palette (`#0a0a0c`, `#121216`, `#f4f1ea`, `#d97706`).
2. **Central Search Landing Page**: Fast coordinate search bar with instantaneous 1-click NASA benchmark targets (*Barnard's Star*, *Epsilon Indi B*, *WISE 0855*, *RW Aurigae*, *R Draconis*).
3. **High-Performance Celestial Canvas**: HTML5 canvas rendering with inertial panning, zoom easing, telescope crosshairs, and 30″ angular scale bar.
4. **Multi-Epoch Movie Player**: Variable frame rates (1–10 fps), pause/play, frame stepper, and missing-array skipping.
5. **Expandable Peer Cross-Verification Chat**: Collapsible/expandable side panel for multi-user triage discussion with verified tags (`Verified Motion`, `Needs Review`, `Artifact`, `Catalog Match`).
6. **102-Band Spectrophotometry**: Interactive spectral energy distribution ($0.75 - 5.00\,\mu\text{m}$) with highlighted molecular lines ($\text{SiO}_4$, $\text{H}_2\text{O}$, $\text{CO}_2$, $\text{CO}$).
7. **Candidate Discovery Report**: Complete summary containing coordinates, proper motion vectors, catalog match checks (Gaia DR3 / WISE), and JSON export.
