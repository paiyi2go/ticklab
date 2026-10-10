"""Web API and demo page. Run with ``uvicorn ticklab.server:app``."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import demo
from .analyze import STANDARD_BPH, AnalysisError
from .diagnose import explain

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
STATIC = Path(__file__).parent / "static"
# AI explanations cost money per request, so a deployment has to opt in.
AI_ENABLED = os.environ.get("TICKLAB_AI") == "1"

app = FastAPI(title="ticklab")


class ReadingIn(BaseModel):
    position: str
    rate_s_per_day: float
    beat_error_ms: float
    amplitude_deg: float | None = None


class AssessRequest(BaseModel):
    readings: list[ReadingIn]
    movement: str | None = None
    explain: bool = False


class SimulateRequest(BaseModel):
    bph: int = 28800
    rate: float = 0.0
    beat_error_ms: float = 0.0
    amplitude: float = 280.0
    snr_db: float = 30.0
    lift_angle: float = 52.0


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
def config() -> dict:
    return {"ai_enabled": AI_ENABLED}


@app.post("/api/analyze")
async def analyze_upload(
    file: UploadFile = File(...),
    lift_angle: float = Form(52.0),
    bph: int | None = Form(None),
) -> dict:
    if bph is not None and bph not in STANDARD_BPH:
        raise HTTPException(422, f"bph must be one of {STANDARD_BPH}")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Recording is larger than 20 MB.")
    try:
        return demo.analyze_wav(data, lift_angle=lift_angle, bph=bph)
    except AnalysisError as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/simulate")
def simulate(req: SimulateRequest) -> dict:
    try:
        return demo.simulate(**req.model_dump())
    except (AnalysisError, ValueError) as e:
        raise HTTPException(422, str(e))


@app.post("/api/assess")
def assess_readings(req: AssessRequest) -> dict:
    try:
        result = demo.assess_readings([r.model_dump() for r in req.readings])
    except ValueError as e:
        raise HTTPException(422, str(e))
    if req.explain:
        if not AI_ENABLED:
            raise HTTPException(403, "AI explanations are not enabled on this server.")
        try:
            result["diagnosis"] = explain(result, movement=req.movement).model_dump()
        except Exception as e:
            result["diagnosis_error"] = f"{type(e).__name__}: could not get an AI explanation."
    return result
