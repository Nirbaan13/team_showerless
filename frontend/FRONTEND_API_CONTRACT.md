# SPHEREx Sky-Viewer Frontend API Contract & Architecture

This document specifies the TypeScript interfaces, REST/WebSocket API endpoints, and expected JSON payloads connecting the frontend (`/frontend`) with:
1. **Backend Cutout Service** (`/api/cutouts`)
2. **Background Subtraction Pipeline** (`/api/subtraction`)
3. **ML Candidate Detection & Triage Pipeline** (`/api/candidates`)
4. **102-Band Spectrophotometry Service** (`/api/spectra`)

---

## 1. Celestial Coordinate & Query Parameters

### 1.1 Sky Query Endpoint
- **HTTP Method**: `GET /api/cutouts`
- **Description**: Retrieves multi-epoch FITS cutout metadata and calibrated image slices for a celestial bounding box.

#### Query Parameters:
| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `ra` | `number` (float) | Yes | — | Right Ascension in decimal degrees ($0^\circ \le \text{RA} < 360^\circ$) |
| `dec` | `number` (float) | Yes | — | Declination in decimal degrees ($-90^\circ \le \text{Dec} \le +90^\circ$) |
| `fov_arcmin` | `number` (float) | No | `3.0` | Field of view size in arcminutes (`1.0`, `3.0`, `5.0`, `10.0`) |
| `detector_array` | `integer` (1–6) or `"all"` | No | `"all"` | SPHEREx detector array (1 to 6) or stacked arrays |
| `channel_index` | `integer` (1–102) | No | `null` | Single discrete wavelength channel (1 to 102) |
| `subtraction_mode` | `string` | No | `"raw_calibrated"` | Subtraction state: `raw_calibrated`, `zodi_reference_subtracted`, `epoch_difference` |

#### Success Response (`200 OK`):
```json
{
  "query": {
    "ra": 269.452075,
    "dec": 4.693365,
    "fov_arcmin": 3.0,
    "detector_array": 2,
    "subtraction_mode": "raw_calibrated",
    "timestamp_utc": "2026-11-14T08:50:00Z"
  },
  "total_epochs": 5,
  "available_epochs": 4,
  "frames": [
    {
      "frame_id": "SPX-L3-BARNARDS-STAR-E1-A2",
      "epoch_index": 0,
      "observation_date": "2025-06-15T04:12:00Z",
      "detector_array": 2,
      "wavelength_min_um": 1.11,
      "wavelength_max_um": 1.64,
      "channel_index": 18,
      "flagged_pixel_percentage": 0.45,
      "cosmic_ray_hits": 14,
      "is_available": true,
      "image_url": "/static/cutouts/spx_269.452_4.693_e1_a2.png",
      "fits_cutout_url": "/api/fits/download?id=SPX-L3-BARNARDS-STAR-E1-A2",
      "header_metadata": {
        "exposure_time_sec": 142.5,
        "airmass": 1.0,
        "zodi_brightness_mjy_sr": 12.4,
        "snr_estimated": 26.2
      }
    },
    {
      "frame_id": "SPX-L3-BARNARDS-STAR-E3-A4",
      "epoch_index": 2,
      "observation_date": "2025-12-08T19:30:00Z",
      "detector_array": 4,
      "wavelength_min_um": 2.42,
      "wavelength_max_um": 3.82,
      "flagged_pixel_percentage": 100.0,
      "cosmic_ray_hits": 0,
      "is_available": false,
      "skip_reason": "Detector Array 4 telemetry offline during downlink pass",
      "header_metadata": {
        "exposure_time_sec": 0.0,
        "airmass": 1.0,
        "zodi_brightness_mjy_sr": 0.0,
        "snr_estimated": 0.0
      }
    }
  ]
}
```

---

## 2. Subtraction Pipeline Integration

### 2.1 Subtraction Execution Endpoint
- **HTTP Method**: `POST /api/subtraction/apply`
- **Description**: Requests on-demand zodiacal light reference subtraction or multi-epoch differential processing.

#### Request Payload:
```json
{
  "target_frame_id": "SPX-L3-BARNARDS-STAR-E2-A2",
  "reference_frame_id": "SPX-L3-BARNARDS-STAR-E1-A2",
  "method": "epoch_difference",
  "kernel_alignment": "wcs_psf_matched",
  "clip_cosmic_rays": true
}
```

#### Response (`200 OK`):
```json
{
  "status": "completed",
  "result_frame_id": "DIFF-SPX-E2-E1-A2",
  "difference_image_url": "/static/diff/diff_e2_e1_a2.png",
  "median_residual_flux": 0.04,
  "noise_sigma": 0.12,
  "transient_candidates_detected": 1
}
```

---

## 3. Machine Learning & Candidate Triage API

