# SPHEREx Sky-Viewer Frontend & Backend API Contract

This document specifies the communication protocol between the **Frontend** (`/frontend`) and Paul's **Backend** (`/backend` deployed on AWS Lightsail `35.159.162.202`).

---

## 1. Cutout Streaming Protocol: Server-Sent Events (SSE)

Because downloading large SPHEREx spectral image Multi-Extension FITS (MEF) cutouts from NASA/IPAC IRSA takes noticeable transfer time, the backend uses **Server-Sent Events (SSE)**. This allows the frontend to start rendering Epoch 1 immediately without waiting for subsequent epochs to finish downloading.

### 1.1 SSE Endpoint
- **URL**: `GET /api/cutouts/stream`
- **Headers**:
  - `Accept: text/event-stream`
- **Query Parameters**:
  - `ra` (float): Right Ascension in decimal degrees (e.g. `269.452075`)
  - `dec` (float): Declination in decimal degrees (e.g. `4.693365`)
  - `size` (float): Cutout box size in degrees (default `0.05`, equivalent to 3 arcminutes)
  - `collection` (string): IRSA collection (default `spherex_qr`)

---

### 1.2 SSE Stream Event Sequence

#### Event 1: `init` (Sent immediately upon connection)
Contains the total number of overlapping frames found in IRSA SIA for this coordinate.
```text
event: init
data: {"target": "Barnards_Star", "ra": 269.452075, "dec": 4.693365, "total_frames": 5, "fov_arcmin": 3.0}
```

#### Event 2..N: `frame` (Sent as each individual frame is cut out & calibrated)
```text
event: frame
data: {
  "frame_id": "SPX-L3-BARNARD-E1-A2",
  "epoch_index": 0,
  "date": "2025-06-15T04:12:00Z",
  "detector_array": 2,
  "wavelength_min_um": 1.11,
  "wavelength_max_um": 1.64,
  "is_available": true,
  "image_url": "/data/cutouts/Barnards_Star/SPX_E1_A2.png",
  "fits_url": "/data/cutouts/Barnards_Star/SPX_E1_A2.fits",
  "flagged_pixel_percentage": 0.42,
  "cosmic_ray_hits": 14,
  "header_metadata": {
    "exposure_time_sec": 142.5,
    "airmass": 1.0,
    "zodi_brightness_mjy_sr": 12.4,
    "snr_estimated": 26.2
  }
}
```

#### Event for Missing / Offline Detector Frame:
When a specific epoch lacks detector array coverage, send `is_available: false` with the `skip_reason`:
```text
event: frame
data: {
  "frame_id": "SPX-L3-BARNARD-E3-A4",
  "epoch_index": 2,
  "date": "2025-12-08T19:30:00Z",
  "detector_array": 4,
  "is_available": false,
  "skip_reason": "Detector Array 4 telemetry offline during downlink pass",
  "flagged_pixel_percentage": 100.0,
  "cosmic_ray_hits": 0
}
```

#### Event Final: `complete` (Sent after the last frame is dispatched)
```text
event: complete
data: {"status": "success", "processed_frames": 5}
```

---

## 2. Citizen Science Volunteer Triage Endpoint

### 2.1 Submit Candidate Verification
- **Endpoint**: `POST /api/candidates/triage`
- **Request Body**:
```json
{
  "candidate_id": "cand-barnard-primary",
  "ra": 269.452075,
  "dec": 4.693365,
  "classification": "moving_object",
  "confidence": "high",
  "volunteer_notes": "Clear proper motion dipole track across epochs 1-5. Matched to Gaia DR3.",
  "submitted_at_utc": "2026-11-14T09:40:00Z"
}
```

- **Allowed Classifications**:
  - `moving_object`: Proper motion / asteroid dipole
  - `transient`: Single-epoch flare or supernova
  - `already_known`: Verified catalog object (Gaia, WISE, NEO)
  - `artifact`: Cosmic ray hit or bad pixel cluster

---

## 3. URL Synchronization Contract for Embeds & Shares

The frontend synchronizes state directly to URL search parameters:
```
?ra=269.452075&dec=4.693365&fov=3'&detector=2&subtraction=raw_calibrated&frame=0
```
This enables sharing exact celestial coordinate views across volunteer forums and generating standard `<iframe>` embeds.
