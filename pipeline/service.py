import asyncio
import hashlib
import io
import json
import os
import signal
import sys
from pathlib import Path
from typing import List, Optional

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.visualization import ZScaleInterval
from fastapi import FastAPI, HTTPException, Request, Query as ApiQuery
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from PIL import Image
from pydantic import BaseModel

from spherex import processing
from spherex.cleaning import load_clean_cutout
from scripts.spectra import extract_spectrum, measure_cutout_point

# Archive dependencies are optional for the internal, offline processing API.
DEFAULT = "spherex_dr1"


def image_search(*args, **kwargs):
    from spherex.query import image_search as query
    return query(*args, **kwargs)


def cutout(*args, **kwargs):
    from spherex.query import cutout as download
    return download(*args, **kwargs)


app = FastAPI(
    title="SPHEREx IRSA Cutout & Preprocessing Worker",
    version="1.0.0",
    description="Image cutouts, ZODI subtraction, ZScale rendering, and experimental aperture photometry",
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
    return {"status": "ok", "service": "SPHEREx IRSA Cutout Worker", "cache_dir": str(CUTOUT_CACHE_DIR), "revision": os.environ.get("APP_REVISION", "unknown"), "processing": "ready"}


@app.post("/api/cutout/search")
def search_cutouts(req: CutoutRequest):
    """Search NASA/IPAC IRSA SIA archive for SPHEREx images covering the region."""
    try:
        coord = SkyCoord(req.ra * u.deg, req.dec * u.deg)
        size_deg = req.size_arcmin / 60.0
        results = image_search(coord, size_deg, req.collection)
        records = []
        for row in results:
            records.append({
                "access_url": str(row.get("access_url", "")),
                "t_min": float(row["t_min"]) if "t_min" in row.colnames else None,
                "instrument": str(row.get("instrument_name", "SPHEREx")),
                "format": str(row.get("format", "application/fits")),
            })
        return {"total": len(records), "results": records}
    except Exception as e:
        return {"total": 0, "results": [], "error": str(e)}


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
        results = image_search(coord, size_deg, DEFAULT)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"IRSA search failed: {e}")
    if len(results) == 0:
        raise HTTPException(status_code=404, detail="No SPHEREx coverage at this position")

    b_url = str(results[0]["access_url"]).split("?")[0]
    cutout_url = f"{b_url}?center={ra},{dec}&size={size_deg}"
    local_file = CUTOUT_CACHE_DIR / f"cutout_{DEFAULT}_{ra:.4f}_{dec:.4f}_{size_arcmin:.1f}.fits"
    if not local_file.exists():
        status = cutout(cutout_url, local_file)
        if status != "good":
            raise HTTPException(status_code=502, detail=status)
    try:
        img, bad, clean_m, meta = load_clean_cutout(local_file)
    except Exception as e:
        local_file.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=f"Cutout unreadable: {e}")
    matrix = clean_m if subtraction == "zodi_subtracted" else np.where(bad, np.nan, img)
    png_bytes = array_to_png_bytes(matrix)

    return Response(content=png_bytes, media_type="image/png")


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
        results = image_search(coord, size_deg, DEFAULT)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"IRSA search failed: {e}")
    if len(results) == 0:
        raise HTTPException(status_code=404, detail="No SPHEREx coverage at this position")

    rows, skipped, failed = [], 0, 0
    for row in list(results)[:max_frames]:
        base_url = str(row["access_url"]).split("?")[0]
        key = hashlib.md5(f"{base_url}|{ra:.5f}|{dec:.5f}|{size_deg:.5f}".encode()).hexdigest()[:16]
        local_file = CUTOUT_CACHE_DIR / f"spec_{key}.fits"
        if not local_file.exists():
            status = cutout(f"{base_url}?center={ra},{dec}&size={size_deg}", local_file)
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
        rows.append(pt)

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
        "n_masked_or_outside": skipped,
        "n_failed": failed,
        "spectrum": spectrum,
    }


# Scala owns downloads and file leases; this API processes shared local files only.
PROCESSING_TIMEOUT_SECONDS = min(120.0, max(0.1, float(os.environ.get('PROCESSING_TIMEOUT_SECONDS', '120'))))
PROCESSING_MAX_CONCURRENCY = max(1, min(32, int(os.environ.get('PROCESSING_MAX_CONCURRENCY', '2'))))
PROCESSING_PROTOCOL_BYTES = 65_536
_active_processing = 0


class ProcessingHTTPError(Exception):
    def __init__(self, code, message, status=502):
        self.code, self.message, self.status = code, message, status


def _processing_error(code, message, status):
    return JSONResponse(status_code=status, content={'status': 'error', 'error': {'code': code, 'message': message}})


def _processing_command():
    return [sys.executable, '-m', 'spherex.processing']


