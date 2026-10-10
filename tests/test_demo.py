import json

from ticklab.demo import call_json


def test_call_json_simulate():
    out = json.loads(call_json("simulate", json.dumps({"rate": -5})))
    assert out["ok"] and abs(out["result"]["rate_s_per_day"] + 5) < 0.5


def test_call_json_reports_errors():
    assert json.loads(call_json("simulate", json.dumps({"snr_db": 15}))) == {
        "ok": False, "error": "Ticks are too faint against the background noise.",
    }
    assert not json.loads(call_json("analyze", "{}", b"junk"))["ok"]


def test_call_json_assess():
    reading = {"position": "dial_up", "rate_s_per_day": 3, "beat_error_ms": 0.1, "amplitude_deg": 280}
    out = json.loads(call_json("assess", json.dumps({"readings": [reading]})))
    assert out["result"]["findings"] == []
