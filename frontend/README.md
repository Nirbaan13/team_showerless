# Running the SPHEREx Sky-Viewer Frontend

This frontend is a modern React + TypeScript + Vite web app built with Tailwind CSS.

## 🚀 Run in 1 Command (Anyone on the team or GitHub)

From the root of the repository:

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:5173` in your browser.

---

## 📦 Production Build

To produce an optimized production bundle:

```bash
cd frontend
npm run build
npm run preview
```

---

## 🌌 Core Features

1. **Top Bar**: NASA test presets (Barnard's Star, WISE 0855, Epsilon Indi B, etc.), direct URL synchronization, and iframe embed snippet generator.
2. **Left Panel**: RA/Dec inputs, FOV size selector with estimated IRSA data transfer size, detector array selector (Bands 1–6), background subtraction modes, and catalog overlays (Gaia DR3, WISE, Asteroids).
3. **Center Viewport**: WorldWideTelescope-inspired celestial canvas with mouse pan/zoom, live cursor coordinates (HMS/DMS), and reticle overlays.
4. **Blink Timeline**: Multi-epoch playback with FPS controls and resilient skip handling for offline detector array frames.
5. **Right Drawer**: Data health telemetry (% flagged pixels, cosmic rays), 102-band continuous spectrum plot ($0.75 - 5.00\,\mu\text{m}$) with molecular absorption lines ($H_2O, CO_2, CO$), and 1-click citizen science triage.
