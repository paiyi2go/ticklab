import numpy as np
import pytest

from ticklab.analyze import AnalysisError, analyze, analyze_file
from ticklab.synth import synth_watch, write_wav

SR = 48000


@pytest.mark.parametrize(
    "bph, rate, beat_error, amplitude",
    [
        (28800, 6.0, 0.3, 280),
        (21600, -15.0, 1.5, 220),
        (18000, 40.0, 0.0, 310),
        (19800, 2.0, 0.2, 250),
        (25200, -8.0, 0.9, 290),
        (36000, -3.0, 0.6, 300),
        (36000, 5.0, 2.0, 300),  # beat error makes this look like 18000 bph
        (28800, -200.0, 3.0, 180),
    ],
)
def test_recovers_ground_truth(bph, rate, beat_error, amplitude):
    a = analyze(synth_watch(bph=bph, rate=rate, beat_error_ms=beat_error, amplitude=amplitude), SR)
    assert a.bph == bph
    assert a.rate_s_per_day == pytest.approx(rate, abs=0.5)
    assert a.beat_error_ms == pytest.approx(beat_error, abs=0.05)
    assert a.amplitude_deg == pytest.approx(amplitude, abs=5)


def test_lift_angle_scales_amplitude():
    x = synth_watch(amplitude=280, lift_angle=50)
    assert analyze(x, SR, lift_angle=50).amplitude_deg == pytest.approx(280, abs=5)
    assert analyze(x, SR, lift_angle=52).amplitude_deg == pytest.approx(280 * 52 / 50, abs=5)


def test_noisy_recording_keeps_rate_but_withholds_amplitude():
    # The faint unlock pulse is buried, so amplitude must be None rather than a wrong number.
    a = analyze(synth_watch(rate=10.0, beat_error_ms=0.4, snr_db=20), SR)
    assert a.rate_s_per_day == pytest.approx(10.0, abs=0.5)
    assert a.beat_error_ms == pytest.approx(0.4, abs=0.05)
    assert a.amplitude_deg is None


@pytest.mark.parametrize(
    "samples",
    [
        np.zeros(SR * 10),
        np.random.default_rng(1).standard_normal(SR * 10) * 0.1,
        synth_watch(duration=2.0),
        synth_watch(snr_db=10),
    ],
    ids=["silence", "noise", "too_short", "too_faint"],
)
def test_rejects_unusable_recordings(samples):
    with pytest.raises(AnalysisError):
        analyze(samples, SR)


def test_wav_round_trip(tmp_path):
    path = tmp_path / "watch.wav"
    write_wav(path, synth_watch(rate=-4.0, duration=15.0))
    assert analyze_file(path).rate_s_per_day == pytest.approx(-4.0, abs=0.5)
