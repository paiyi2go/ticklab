"""Entry points shared by the web server and the in-browser (Pyodide) demo."""

from __future__ import annotations

import io
import json

from .analyze import STANDARD_BPH, AnalysisError, analyze, load_wav
from .diagnose import Reading, assess
from .synth import synth_watch

SIMULATION_SECONDS = 15.0
_LIMITS = {
    "rate": (-300.0, 300.0),
    "beat_error_ms": (0.0, 5.0),
    "amplitude": (150.0, 330.0),
    "snr_db": (5.0, 50.0),
    "lift_angle": (30.0, 70.0),
}


def analyze_wav(data: bytes, lift_angle: float = 52.0, bph: int | None = None) -> dict:
    try:
        samples, sr = load_wav(io.BytesIO(data))
    except Exception:
        raise ValueError("Could not read the file as WAV audio.")
    return analyze(samples, sr, lift_angle=lift_angle, bph=bph, detail=True).to_dict()


def simulate(
    bph: int = 28800,
    rate: float = 0.0,
    beat_error_ms: float = 0.0,
    amplitude: float = 280.0,
    snr_db: float = 30.0,
    lift_angle: float = 52.0,
) -> dict:
    """Synthesise a watch with the given faults and measure it."""
    if bph not in STANDARD_BPH:
        raise ValueError(f"bph must be one of {STANDARD_BPH}.")
    values = {"rate": rate, "beat_error_ms": beat_error_ms, "amplitude": amplitude, "snr_db": snr_db, "lift_angle": lift_angle}
    for name, value in values.items():
        lo, hi = _LIMITS[name]
        if not lo <= value <= hi:
            raise ValueError(f"{name} must be between {lo:g} and {hi:g}.")
    samples = synth_watch(
        duration=SIMULATION_SECONDS, bph=bph, rate=rate, beat_error_ms=beat_error_ms,
        amplitude=amplitude, lift_angle=lift_angle, snr_db=snr_db,
    )
    return analyze(samples, 48000, lift_angle=lift_angle, detail=True).to_dict()


def assess_readings(readings: list[dict]) -> dict:
    return assess([Reading(**r) for r in readings])


def call_json(name: str, payload: str, data=None) -> str:
    """Single JSON-in, JSON-out entry point for the Pyodide build."""
    args = json.loads(payload)
    try:
        if name == "analyze":
            if hasattr(data, "to_py"):
                data = data.to_py()
            result = analyze_wav(bytes(data), **args)
        elif name == "simulate":
            result = simulate(**args)
        elif name == "assess":
            result = assess_readings(args["readings"])
        else:
            raise ValueError(f"Unknown call {name!r}.")
    except (AnalysisError, ValueError) as e:
        return json.dumps({"ok": False, "error": str(e)})
    return json.dumps({"ok": True, "result": result})