async def _bounded_pipe(stream):
    data = bytearray()
    while chunk := await stream.read(4096):
        data.extend(chunk)
        if len(data) > PROCESSING_PROTOCOL_BYTES:
            raise ProcessingHTTPError('invalid_response', 'Processing child exceeded its protocol output limit')
    return bytes(data)


async def _send_processing_request(stream, payload):
    stream.write(payload)
    await stream.drain()
    stream.close()
    await stream.wait_closed()


async def _processing_disconnect(request):
    while not await request.is_disconnected():
        await asyncio.sleep(0.05)


async def _stop_processing_child(child):
    # The process owns no network work; kill its entire group before releasing leases.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await child.wait()


async def _finish_processing(child, tasks):
    try:
        if child is not None:
            await _stop_processing_child(child)
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def _supervised_processing(request, payload):
    child = None
    tasks = []
    try:
        pipeline_dir = str(Path(__file__).resolve().parent)
        spawn = asyncio.create_task(asyncio.create_subprocess_exec(
            *_processing_command(), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=pipeline_dir, env={**os.environ, 'PYTHONPATH': pipeline_dir},
            start_new_session=True, limit=PROCESSING_PROTOCOL_BYTES,
        ))
        interrupted = False
        while not spawn.done():
            try:
                await asyncio.shield(spawn)
            except asyncio.CancelledError:
                interrupted = True
        child = spawn.result()
        if interrupted:
            raise asyncio.CancelledError
        readers = [asyncio.create_task(coroutine) for coroutine in (
            _send_processing_request(child.stdin, payload), _bounded_pipe(child.stdout),
            _bounded_pipe(child.stderr), child.wait())]
        collection = asyncio.gather(*readers)
        disconnected = asyncio.create_task(_processing_disconnect(request))
        tasks = [collection, disconnected, *readers]
        done, _ = await asyncio.wait([collection, disconnected], timeout=PROCESSING_TIMEOUT_SECONDS,
                                     return_when=asyncio.FIRST_COMPLETED)
        if not done:
            raise ProcessingHTTPError('deadline_exceeded', 'Processing deadline exceeded', 504)
        if disconnected in done:
            raise ProcessingHTTPError('client_disconnected', 'Processing client disconnected', 499)
        _, stdout, _, exit_code = await collection
        try:
            result = json.loads(stdout)
        except (ValueError, UnicodeError) as error:
            raise ProcessingHTTPError('invalid_response', 'Processing child returned invalid JSON') from error
        if not isinstance(result, dict) or result.get('status') not in ('ok', 'error'):
            raise ProcessingHTTPError('invalid_response', 'Processing child returned an invalid result')
        if result['status'] == 'error':
            error = result.get('error')
            if not isinstance(error, dict) or not isinstance(error.get('code'), str):
                raise ProcessingHTTPError('invalid_response', 'Processing child returned an invalid error')
            return JSONResponse(status_code=422, content=result)
        if exit_code != 0:
            raise ProcessingHTTPError('processing_failed', 'Processing child failed')
        return JSONResponse(content=result)
    finally:
        # Even repeated cancellation must wait for OS exit and reader cleanup.
        cleanup = asyncio.create_task(_finish_processing(child, tasks))
        interrupted = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                interrupted = True
        await cleanup
        if interrupted:
            raise asyncio.CancelledError


@app.get('/internal/capabilities')
def processing_capabilities():
    return processing.execute({'operation': 'capabilities'})


@app.post('/internal/processing')
async def process_shared_fits(request: Request):
    global _active_processing
    try:
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > processing.MAX_REQUEST_BYTES:
                raise processing.WorkerError('invalid_request', 'request exceeds 65536 bytes')
            raw.extend(chunk)
        try:
            payload = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        except (ValueError, UnicodeError, RecursionError) as error:
            raise processing.WorkerError('invalid_request', 'request must contain one JSON object') from error
        payload = processing.validate_http_request(payload)
        immutable_payload = json.dumps(payload, allow_nan=False, separators=(',', ':')).encode()
    except processing.WorkerError as error:
        return _processing_error(error.code, str(error), 422)
    except (OSError, ValueError, TypeError) as error:
        return _processing_error('invalid_request', str(error), 422)
    if _active_processing >= PROCESSING_MAX_CONCURRENCY:
        return _processing_error('capacity_exceeded', 'Processing capacity is exhausted', 503)
    _active_processing += 1
    try:
        return await _supervised_processing(request, immutable_payload)
    except ProcessingHTTPError as error:
        return _processing_error(error.code, error.message, error.status)
    except (OSError, ValueError, BrokenPipeError):
        return _processing_error('processing_failed', 'Processing child could not complete', 502)
    finally:
        _active_processing -= 1
