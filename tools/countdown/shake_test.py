#!/usr/bin/env python3
"""Test frontmost-window shake in isolation.

Focus the app you want to wobble, then run:

    ./shake --seconds 20
    ./shake --seconds 30 --max-x 8 --max-y 4 --speed 2
    ./shake --seconds 20 --intensity-ramp 8 --intensity-curve smooth
    ./shake --seconds 15 --intensity 1 --speed-x 0.9 --speed-y 0.7 --verbose

Tune flags until it feels right, then copy the numbers into
FocusShaker.update() in countdown.py.

Needs Accessibility permission for Terminal/iTerm.
"""

from __future__ import annotations

import argparse
import math
import signal
import sys
import time

import AppKit
import objc

try:
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
        AXUIElementSetAttributeValue,
        AXValueCreate,
        AXValueGetValue,
        kAXValueCGPointType,
    )
except ImportError:
    print("Missing pyobjc-framework-ApplicationServices. Run: pip install pyobjc-framework-ApplicationServices", file=sys.stderr)
    raise SystemExit(1)

FRAME_INTERVAL = 1.0 / 60.0


def _lerp(current: float, target: float, dt_seconds: float, rate: float) -> float:
    alpha = 1.0 - math.exp(-rate * dt_seconds)
    return current + (target - current) * alpha


def _intensity_curve(t: float, curve: str) -> float:
    t = max(0.0, min(1.0, t))
    if curve == "linear":
        return t
    if curve == "smooth":
        return t * t * (3.0 - 2.0 * t)
    if curve == "exp":
        return t * t
    raise ValueError(f"unknown intensity curve: {curve}")


class ShakeTester:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self._phase = 0.0
        self._dx = 0.0
        self._dy = 0.0
        self._ax_window = None
        self._ax_origin: AppKit.NSPoint | None = None
        self._ax_enabled = True
        self._done = False
        self._started = time.monotonic()

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._stop)

        AppKit.NSApplication.sharedApplication()
        AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

        front = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        name = front.localizedName() if front else "?"
        print(f"Shaking frontmost app: {name}", flush=True)
        print(f"  duration={self.args.seconds}s", flush=True)
        if self.args.intensity is not None:
            print(f"  intensity=fixed {self.args.intensity}", flush=True)
        else:
            print(
                f"  intensity=ramp 0→1 over {self.args.intensity_ramp}s "
                f"({self.args.intensity_curve})",
                flush=True,
            )
        print(
            f"  max-x={self.args.max_x}  max-y={self.args.max_y}  "
            f"speed={self.args.speed}  speed-x={self.args.speed_x}  speed-y={self.args.speed_y}",
            flush=True,
        )
        print("Ctrl+C to stop early.\n", flush=True)

        bridge = _TimerBridge.alloc().initWithHandler_(self._tick)
        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            FRAME_INTERVAL, bridge, "tick:", None, True
        )

        while not self._done:
            AppKit.NSRunLoop.currentRunLoop().runMode_beforeDate_(
                AppKit.NSDefaultRunLoopMode,
                AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.05),
            )

        self.restore()
        print("\nStopped — window restored.", flush=True)

    def _stop(self, *_args) -> None:
        self._done = True

    def _intensity(self) -> float:
        if self.args.intensity is not None:
            return max(0.0, min(1.0, self.args.intensity))
        elapsed = time.monotonic() - self._started
        ramp = max(0.001, self.args.intensity_ramp)
        t = min(1.0, elapsed / ramp)
        return _intensity_curve(t, self.args.intensity_curve)

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started
        if elapsed >= self.args.seconds:
            self._done = True
            return

        intensity = self._intensity()
        dt_seconds = FRAME_INTERVAL

        self._phase += dt_seconds * self.args.speed * (0.4 + intensity * 0.6)
        wave = (
            math.sin(self._phase) * 0.65
            + math.sin(self._phase * 0.55 + 0.8) * 0.35
        )

        target_dx = (
            self.args.max_x * wave * intensity
            * math.sin(self._phase * self.args.speed_x)
        )
        target_dy = (
            self.args.max_y * wave * intensity
            * math.cos(self._phase * self.args.speed_y + 0.4)
        )
        self._dx = _lerp(self._dx, target_dx, dt_seconds, self.args.smooth)
        self._dy = _lerp(self._dy, target_dy, dt_seconds, self.args.smooth)

        self._apply()

        if self.args.verbose and int(elapsed * 4) != getattr(self, "_last_print", -1):
            self._last_print = int(elapsed * 4)
            print(
                f"  t={elapsed:5.1f}s  intensity={intensity:.2f}  "
                f"offset=({self._dx:+.1f}, {self._dy:+.1f})",
                flush=True,
            )

    def _apply(self) -> None:
        window = self._focused_window()
        if window is None:
            return

        if window != self._ax_window:
            self.restore()
            self._ax_window = window
            self._ax_origin = self._window_position(window)

        if self._ax_origin is None:
            return

        point = AppKit.NSPoint(self._ax_origin.x + self._dx, self._ax_origin.y + self._dy)
        self._move_window(window, point)

    def restore(self) -> None:
        if self._ax_window is not None and self._ax_origin is not None:
            value = AXValueCreate(kAXValueCGPointType, self._ax_origin)
            AXUIElementSetAttributeValue(self._ax_window, "AXPosition", value)
        self._ax_window = None
        self._ax_origin = None
        self._dx = 0.0
        self._dy = 0.0

    def _focused_window(self):
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        ax_app = AXUIElementCreateApplication(app.processIdentifier())
        err, window = AXUIElementCopyAttributeValue(ax_app, "AXFocusedWindow", None)
        if err != 0 or window is None:
            err, windows = AXUIElementCopyAttributeValue(ax_app, "AXWindows", None)
            if err != 0 or not windows:
                return None
            window = windows[0]
        return window

    def _window_position(self, window):
        err, value = AXUIElementCopyAttributeValue(window, "AXPosition", None)
        if err != 0 or value is None:
            return None
        ok, point = AXValueGetValue(value, kAXValueCGPointType, None)
        if not ok:
            return None
        return AppKit.NSPoint(point.x, point.y)

    def _move_window(self, window, point: AppKit.NSPoint) -> None:
        value = AXValueCreate(kAXValueCGPointType, point)
        err = AXUIElementSetAttributeValue(window, "AXPosition", value)
        if err != 0:
            self._ax_enabled = False
            print("Accessibility move failed — check System Settings → Privacy → Accessibility", file=sys.stderr)
            self.restore()
            self._done = True


