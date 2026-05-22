#!/usr/bin/env python3
"""Standalone wiggle-tuning harness (macOS).

Focus the window you want to wobble, then run:

    ./shake --seconds 20
    ./shake --seconds 30 --max-x 8 --max-y 4 --speed 2
    ./shake --seconds 15 --intensity 1 --speed-x 0.9 --speed-y 0.7

This drives the real WindowShaker adapter and the pure ShakeMotion curve — it
shares all motion code with the app, so numbers tuned here transfer directly
to .env (edge-cases #10). Needs Accessibility permission for the terminal.
"""

from __future__ import annotations

import argparse
import time

import AppKit

from countdown.adapters.macos.runloop import pump_run_loop
from countdown.adapters.macos.shaker import MacShaker
from countdown.adapters.system.logger import StderrLogger
from countdown.domain.config import AppConfig
from countdown.domain.math import smoothstep
from countdown.domain.shake import ShakeMotion

FRAME = 1.0 / 60.0


def _intensity(args: argparse.Namespace, elapsed: float) -> float:
    if args.intensity is not None:
        return max(0.0, min(1.0, args.intensity))
    ramp = max(0.001, args.intensity_ramp)
    return smoothstep(min(1.0, elapsed / ramp))


def main() -> int:
    parser = argparse.ArgumentParser(description="Tune the frontmost-window wiggle.")
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--intensity", type=float, default=None, help="Fixed 0-1")
    parser.add_argument("--intensity-ramp", type=float, default=None, metavar="SEC")
    parser.add_argument("--max-x", type=float, default=28.0)
    parser.add_argument("--max-y", type=float, default=28.0)
    parser.add_argument("--speed", type=float, default=10.0)
    parser.add_argument("--speed-x", type=float, default=10.0)
    parser.add_argument("--speed-y", type=float, default=10.0)
    parser.add_argument("--smooth", type=float, default=14.0)
    args = parser.parse_args()
    if args.intensity_ramp is None:
        args.intensity_ramp = args.seconds

    AppKit.NSApplication.sharedApplication()
    AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    cfg = AppConfig(
        shake_max_x=args.max_x,
        shake_max_y=args.max_y,
        shake_speed=args.speed,
        shake_speed_x=args.speed_x,
        shake_speed_y=args.speed_y,
        shake_smooth=args.smooth,
    )
    motion = ShakeMotion(cfg)
    shaker = MacShaker(StderrLogger())
    print(f"Shaking the frontmost window for {args.seconds:.0f}s — Ctrl+C to stop.")

    start = time.monotonic()
    last = start
    try:
        while True:
            now = time.monotonic()
            elapsed = now - start
            if elapsed >= args.seconds:
                break
            dt_seconds = max(FRAME, now - last)
            last = now
            dx, dy = motion.offset(_intensity(args, elapsed), dt_seconds)
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
