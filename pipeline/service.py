import base64
import hashlib
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.visualization import ZScaleInterval
from fastapi import FastAPI, HTTPException, Query as ApiQuery
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from PIL import Image
from pydantic import BaseModel

from spherex.cleaning import load_clean_cutout
from spherex.query import DEFAULT, cutout, image_search
from scripts.spectra import extract_spectrum, measure_cutout_point

app = FastAPI(
    title="SPHEREx IRSA Cutout & Preprocessing Worker",
    version="1.0.0",
    description="Scientific image cutout, Zodi subtraction, ZScale stretch, and 102-band spectrophotometry worker",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

CUTOUT_CACHE_DIR = Path("/tmp/spherex_cutouts")
CUTOUT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class CutoutRequest(BaseModel):
    ra: float
    dec: float
    size_arcmin: float = 3.0
    collection: str = DEFAULT
    detector_array: Optional[int] = None


class SpectrumRequest(BaseModel):
    ra: float
    dec: float
    radius_pix: float = 2.0
    cutout_paths: Optional[List[str]] = None


def array_to_png_bytes(data: np.ndarray) -> bytes:
    """Apply ZScaleInterval stretch and convert 2D float array to grayscale PNG bytes."""
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        norm = np.zeros_like(data, dtype=np.uint8)
    else:
        lo, hi = ZScaleInterval().get_limits(finite)
        if hi <= lo:
            hi = lo + 1e-6
        stretched = np.nan_to_num(np.clip((data - lo) / (hi - lo), 0.0, 1.0), nan=0.0)
        norm = (stretched * 255.0).astype(np.uint8)

    img = Image.fromarray(norm, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@app.get("/health")
def health():
    return {"status": "ok", "service": "SPHEREx IRSA Cutout Worker", "cache_dir": str(CUTOUT_CACHE_DIR)}


def _discovery_metadata(results):
    return {
        "discovery_complete": results.meta.get("discovery_complete", True),
        "discovery_source": results.meta.get("discovery_source", ["sia"]),
    }


def _image_provenance(row):
    collection = str(row.get("obs_collection", ""))
    return {
        "release": collection.removeprefix("spherex_").upper() if collection else None,
        "obs_collection": collection or None,
        "observation_date": str(row["observation_date"]) if "observation_date" in row.colnames else None,
        "source_url": str(row.get("source_url", row.get("access_url", ""))),
        "discovery_source": str(row.get("discovery_source", "sia")),
    }


@app.post("/api/cutout/search")
def search_cutouts(req: CutoutRequest):
    """Search NASA/IPAC IRSA SIA archive for SPHEREx images covering the region."""
    try:
        coord = SkyCoord(req.ra * u.deg, req.dec * u.deg)
        size_deg = req.size_arcmin / 60.0
        results = image_search(coord, size_deg, req.collection,
                               allow_release_fallback="collection" not in req.model_fields_set)
        records = []
        for row in results:
            records.append({
                "access_url": str(row.get("access_url", "")),
                "t_min": float(row["t_min"]) if "t_min" in row.colnames else None,
                "instrument": str(row.get("instrument_name", "SPHEREx")),
                "format": str(row.get("format", "application/fits")),
                **_image_provenance(row),
            })
        return {"total": len(records), "results": records, **_discovery_metadata(results)}
    except Exception as e:
        raise HTTPException(status_code=getattr(e, "status", 502), detail=f"IRSA search failed: {e}") from e


@app.get("/api/cutout/render")
def render_cutout_png(
    ra: float = ApiQuery(..., description="Right Ascension in degrees"),
    dec: float = ApiQuery(..., description="Declination in degrees"),
    size_arcmin: float = ApiQuery(3.0, description="Cutout box size in arcmin"),
    subtraction: str = ApiQuery("raw_calibrated", description="raw_calibrated or zodi_subtracted"),
):
    """
    return a ZScale stretched PNG cutout image.
    can be used inside <img src="..." /> or HTML5 canvas.
    """
    size_deg = size_arcmin / 60.0
    coord = SkyCoord(ra * u.deg, dec * u.deg)

    try:
        results = image_search(coord, size_deg, DEFAULT, allow_release_fallback=True)
    except Exception as e:
        raise HTTPException(status_code=getattr(e, "status", 502), detail=f"IRSA search failed: {e}") from e
    if len(results) == 0:
        if not _discovery_metadata(results)["discovery_complete"]:
            raise HTTPException(status_code=503, detail="Archive discovery is incomplete; no indexed SPHEREx coverage yet")
        raise HTTPException(status_code=404, detail="No SPHEREx coverage at this position")

    b_url = str(results[0]["access_url"]).split("?")[0]
    cutout_url = f"{b_url}?center={ra},{dec}&size={size_deg}"
    source_key = hashlib.sha256(b_url.encode()).hexdigest()[:16]
    local_file = CUTOUT_CACHE_DIR / f"cutout_{source_key}_{ra:.4f}_{dec:.4f}_{size_arcmin:.1f}.fits"
    if not local_file.exists():
        status = cutout(cutout_url, local_file,
                        source_url=results[0].get("source_url"),
                        discovery_source=str(results[0].get("discovery_source", "sia")))
        if status != "good":
            raise HTTPException(status_code=502, detail=status)
    try:
        img, bad, clean_m, meta = load_clean_cutout(local_file)
    except Exception as e:
        local_file.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=f"Cutout unreadable: {e}")
    matrix = clean_m if subtraction == "zodi_subtracted" else np.where(bad, np.nan, img)
    png_bytes = array_to_png_bytes(matrix)

    provenance = _image_provenance(results[0])
    discovery = _discovery_metadata(results)
    return Response(content=png_bytes, media_type="image/png", headers={
        "X-IRSA-Discovery-Complete": str(discovery["discovery_complete"]).lower(),
        "X-IRSA-Discovery-Source": ",".join(discovery["discovery_source"]),
        "X-IRSA-Release": provenance["release"] or "unknown",
        "X-IRSA-Source-Url": provenance["source_url"],
    })


@app.post("/api/spectrum/measure")
def measure_spectrum(req: SpectrumRequest):
    """Extract flux and SNR over channels at coords"""
    if not req.cutout_paths:
        return {"channels": [], "message": "No cutout paths supplied"}
    try:
        safe = []
        for name in req.cutout_paths:
            p = (CUTOUT_CACHE_DIR / Path(name).name).resolve()
            if p.parent != CUTOUT_CACHE_DIR.resolve() or not p.exists():
                raise HTTPException(status_code=400, detail=f"Unknown cutout: {name}")
            safe.append(p)
        tbl = extract_spectrum(safe, req.ra, req.dec, radius_pix=req.radius_pix)
        rows = []
        for r in tbl:
            rows.append({
                "mjd": float(r["mjd"]),
                "detector": str(r["detector"]),
                "wavelength_um": float(r["wavelength_um"]),
                "bandwidth_um": float(r["bandwidth_um"]),
                "flux_mjy": float(r["flux_mjy"]),
                "uncertainty_mjy": float(r["uncertainty_mjy"]),
                "snr": float(r["snr"]),
            })
        return {"total": len(rows), "spectrum": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _detector_number(value) -> int:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else 0


@app.get("/api/spectrum")
def real_spectrum(
    ra: float = ApiQuery(..., description="Right Ascension in degrees"),
    dec: float = ApiQuery(..., description="Declination in degrees"),
    radius_pix: float = ApiQuery(2.0, ge=0.5, le=10.0),
    size_arcmin: float = ApiQuery(1.5, ge=0.5, le=10.0, description="Cutout size per exposure"),
    max_frames: int = ApiQuery(120, ge=1, le=400),
    candidate_id: Optional[str] = None,
):
    """
    SPHEREx spectrophotometry at fixed sky position.
    IRSA for every exposure covering (ra, dec), downloads cutout,
    and measures zodi-subtracted, flag-masked aperture photometry
    response shape matches the frontend's TargetSpectrumResult.
    """
    coord = SkyCoord(ra * u.deg, dec * u.deg)
    size_deg = size_arcmin / 60.0
    try:
        results = image_search(coord, size_deg, DEFAULT, allow_release_fallback=True)
    except Exception as e:
        raise HTTPException(status_code=getattr(e, "status", 502), detail=f"IRSA search failed: {e}") from e
    if len(results) == 0:
        if not _discovery_metadata(results)["discovery_complete"]:
            raise HTTPException(status_code=503, detail="Archive discovery is incomplete; no indexed SPHEREx coverage yet")
        raise HTTPException(status_code=404, detail="No SPHEREx coverage at this position")

    rows, skipped, failed = [], 0, 0
    for row in list(results)[:max_frames]:
        base_url = str(row["access_url"]).split("?")[0]
        key = hashlib.md5(f"{base_url}|{ra:.5f}|{dec:.5f}|{size_deg:.5f}".encode()).hexdigest()[:16]
        local_file = CUTOUT_CACHE_DIR / f"spec_{key}.fits"
        if not local_file.exists():
            status = cutout(f"{base_url}?center={ra},{dec}&size={size_deg}", local_file,
                            source_url=row.get("source_url"),
                            discovery_source=str(row.get("discovery_source", "sia")))
            if status != "good":
                failed += 1
                continue
        try:
            pt = measure_cutout_point(local_file, ra, dec, radius_pix=radius_pix)
        except Exception:
            local_file.unlink(missing_ok=True)
            failed += 1
            continue
        if pt is None:
            skipped += 1  # outside the cutout, or aperture touches a masked pixel
            continue
        rows.append({**pt, **_image_provenance(row)})

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No usable measurements ({skipped} masked/out of footprint, {failed} failed)",
        )

    rows.sort(key=lambda r: r["wavelength_um"])
    spectrum, summaries = [], {}
    for i, r in enumerate(rows, start=1):
        det_num = _detector_number(r["detector"])
        spectrum.append({
            **{k: r[k] for k in ("release", "obs_collection", "observation_date", "source_url", "discovery_source")},
            "channel": i,
            "detector": f"D{det_num}",
            "detector_array": det_num,
            "wavelength_um": r["wavelength_um"],
            "bandwidth_um": r["bandwidth_um"],
            "flux_mjy": r["flux_mjy"],
            "uncertainty_mjy": r["uncertainty_mjy"],
            "snr": r["snr"],
            "flagged": False,
            "mjd": r["mjd"],
        })
    for d in sorted({p["detector"] for p in spectrum}):
        pts = [p for p in spectrum if p["detector"] == d]
        summaries[d] = {
            "range": f"{min(p['wavelength_um'] for p in pts):.2f}-{max(p['wavelength_um'] for p in pts):.2f} um",
            "mean_flux_mjy": round(float(np.mean([p["flux_mjy"] for p in pts])), 3),
            "mean_snr": round(float(np.mean([p["snr"] for p in pts])), 2),
            "channels": len(pts),
        }

    return {
        "target": candidate_id or f"RA {ra:.4f}, Dec {dec:.4f}",
        "ra": round(ra, 5),
        "dec": round(dec, 5),
        "candidate_id": candidate_id,
        "aperture_radius_pix": radius_pix,
        "subtraction_mode": "zodi_subtracted",
        "bad_pixel_mask": "FLAGS allow-list (SOURCE only); non-finite and VARIANCE<=0 masked",
        "wcs_mode": "WCS-WAVE (alt key 'W')",
        "molecular_detections": [],  # compute from the measured spectrum; never hard-code
        "detectors_summary": summaries,
        "total_channels": len(spectrum),
        "n_exposures_found": len(results),
        **_discovery_metadata(results),
        "n_masked_or_outside": skipped,
        "n_failed": failed,
        "spectrum": spectrum,
    }
