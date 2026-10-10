"""Command-line interface: ``ticklab synth | analyze | report``."""

from __future__ import annotations

import argparse
import json
import sys

from .analyze import STANDARD_BPH, AnalysisError, analyze_file
from .diagnose import POSITIONS, Reading, assess, explain
from .synth import synth_watch, write_wav


def _print_analysis(a) -> None:
    amplitude = f"{a.amplitude_deg:.0f} deg" if a.amplitude_deg else "not measurable"
    print(f"  beat rate    {a.bph} bph")
    print(f"  rate         {a.rate_s_per_day:+.1f} s/day")
    print(f"  beat error   {a.beat_error_ms:.2f} ms")
    print(f"  amplitude    {amplitude} (lift angle {a.lift_angle_deg:g})")
    print(f"  quality      {a.n_ticks} ticks, jitter {a.jitter_ms:.3f} ms, SNR {a.snr_db:.0f} dB")


def _cmd_synth(args) -> None:
    samples = synth_watch(
        duration=args.duration, bph=args.bph, rate=args.rate,
        beat_error_ms=args.beat_error, amplitude=args.amplitude, snr_db=args.snr,
    )
    write_wav(args.out, samples)
    print(f"Wrote {args.out}")


def _cmd_analyze(args) -> None:
    a = analyze_file(args.wav, lift_angle=args.lift_angle, bph=args.bph)
    if args.json:
        print(json.dumps(a.to_dict(), indent=2))
    else:
        _print_analysis(a)


def _cmd_report(args) -> None:
    readings = []
    for item in args.recordings:
        position, _, path = item.partition("=")
        if position not in POSITIONS or not path:
            sys.exit(f"Expected POSITION=FILE with POSITION in {', '.join(POSITIONS)}; got {item!r}")
        a = analyze_file(path, lift_angle=args.lift_angle, bph=args.bph)
        print(position)
        _print_analysis(a)
        readings.append(Reading(position, a.rate_s_per_day, a.beat_error_ms, a.amplitude_deg))

    result = assess(readings)
    print(f"\nAverage rate {result['mean_rate_s_per_day']:+.1f} s/day", end="")
    if result["positional_delta_s_per_day"] is not None:
        print(f", positional delta {result['positional_delta_s_per_day']:.1f} s/day", end="")
    print()
    for f in result["findings"]:
        print(f"  [{f['severity']}] {f['message']}")
    if not result["findings"]:
        print("  Nothing flagged.")

    if args.ai:
        diagnosis = explain(result, movement=args.movement)
        print(f"\n{diagnosis.summary}\n")
        for c in diagnosis.likely_causes:
            print(f"  ({c.likelihood}) {c.cause}: {c.evidence}")
        print()
        for step in diagnosis.recommended_actions:
            print(f"  - {step}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="ticklab", description="Timegrapher for mechanical watches.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_measurement_options(p):
        p.add_argument("--lift-angle", type=float, default=52.0, help="movement lift angle in degrees (default 52)")
        p.add_argument("--bph", type=int, choices=STANDARD_BPH, help="beat rate; detected automatically if omitted")

    p = sub.add_parser("synth", help="generate a synthetic watch recording")
    p.add_argument("out")
    p.add_argument("--duration", type=float, default=30.0)
    p.add_argument("--bph", type=int, default=28800, choices=STANDARD_BPH)
    p.add_argument("--rate", type=float, default=0.0, help="s/day, positive gains")
    p.add_argument("--beat-error", type=float, default=0.0, help="ms")
    p.add_argument("--amplitude", type=float, default=280.0, help="degrees")
    p.add_argument("--snr", type=float, default=30.0, help="dB")
    p.set_defaults(func=_cmd_synth)

    p = sub.add_parser("analyze", help="measure one WAV recording")
    p.add_argument("wav")
    p.add_argument("--json", action="store_true")
    add_measurement_options(p)
    p.set_defaults(func=_cmd_analyze)

    p = sub.add_parser("report", help="measure several positions and assess the watch")
    p.add_argument("recordings", nargs="+", metavar="POSITION=FILE")
    p.add_argument("--ai", action="store_true", help="add a plain-language diagnosis from Claude")
    p.add_argument("--movement", help='movement name, e.g. "ETA 2824-2"')
    add_measurement_options(p)
    p.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (AnalysisError, FileNotFoundError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
