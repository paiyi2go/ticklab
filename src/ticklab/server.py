"""Web API and demo page. Run with ``uvicorn ticklab.server:app``."""

from __future__ import annotations

import io
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .analyze import STANDARD_BPH, AnalysisError, analyze, load_wav
from .diagnose import Reading, assess, explain

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
        samples, sr = load_wav(io.BytesIO(data))
    except Exception:
        raise HTTPException(400, "Could not read the file as WAV audio.")
    try:
        return analyze(samples, sr, lift_angle=lift_angle, bph=bph).to_dict()
    except AnalysisError as e:
        raise HTTPException(422, str(e))


@app.post("/api/assess")
def assess_readings(req: AssessRequest) -> dict:
    try:
        result = assess([Reading(**r.model_dump()) for r in req.readings])
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
