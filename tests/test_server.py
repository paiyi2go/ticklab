import io

import pytest
from fastapi.testclient import TestClient
from scipy.io import wavfile

from ticklab.server import app
from ticklab.synth import synth_watch

client = TestClient(app)


def wav_bytes(samples, sr=48000):
    buf = io.BytesIO()
    wavfile.write(buf, sr, (samples * 32767).astype("int16"))
    return buf.getvalue()


def test_index_page():
    res = client.get("/")
    assert res.status_code == 200
    assert "ticklab" in res.text


def test_analyze_upload():
    data = wav_bytes(synth_watch(duration=15.0, rate=7.0, amplitude=270))
    res = client.post("/api/analyze", files={"file": ("w.wav", data, "audio/wav")}, data={"lift_angle": "52"})
    assert res.status_code == 200
    body = res.json()
    assert body["bph"] == 28800
    assert body["rate_s_per_day"] == pytest.approx(7.0, abs=0.5)
    assert body["amplitude_deg"] == pytest.approx(270, abs=5)


def test_analyze_rejects_non_audio():
    res = client.post("/api/analyze", files={"file": ("w.wav", b"not a wav file", "audio/wav")})
    assert res.status_code == 400


def test_analyze_reports_unusable_recording():
    res = client.post("/api/analyze", files={"file": ("w.wav", wav_bytes(synth_watch(duration=2.0)), "audio/wav")})
    assert res.status_code == 422
    assert "too short" in res.json()["detail"]


def test_assess():
    res = client.post("/api/assess", json={"readings": [
        {"position": "dial_up", "rate_s_per_day": -12, "beat_error_ms": 1.1, "amplitude_deg": 240},
        {"position": "crown_down", "rate_s_per_day": -41, "beat_error_ms": 1.2, "amplitude_deg": 185},
    ]})
    assert res.status_code == 200
    assert res.json()["positional_delta_s_per_day"] == pytest.approx(29.0)


def test_ai_explanation_is_off_by_default():
    res = client.post("/api/assess", json={"explain": True, "readings": [
        {"position": "dial_up", "rate_s_per_day": 3, "beat_error_ms": 0.1, "amplitude_deg": 280},
    ]})
    assert res.status_code == 403
