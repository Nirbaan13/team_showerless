"""SPHEREx Blink - ML Candidate Detection Microservice.

Exposes REST endpoints for moving-object track detection and NASA 3I/ATLAS comet benchmark validation.
"""

import json
from pathlib import Path
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from detector import find_candidates

app = FastAPI(
    title="SPHEREx Blink ML Inference Service",
    description="Peak filtering and candidate trajectory detection across multi-epoch infrared frames.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DIR_PATH = Path(__file__).resolve().parent


class DetectionRequest(BaseModel):
    images: List[List[List[float]]] = Field(
        ...,
        description="3D list with dimensions (epochs, height, width). Use null or NaN for masked pixels.",
    )
    times: Optional[List[float]] = Field(
        None,
        description="Observation times strictly increasing for each epoch.",
    )
    min_snr: float = 4.0
    max_peaks: int = 100
    psf_sigma: float = 1.2
    min_speed: float = 0.5
    max_speed: float = 12.0
    match_radius: float = 1.4
    min_epochs: int = 3
    min_support: float = 0.8


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "spherex-ml-detector",
        "version": "1.0.0",
    }


@app.get("/benchmark/3i-atlas")
def get_3i_atlas_benchmark():
    benchmark_file = DIR_PATH / "candidate-example.json"
    if not benchmark_file.exists():
        raise HTTPException(status_code=404, detail="Benchmark sample file not found")
    with open(benchmark_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/detect")
def detect_candidates(req: DetectionRequest):
    try:
        images_array = np.array(req.images, dtype=float)
        times_array = np.array(req.times, dtype=float) if req.times is not None else None

        candidates = find_candidates(
            images_array,
            times_array,
            min_snr=req.min_snr,
            max_peaks=req.max_peaks,
            psf_sigma=req.psf_sigma,
            min_speed=req.min_speed,
            max_speed=req.max_speed,
            match_radius=req.match_radius,
            min_epochs=req.min_epochs,
            min_support=req.min_support,
        )

        results = []
        for rank, cand in enumerate(candidates, start=1):
            results.append({
                "rank": rank,
                "epochs": cand.epochs,
                "positions_xy": cand.positions_xy,
                "snr": cand.snr,
                "speed_px_per_time": cand.speed_px_per_time,
                "fit_rms_px": cand.fit_rms_px,
                "median_peak_ratio": cand.median_peak_ratio,
            })

        return {
            "status": "success",
            "candidate_count": len(results),
            "candidates": results,
        }
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
