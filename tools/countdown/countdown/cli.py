"""Command-line entry point — argparse only.

Parses argv, builds an AppConfig, and dispatches to the composition root.
Holds no domain logic. See docs/configuration.md for the flag reference.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from countdown.composition import build_config, run_apps, run_one_shot, run_watch
from countdown.domain.timespec import parse_quick_input


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "watch":
        return _run_watch(argv[1:])
    if argv and argv[0] == "apps":
        return run_apps()
    return _run_countdown(argv)


def _run_watch(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="countdown watch", description="Watch mode — quick-add countdown timers."
    )
    _add_config_args(parser)
    args = parser.parse_args(argv)
    config, warnings = build_config(**_config_overrides(args))
    for w in warnings:
        print(w, file=sys.stderr)
    return run_watch(config)


def _run_countdown(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="countdown", description="Screen-edge countdown timer (macOS)."
    )
    parser.add_argument(
        "time", nargs="?", help="Minutes (15), clock time (6:00), or use --for-minutes"
    )
    parser.add_argument("--at", metavar="HH:MM", help="Target time (flag form)")
    parser.add_argument(
        "--for-minutes",
        type=float,
        default=None,
        metavar="MIN",
        help="Count down N minutes from now",
    )
    _add_config_args(parser)
    args = parser.parse_args(argv)
    config, warnings = build_config(**_config_overrides(args))
    for w in warnings:
        print(w, file=sys.stderr)
    now = dt.datetime.now()

    if args.for_minutes is not None:
        if args.time or args.at:
            parser.error("Use either --for-minutes or a clock time, not both")
        target = now + dt.timedelta(minutes=args.for_minutes)
    else:
        raw = args.time or args.at
        if not raw:
            parser.error("Provide a target time, --for-minutes, or use: countdown watch")
        try:
            target = parse_quick_input(raw, now)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1

    if (target - now).total_seconds() <= 0:
        print("Target time is already in the past.", file=sys.stderr)
        return 1
    return run_one_shot(config, target)


def _add_config_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("config (.env defaults, CLI overrides)")
    for flag in (
        "--stroke-width",
        "--pulse-before-secs",
        "--pulse-opacity-ramp-secs",
        "--pulse-max-opacity",
        "--pulse-depth-min",
        "--pulse-depth-max",
        "--pulse-visual-power",
        "--shake-wiggle-seconds",
        "--shake-max-x",
        "--shake-max-y",
        "--shake-speed",
        "--shake-speed-x",
        "--shake-speed-y",
        "--shake-smooth",
        "--red-zone-fraction",
    ):
        group.add_argument(flag, type=float, default=None)
    group.add_argument(
        "--pulse-ramp", choices=["linear", "late"], default=None,
        help="Pulse spread preset",
    )
    group.add_argument(
        "--pulse-ramp-power", type=float, default=None, metavar="N",
        help="Pulse spread exponent (overrides --pulse-ramp)",
    )
    group.add_argument(
        "--block-on-end",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="At zero: show the stop overlay, then tidy windows",
    )


def _config_overrides(args: argparse.Namespace) -> dict[str, object]:
    """Map CLI args to AppConfig field names. None values are ignored by merge()."""
    return {
        "stroke_width": args.stroke_width,
        "pulse_before_secs": args.pulse_before_secs,
        "pulse_opacity_ramp_secs": args.pulse_opacity_ramp_secs,
        "pulse_max_opacity": args.pulse_max_opacity,
        "pulse_depth_min": args.pulse_depth_min,
        "pulse_depth_max": args.pulse_depth_max,
        "pulse_ramp_power": _ramp_power(args),
        "pulse_visual_power": args.pulse_visual_power,
        "shake_wiggle_seconds": args.shake_wiggle_seconds,
        "shake_max_x": args.shake_max_x,
        "shake_max_y": args.shake_max_y,
        "shake_speed": args.shake_speed,
        "shake_speed_x": args.shake_speed_x,
        "shake_speed_y": args.shake_speed_y,
        "shake_smooth": args.shake_smooth,
        "red_zone_fraction": args.red_zone_fraction,
        "block_on_end": args.block_on_end,
    }


def _ramp_power(args: argparse.Namespace) -> float | None:
    """--pulse-ramp-power overrides the --pulse-ramp preset."""
    if args.pulse_ramp_power is not None:
        return args.pulse_ramp_power
    return {"linear": 1.0, "late": 3.0}.get(args.pulse_ramp)


if __name__ == "__main__":
    raise SystemExit(main())
