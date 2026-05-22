#!/usr/bin/env python3
"""Standalone wiggle-tuning harness (macOS).

Focus the window you want to wobble, then run:

    ./shake
    ./shake --seconds 20
    ./shake --seconds 30 --max-x 8 --speed 2

Loads shake settings from .env (same as ./run). CLI flags override .env only
when explicitly passed. Drives the real MacShaker adapter and ShakeMotion curve
(edge-cases #10). Needs Accessibility permission for the terminal.
"""

from __future__ import annotations

import argparse
import time

import AppKit

from countdown.adapters.macos.runloop import pump_run_loop
from countdown.adapters.macos.shaker import MacShaker
from countdown.adapters.system.logger import StderrLogger
from countdown.composition import build_config
from countdown.domain.curves import shake_intensity
from countdown.domain.math import smoothstep
from countdown.domain.shake import ShakeMotion

FRAME = 1.0 / 60.0


def _intensity(
    args: argparse.Namespace,
    cfg,
    elapsed: float,
    remaining: float,
) -> float:
    if args.intensity is not None:
        return max(0.0, min(1.0, args.intensity))
    if args.app_timing:
        return shake_intensity(remaining, cfg)
    ramp = max(0.001, args.intensity_ramp)
    return smoothstep(min(1.0, elapsed / ramp))


def main() -> int:
    parser = argparse.ArgumentParser(description="Tune the frontmost-window wiggle.")
    parser.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Duration (default: SHAKE_WIGGLE_SECONDS from .env)",
    )
    parser.add_argument("--intensity", type=float, default=None, help="Fixed 0-1")
    parser.add_argument(
        "--intensity-ramp",
        type=float,
        default=None,
        metavar="SEC",
        help="Ramp 0→1 over this many seconds (default: full run length)",
    )
    parser.add_argument(
        "--app-timing",
        action="store_true",
        help="Use shake_intensity() like ./run (ramp only in final wiggle window)",
    )
    parser.add_argument("--max-x", type=float, default=None)
    parser.add_argument("--max-y", type=float, default=None)
    parser.add_argument("--speed", type=float, default=None)
    parser.add_argument("--speed-x", type=float, default=None)
    parser.add_argument("--speed-y", type=float, default=None)
    parser.add_argument("--smooth", type=float, default=None)
    args = parser.parse_args()

    cfg, _warnings = build_config(
        shake_max_x=args.max_x,
        shake_max_y=args.max_y,
        shake_speed=args.speed,
        shake_speed_x=args.speed_x,
        shake_speed_y=args.speed_y,
        shake_smooth=args.smooth,
    )

    seconds = args.seconds if args.seconds is not None else cfg.shake_wiggle_seconds
    if args.intensity_ramp is None:
        args.intensity_ramp = seconds

    AppKit.NSApplication.sharedApplication()
    AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    motion = ShakeMotion(cfg)
    shaker = MacShaker(StderrLogger())
    print(
        f"Shaking for {seconds:.1f}s — "
        f"max=({cfg.shake_max_x},{cfg.shake_max_y}) "
        f"speed={cfg.shake_speed} smooth={cfg.shake_smooth} "
        f"(from .env; Ctrl+C to stop)"
    )

    start = time.monotonic()
    last = start
    try:
        while True:
            now = time.monotonic()
            elapsed = now - start
            if elapsed >= seconds:
                break
            dt_seconds = max(FRAME, now - last)
            last = now
            remaining = max(0.0, seconds - elapsed)
            level = _intensity(args, cfg, elapsed, remaining)
            dx, dy = motion.offset(level, dt_seconds)
            shaker.apply(dx, dy)
            pump_run_loop(FRAME)
    except KeyboardInterrupt:
        pass
    finally:
        shaker.restore()
    print("Stopped — window restored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