### 3.1 Candidate Detection Endpoint
- **HTTP Method**: `GET /api/candidates`
- **Description**: Fetches candidate transients and high proper motion objects identified within the cutout area.

#### Query Parameters:
- `ra`: Target RA
- `dec`: Target Dec
- `radius_arcmin`: Search radius (default `3.0`)
- `min_snr`: Minimum detection signal-to-noise ratio (default `5.0`)

#### Response Payload:
```json
{
  "candidates": [
    {
      "id": "cand-barnard-primary",
      "ra": 269.452075,
      "dec": 4.693365,
      "pixel_x": 250,
      "pixel_y": 250,
      "classification": "moving_object",
      "confidence": "high",
      "is_known_catalog_match": true,
      "matched_catalog": "Gaia DR3",
      "catalog_id": "Gaia DR3 4472832130942575872",
      "proper_motion_mas_yr": {
        "pm_ra": -802.8,
        "pm_dec": 10362.5
      },
      "epoch_positions": [
        { "epoch_index": 0, "x": 235, "y": 240, "flux": 142.0, "snr": 38.2 },
        { "epoch_index": 1, "x": 242, "y": 245, "flux": 141.5, "snr": 37.9 },
        { "epoch_index": 2, "x": 250, "y": 250, "flux": 143.1, "snr": 38.0 },
        { "epoch_index": 3, "x": 258, "y": 255, "flux": 140.8, "snr": 37.4 },
        { "epoch_index": 4, "x": 265, "y": 260, "flux": 142.9, "snr": 38.5 }
      ]
    }
  ]
}
```

### 3.2 Volunteer Triage Submission Endpoint
- **HTTP Method**: `POST /api/candidates/triage`
- **Description**: Submits volunteer verification decisions back to the team's database and ML retraining pipeline.

#### Request Payload:
```json
{
  "candidate_id": "cand-barnard-primary",
  "classification": "moving_object",
  "confidence": "high",
  "volunteer_notes": "Clear proper motion dipole track across all epochs. Matched to Gaia DR3.",
  "submitted_at_utc": "2026-11-14T08:52:10Z",
  "client_metadata": {
    "viewport_zoom": 1.4,
    "subtraction_mode_used": "epoch_difference"
  }
}
```

#### Response (`201 Created`):
```json
{
  "status": "success",
  "message": "Candidate classification stored successfully",
  "candidate_id": "cand-barnard-primary",
  "consensus_votes": {
    "moving_object": 8,
    "artifact": 0,
    "transient": 1
  }
}
```

---

## 4. 102-Band Spectrophotometry API

### 4.1 Spectrum Retrieval Endpoint
- **HTTP Method**: `GET /api/spectra`
- **Description**: Queries calibrated spectrophotometry across SPHEREx's 102 bands ($0.75 - 5.00\,\mu\text{m}$) for a designated point source.

#### Response Payload:
```json
{
  "candidate_id": "cand-barnard-primary",
  "spectral_points": [
    {
      "channel": 1,
      "wavelength_um": 0.75,
      "flux_mjy": 24.3,
      "uncertainty_mjy": 1.2,
      "detector_array": 1
    },
    {
      "channel": 52,
      "wavelength_um": 3.05,
      "flux_mjy": 11.2,
      "uncertainty_mjy": 0.8,
      "detector_array": 4
    }
  ],
  "atmospheric_model_fit": {
    "model_name": "BT-Settl-CIFIST",
    "effective_temperature_k": 3100,
    "log_g": 5.0,
    "metallicity": -0.3,
    "reduced_chi_squared": 1.18
  }
}
```

---

## 5. URL Query Parameter Synchronization Contract

Any deep link or `<iframe>` embed will adhere to the following URL pattern:
```
https://[domain]/?ra=[FLOAT]&dec=[FLOAT]&fov=[FOV]&detector=[ARRAY]&subtraction=[MODE]&frame=[INT]
```
- Example:
  `https://spherex-skyviewer.org/?ra=269.452075&dec=4.693365&fov=3'&detector=2&subtraction=raw_calibrated&frame=0`

---

## 6. Frontend TypeScript Interfaces

All shared TypeScript types are housed in `/frontend/src/types/spherex.ts`:
- `DetectorArrayId`: `1 | 2 | 3 | 4 | 5 | 6`
- `SubtractionMode`: `'raw_calibrated' | 'zodi_reference_subtracted' | 'epoch_difference'`
- `CandidateClassification`: `'moving_object' | 'transient' | 'already_known' | 'artifact' | 'unreviewed'`
- `ConfidenceLevel`: `'low' | 'medium' | 'high'`
- `FOVOption`: `"1'" | "3'" | "5'" | "10'"`
- `SpherexEpochFrame`, `CandidateObject`, `SpectralDataPoint`, `MolecularLine`, `CatalogOverlayState`
