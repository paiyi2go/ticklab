import pytest

from ticklab.diagnose import Reading, assess


def codes(result):
    return {f["code"] for f in result["findings"]}


def test_healthy_watch_has_no_findings():
    result = assess([
        Reading("dial_up", 4.0, 0.1, 295),
        Reading("crown_down", 1.0, 0.2, 265),
        Reading("crown_left", 6.0, 0.2, 262),
    ])
    assert result["findings"] == []
    assert result["mean_rate_s_per_day"] == pytest.approx(11 / 3)
    assert result["positional_delta_s_per_day"] == pytest.approx(5.0)


def test_tired_movement_is_flagged():
    result = assess([
        Reading("dial_up", -12.0, 1.1, 240),
        Reading("crown_down", -41.0, 1.2, 185),
    ])
    assert codes(result) == {"rate", "positional", "beat_error", "amplitude_flat", "amplitude_hanging", "amplitude_drop"}


def test_large_gain_suggests_magnetism():
    assert "magnetism" in codes(assess([Reading("dial_up", 180.0, 0.2, 270)]))


def test_single_reading_has_no_delta():
    assert assess([Reading("dial_up", 3.0, 0.1, 280)])["positional_delta_s_per_day"] is None


def test_missing_amplitude_is_reported():
    assert "no_amplitude" in codes(assess([Reading("dial_up", 3.0, 0.1, None)]))


def test_rejects_unknown_position():
    with pytest.raises(ValueError):
        assess([Reading("sideways", 0.0, 0.0, 280)])