class _TimerBridge(AppKit.NSObject):
    def initWithHandler_(self, handler):
        self = objc.super(_TimerBridge, self).init()
        if self is None:
            return None
        self._handler = handler
        return self

    def tick_(self, _timer) -> None:
        self._handler()


def main() -> int:
    parser = argparse.ArgumentParser(description="Test frontmost-window shake (macOS).")
    parser.add_argument("--seconds", type=float, default=20.0, help="How long to run (default: 20)")
    parser.add_argument("--intensity", type=float, default=None, help="Fixed intensity 0–1 (default: ramp up)")
    parser.add_argument(
        "--intensity-ramp",
        type=float,
        default=None,
        metavar="SEC",
        help="Seconds to ramp intensity 0→1 (default: same as --seconds)",
    )
    parser.add_argument(
        "--intensity-curve",
        choices=["linear", "smooth", "exp"],
        default="smooth",
        help="Intensity ramp shape (default: smooth)",
    )
    parser.add_argument("--max-px", type=float, default=8.0, help="Default max slide px for both axes")
    parser.add_argument("--max-x", type=float, default=None, help="Max horizontal slide px (default: --max-px)")
    parser.add_argument("--max-y", type=float, default=None, help="Max vertical slide px (default: --max-px)")
    parser.add_argument("--speed", type=float, default=3.0, help="Base oscillation speed")
    parser.add_argument("--speed-x", type=float, default=0.9, help="X-axis oscillation multiplier")
    parser.add_argument("--speed-y", type=float, default=0.75, help="Y-axis oscillation multiplier")
    parser.add_argument("--smooth", type=float, default=14.0, help="Motion smoothing (higher = snappier)")
    parser.add_argument("--verbose", action="store_true", help="Print live values")
    args = parser.parse_args()

    if args.max_x is None:
        args.max_x = args.max_px
    if args.max_y is None:
        args.max_y = args.max_px
    if args.intensity_ramp is None:
        args.intensity_ramp = args.seconds

    ShakeTester(args).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
