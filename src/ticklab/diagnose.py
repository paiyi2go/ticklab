"""Turn timegrapher readings into a diagnosis.

Two layers, kept deliberately separate:

* ``assess`` is deterministic. It computes the summary numbers and applies
  watchmakers' rules of thumb. Every number the user sees comes from here.
* ``explain`` asks Claude to interpret those findings in plain language. The
  model is given the numbers and never measures or recomputes anything.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

POSITIONS = ("dial_up", "dial_down", "crown_up", "crown_down", "crown_left", "crown_right")
HORIZONTAL = {"dial_up", "dial_down"}
MODEL = "claude-opus-5-5"


@dataclass
class Reading:
    position: str
    rate_s_per_day: float
    beat_error_ms: float
    amplitude_deg: float | None = None


def _finding(code: str, severity: str, message: str) -> dict:
    return {"code": code, "severity": severity, "message": message}


def assess(readings: list[Reading]) -> dict:
    """Summarise readings and flag anything outside common rules of thumb."""
    if not readings:
        raise ValueError("At least one reading is required.")
    for r in readings:
        if r.position not in POSITIONS:
            raise ValueError(f"Unknown position {r.position!r}; expected one of {POSITIONS}.")

    rates = [r.rate_s_per_day for r in readings]
    mean_rate = sum(rates) / len(rates)
    delta = max(rates) - min(rates) if len(rates) > 1 else None
    max_beat_error = max(r.beat_error_ms for r in readings)
    flat = [r.amplitude_deg for r in readings if r.position in HORIZONTAL and r.amplitude_deg]
    hanging = [r.amplitude_deg for r in readings if r.position not in HORIZONTAL and r.amplitude_deg]

    findings = []
    if abs(mean_rate) > 30:
        findings.append(_finding("rate", "warning", f"Average rate is {mean_rate:+.0f} s/day, well outside a normal range."))
    elif abs(mean_rate) > 10:
        findings.append(_finding("rate", "info", f"Average rate is {mean_rate:+.0f} s/day; regulation should bring it in."))
    if mean_rate > 60:
        findings.append(_finding("magnetism", "warning", "A large gain like this is often caused by a magnetised or sticking hairspring."))

    if delta is not None and delta > 20:
        findings.append(_finding("positional", "warning", f"Rate varies by {delta:.0f} s/day between positions, which points to poise or friction problems."))

    if max_beat_error > 0.8:
        findings.append(_finding("beat_error", "warning", f"Beat error reaches {max_beat_error:.1f} ms; the balance is out of beat."))
    elif max_beat_error > 0.5:
        findings.append(_finding("beat_error", "info", f"Beat error of {max_beat_error:.1f} ms is acceptable but not ideal."))

    if flat and min(flat) < 250:
        severity = "warning" if min(flat) < 220 else "info"
        findings.append(_finding("amplitude_flat", severity, f"Amplitude lying flat is {min(flat):.0f} degrees; a healthy, fully wound movement usually exceeds 270."))
    if hanging and min(hanging) < 220:
        severity = "warning" if min(hanging) < 200 else "info"
        findings.append(_finding("amplitude_hanging", severity, f"Amplitude in vertical positions drops to {min(hanging):.0f} degrees."))
    if flat and hanging and max(flat) - min(hanging) > 50:
        findings.append(_finding("amplitude_drop", "warning", "Amplitude falls by more than 50 degrees from flat to vertical, suggesting pivot friction or old oil."))
    if max(flat + hanging, default=0) > 330:
        findings.append(_finding("rebanking", "warning", "Amplitude is very high; the balance may be close to knocking."))
    if not flat and not hanging:
        findings.append(_finding("no_amplitude", "info", "Amplitude could not be measured; the recording was probably too noisy."))

    return {
        "mean_rate_s_per_day": mean_rate,
        "positional_delta_s_per_day": delta,
        "max_beat_error_ms": max_beat_error,
        "min_amplitude_deg": min(flat + hanging, default=None),
        "findings": findings,
        "readings": [asdict(r) for r in readings],
    }


SYSTEM_PROMPT = """\
You are an experienced watchmaker explaining timegrapher results to a watch owner.

You will receive readings taken in one or more positions, plus findings that a rule-based \
check has already flagged. Explain what the results mean for this watch and what the owner \
should do next.

The numbers come from a microphone recording analysed by software, so treat them as \
measured facts and reason from them; do not restate them with different values or invent \
readings for positions that were not measured. When only one or two positions were measured, \
say what further positions would tell you. If a movement is named, use what you know about \
it, including its typical beat rate, lift angle and common faults, and say so when you are unsure.

The owner may not be a watchmaker. Opening a watch and adjusting the regulator or stud \
carrier can damage it, so recommend that only for someone who says they have the tools and \
experience, and otherwise point them to a watchmaker. Likely causes should be ordered from \
most to least probable, each tied to the specific reading that supports it."""


def explain(assessment: dict, movement: str | None = None, client=None):
    """Ask Claude for a plain-language diagnosis of an assessment from ``assess``."""
    import json

    import anthropic
    from pydantic import BaseModel

    class Cause(BaseModel):
        cause: str
        evidence: str
        likelihood: Literal["low", "medium", "high"]

    class Diagnosis(BaseModel):
        summary: str
        likely_causes: list[Cause]
        recommended_actions: list[str]
        needs_watchmaker: bool

    client = client or anthropic.Anthropic()
    payload = {"movement": movement or "unknown", **assessment}
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload, indent=2)}],
        output_format=Diagnosis,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"No diagnosis returned (stop_reason={response.stop_reason}).")
    return response.parsed_output
