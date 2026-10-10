"""Synthetic watch recordings with known ground truth, used to test the analyser."""

from __future__ import annotations

import numpy as np
from scipy.io import wavfile

# (relative loudness, decay time in s) for the unlock, impulse and drop pulses of one tick
_PULSES = ((0.3, 0.0004), (0.4, 0.0004), (1.0, 0.001))
_TONES_HZ = (5000.0, 8000.0, 12000.0)


def lift_time(bph: int, amplitude: float, lift_angle: float) -> float:
    """Time for the balance to sweep the lift angle at a given amplitude."""
    return float(np.arcsin(lift_angle / (2 * amplitude)) / (np.pi * bph / 7200.0))


def synth_watch(
    duration: float = 30.0,
    sr: int = 48000,
    bph: int = 28800,
    rate: float = 0.0,
    beat_error_ms: float = 0.0,
    amplitude: float = 280.0,
    lift_angle: float = 52.0,
    snr_db: float = 30.0,
    seed: int = 0,
) -> np.ndarray:
    """Generate a mono recording of a watch with the given rate (s/day), beat error and amplitude."""
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    out = np.zeros(n)
    period = 3600.0 / bph / (1 + rate / 86400.0)
    lift = lift_time(bph, amplitude, lift_angle)
    offsets = (0.0, 0.4 * lift, lift)

    k = 0
    while True:
        t0 = 0.05 + k * period + (beat_error_ms / 2e3) * (1 if k % 2 == 0 else -1)
        if t0 + lift + 0.01 > duration:
            break
        for (gain, tau), offset in zip(_PULSES, offsets):
            start = int(round((t0 + offset) * sr))
            ts = np.arange(int(6 * tau * sr)) / sr
            tone = sum(np.sin(2 * np.pi * f * ts + rng.uniform(0, 2 * np.pi)) for f in _TONES_HZ)
            out[start : start + len(ts)] += gain * np.exp(-ts / tau) * tone / len(_TONES_HZ)
        k += 1

    out += rng.standard_normal(n) * 10 ** (-snr_db / 20)
    return out / np.max(np.abs(out)) * 0.9


def write_wav(path, samples: np.ndarray, sr: int = 48000) -> None:
    wavfile.write(path, sr, (np.clip(samples, -1, 1) * 32767).astype(np.int16))
