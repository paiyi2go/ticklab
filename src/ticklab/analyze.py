"""Timegrapher analysis: rate, beat error and amplitude from a recording of a watch.

Pipeline
--------
1. High-pass and rectify the audio into an envelope.
2. Find the beat rate (bph) from the envelope's autocorrelation.
3. Locate each tick: the loudest pulse is the drop, the first pulse is the unlock.
4. Fit drop times to ``t_k = a + T*k + d*(-1)^k``. ``T`` gives the rate, ``d`` the beat error.
5. The unlock-to-drop time is how long the balance takes to sweep the lift angle,
   which gives the amplitude.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import signal
from scipy.io import wavfile
from scipy.ndimage import uniform_filter1d

STANDARD_BPH = (18000, 19800, 21600, 25200, 28800, 36000)
SECONDS_PER_DAY = 86400.0
MIN_DURATION_S = 5.0
MIN_TICKS = 12


class AnalysisError(ValueError):
    """The recording cannot be analysed (too short, too noisy, no ticking found)."""


@dataclass
class Analysis:
    bph: int
    rate_s_per_day: float  # positive = watch gains time
    beat_error_ms: float
    amplitude_deg: float | None  # None when the pulses could not be resolved
    lift_angle_deg: float
    n_ticks: int
    duration_s: float
    jitter_ms: float  # scatter of tick times around the fit
    snr_db: float

    def to_dict(self) -> dict:
        return asdict(self)


def load_wav(path) -> tuple[np.ndarray, int]:
    """Read a WAV file as mono float samples in [-1, 1]."""
    sr, data = wavfile.read(path)
    if data.dtype.kind in "iu":
        scale = float(np.iinfo(data.dtype).max)
        offset = 128.0 if data.dtype == np.uint8 else 0.0
        data = (data.astype(np.float64) - offset) / scale
    else:
        data = data.astype(np.float64)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, int(sr)


def _envelope(x: np.ndarray, sr: int) -> np.ndarray:
    # Tick energy sits in the kHz range; the high-pass removes hum and handling noise.
    sos = signal.butter(4, 2000, "highpass", fs=sr, output="sos")
    y = signal.sosfiltfilt(sos, x)
    return uniform_filter1d(np.abs(y), size=max(3, int(sr * 0.0003)))


def detect_bph(env: np.ndarray, sr: int) -> int:
    """Pick the standard beat rate whose period best matches the envelope's periodicity."""
    q = max(1, sr // 4000)
    n = len(env) // q
    coarse = env[: n * q].reshape(n, q).mean(axis=1)
    fs = sr / q
    # Smooth over a few ms so beat error does not decorrelate adjacent ticks.
    coarse = uniform_filter1d(coarse, size=max(1, int(fs * 0.003)))
    coarse = coarse - coarse.mean()
    spectrum = np.fft.rfft(coarse, 2 * n)  # zero-padded so the autocorrelation does not wrap
    ac = np.fft.irfft(np.abs(spectrum) ** 2)[:n]
    if ac[0] <= 0:
        raise AnalysisError("The recording is silent.")
    ac /= ac[0]

    scores = {}
    for bph in STANDARD_BPH:
        lag = 3600.0 / bph * fs
        lo, hi = int(lag * 0.97), int(np.ceil(lag * 1.03)) + 1
        scores[bph] = float(ac[lo:hi].max()) if hi <= n else 0.0
    best = max(scores.values())
    if best < 0.1:
        raise AnalysisError("No regular ticking found in the recording.")
    # A 36000 bph watch also correlates at the 18000 bph lag (more strongly, if it has
    # beat error), so prefer the fastest clear match.
    return max(b for b, s in scores.items() if s >= 0.3 * best)


def _fit_ticks(t: np.ndarray, period: float) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Least-squares fit of tick times, rejecting outliers. Returns (T, d, residuals, keep)."""
    k = np.concatenate([[0], np.cumsum(np.rint(np.diff(t) / period))]).astype(int)
    parity = np.where(k % 2 == 0, 1.0, -1.0)
    keep = np.ones(len(t), dtype=bool)
    for _ in range(3):
        if keep.sum() < MIN_TICKS or len(set(k[keep] % 2)) < 2:
            raise AnalysisError("Too few clean ticks to measure the rate.")
        design = np.column_stack([np.ones(keep.sum()), k[keep], parity[keep]])
        coef, *_ = np.linalg.lstsq(design, t[keep], rcond=None)
        res = t - (coef[0] + coef[1] * k + coef[2] * parity)
        mad = np.median(np.abs(res[keep] - np.median(res[keep]))) * 1.4826
        new_keep = np.abs(res) < max(4 * mad, 2e-4)
        if np.array_equal(new_keep, keep):
            break
        keep = new_keep
    return float(coef[1]), float(coef[2]), res, keep


def analyze(
    samples: np.ndarray, sr: int, lift_angle: float = 52.0, bph: int | None = None
) -> Analysis:
    """Measure a watch from a mono recording.

    ``lift_angle`` is movement-specific (52 degrees is a common default) and only
    affects the amplitude. Pass ``bph`` to skip beat-rate detection.
    """
    samples = np.asarray(samples, dtype=np.float64)
    duration = len(samples) / sr
    if sr < 16000:
        raise AnalysisError("Sample rate must be at least 16 kHz.")
    if duration < MIN_DURATION_S:
        raise AnalysisError(f"Recording is too short; need at least {MIN_DURATION_S:.0f} s.")

    env = _envelope(samples, sr)
    if bph is None:
        bph = detect_bph(env, sr)
    period = 3600.0 / bph
    period_n = int(round(period * sr))

    floor = float(np.median(env))
    mad = float(np.median(np.abs(env - floor))) * 1.4826
    m = len(env) // period_n
    peak_level = float(np.median(env[: m * period_n].reshape(m, period_n).max(axis=1)))
    snr_db = 20 * np.log10(peak_level / max(floor, 1e-12))
    if snr_db < 12:
        raise AnalysisError("Ticks are too faint against the background noise.")

    peaks, _ = signal.find_peaks(env, height=0.4 * peak_level, distance=int(0.7 * period_n))
    window = int(min(0.3 * period, 0.03) * sr)
    drops, lifts = [], []
    for p in peaks:
        if p < window:
            continue
        seg = env[p - window : p + 1]
        below_half = np.nonzero(seg < 0.5 * env[p])[0]
        if len(below_half) == 0:
            continue
        drop = int(below_half[-1]) + 1
        # The unlock pulse is faint; when it is lost in noise the lift time is unknown.
        above = seg > max(floor + 5 * mad, 0.08 * env[p])
        onset = int(np.argmax(above))
        drops.append((p - window + drop) / sr)
        lifts.append((drop - onset) / sr if not above[0] else np.nan)
    if len(drops) < MIN_TICKS:
        raise AnalysisError("Too few clean ticks to measure the rate.")

    # Timing uses the drop pulse: it is the loudest, so its edge is the most repeatable.
    fitted_period, d, res, keep = _fit_ticks(np.array(drops), period)

    amplitude = None
    good_lifts = np.array(lifts)[keep]
    good_lifts = good_lifts[np.isfinite(good_lifts)]
    if len(good_lifts) >= MIN_TICKS:
        lift_time = float(np.median(good_lifts))
        spread = float(np.median(np.abs(good_lifts - lift_time)))
        phase = np.pi * (bph / 7200.0) * lift_time  # balance: theta = A sin(2 pi f t)
        if spread < 0.1 * lift_time and 0 < phase < np.pi / 2:
            candidate = lift_angle / (2 * np.sin(phase))
            if 90 <= candidate <= 360:
                amplitude = float(candidate)

    return Analysis(
        bph=bph,
        rate_s_per_day=(period / fitted_period - 1) * SECONDS_PER_DAY,
        beat_error_ms=2 * abs(d) * 1e3,
        amplitude_deg=amplitude,
        lift_angle_deg=lift_angle,
        n_ticks=int(keep.sum()),
        duration_s=duration,
        jitter_ms=float(np.std(res[keep]) * 1e3),
        snr_db=float(snr_db),
    )


def analyze_file(path, lift_angle: float = 52.0, bph: int | None = None) -> Analysis:
    samples, sr = load_wav(path)
    return analyze(samples, sr, lift_angle=lift_angle, bph=bph)
