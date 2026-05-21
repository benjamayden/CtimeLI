#!/usr/bin/env python3
"""Terminal-activated countdown with a screen-edge stroke timer (macOS).

Usage:
    ./run 6:00
    ./run --for-minutes 25
    cp .env.example .env   # tune shake + block-on-end

Config: .env in this directory (see .env.example). CLI flags override .env.
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import os
import re
import signal
import subprocess
import sys
import time

import AppKit
import objc
from Cocoa import NSBezierPath, NSColor, NSFont, NSMakeRect

from config import AppConfig, shake_intensity

try:
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
        AXUIElementSetAttributeValue,
        AXValueCreate,
        AXValueGetValue,
        kAXValueCGPointType,
    )

    _HAS_ACCESSIBILITY = True
except ImportError:
    _HAS_ACCESSIBILITY = False

STROKE_BLUE = (0.2, 0.75, 1.0)
STROKE_RED = (1.0, 0.12, 0.12)
FRAME_INTERVAL = 1.0 / 60.0
DISPLAY_SMOOTH_RATE = 9.0

TIME_RE = re.compile(
    r"^(\d{1,2})(?::(\d{2})(?::(\d{2}))?)?\s*(am|pm|a\.m\.|p\.m\.)?$",
    re.IGNORECASE,
)


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _stroke_color_for_fraction(fraction: float, red_zone: float):
    if fraction > red_zone:
        r, g, b = STROKE_BLUE
    else:
        t = _smoothstep(1.0 - (fraction / red_zone))
        r = STROKE_BLUE[0] + t * (STROKE_RED[0] - STROKE_BLUE[0])
        g = STROKE_BLUE[1] + t * (STROKE_RED[1] - STROKE_BLUE[1])
        b = STROKE_BLUE[2] + t * (STROKE_RED[2] - STROKE_BLUE[2])
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 0.95)


def parse_target_time(raw: str) -> dt.datetime:
    """Parse a clock time into the next future datetime."""
    m = TIME_RE.match(raw.strip())
    if not m:
        raise ValueError(f"Could not parse time: {raw!r} (try 6:00, 18:00, or 6:00pm)")

    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    second = int(m.group(3) or 0)
    meridiem = (m.group(4) or "").lower().replace(".", "")

    if minute >= 60 or second >= 60 or hour > 23:
        raise ValueError(f"Invalid time: {raw!r}")

    now = dt.datetime.now()

    if meridiem in {"am", "pm"}:
        if hour < 1 or hour > 12:
            raise ValueError(f"Hour must be 1–12 with am/pm: {raw!r}")
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        return target

    if hour >= 13:
        target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        return target

    candidates: list[dt.datetime] = []
    for h in {hour % 12, (hour % 12) + 12}:
        t = now.replace(hour=h, minute=minute, second=second, microsecond=0)
        if t <= now:
            t += dt.timedelta(days=1)
        candidates.append(t)
    return min(candidates, key=lambda t: t - now)


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _lerp(current: float, target: float, dt_sec: float, rate: float) -> float:
    alpha = 1.0 - math.exp(-rate * dt_sec)
    return current + (target - current) * alpha


# Apps we run from / never shake.
_SKIP_SHAKE_APPS = {
    "Terminal",
    "iTerm2",
    "iTerm",
    "Warp",
    "Cursor",
    "Python",
    "python",
    "SystemUIServer",
    "WindowManager",
    "Dock",
    "loginwindow",
}


def _shake_host_names() -> set[str]:
    names = set(_SKIP_SHAKE_APPS)
    term = os.environ.get("TERM_PROGRAM", "").strip()
    if term:
        names.add(term)
    return names


# System processes — never touched on block dismiss.
_SYSTEM_SKIP_PROCESSES = {
    "SystemUIServer",
    "WindowManager",
    "Dock",
    "loginwindow",
    "Python",
    "python",
}


def _applescript_name_list(names: frozenset[str]) -> str:
    if not names:
        return "{}"
    return "{" + ", ".join(f'"{name}"' for name in sorted(names)) + "}"


# Common .env aliases → System Events process names.
_PROCESS_NAME_ALIASES: dict[str, frozenset[str]] = {
    "chrome": frozenset({"Google Chrome", "Chrome"}),
    "google chrome": frozenset({"Google Chrome", "Chrome"}),
    "settings": frozenset({"System Settings", "Settings"}),
    "system preferences": frozenset({"System Settings"}),
    "iterm": frozenset({"iTerm2", "iTerm"}),
    "vscode": frozenset({"Code"}),
}


def _expand_block_end_names(names: frozenset[str]) -> frozenset[str]:
    expanded: set[str] = set(names)
    for name in names:
        aliases = _PROCESS_NAME_ALIASES.get(name.lower())
        if aliases:
            expanded.update(aliases)
    return frozenset(expanded)


def _process_in_list(process: str, names: frozenset[str]) -> bool:
    expanded = _expand_block_end_names(names)
    if process in expanded:
        return True
    lower = process.lower()
    return lower in {name.lower() for name in expanded}


def _foreground_process_names() -> list[str]:
    result = subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to get name of every process '
            "whose background only is false",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    raw = result.stdout.strip()
    if not raw:
        return []
    return [name.strip() for name in raw.split(", ")]


def _action_for_process(process: str, cfg: AppConfig, skip: frozenset[str]) -> str:
    if process in skip:
        return "skip"
    if _process_in_list(process, cfg.block_end_quit):
        return "quit"
    if _process_in_list(process, cfg.block_end_hide):
        return "hide"
    if _process_in_list(process, cfg.block_end_minimize):
        return "minimize"
    return cfg.block_end_default


def _quit_application(process_name: str) -> bool:
    if process_name == "Finder":
        # macOS won't quit Finder — hide it instead.
        return _applescript_hide_processes(["Finder"]) > 0

    targets = _expand_block_end_names(frozenset({process_name}))
    target_lowers = {name.lower() for name in targets}
    ws = AppKit.NSWorkspace.sharedWorkspace()
    for app in ws.runningApplications():
        name = app.localizedName() or ""
        if name not in targets and name.lower() not in target_lowers:
            continue
        if app.activationPolicy() != AppKit.NSApplicationActivationPolicyRegular:
            continue
        pid = app.processIdentifier()
        if not app.terminate():
            app.forceTerminate()
        for _ in range(10):
            time.sleep(0.1)
            if not any(
                a.processIdentifier() == pid
                for a in ws.runningApplications()
            ):
                return True
        return False
    return False


def _applescript_hide_processes(processes: list[str]) -> int:
    if not processes:
        return 0
    hide_list = _applescript_name_list(frozenset(processes))
    script = f"""
set hideCount to 0
tell application "System Events"
    repeat with procName in {hide_list}
        try
            set visible of process procName to false
            set hideCount to hideCount + 1
        end try
    end repeat
end tell
return hideCount
"""
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    try:
        return max(0, int(result.stdout.strip()))
    except ValueError:
        return 0


def _applescript_minimize_processes(processes: list[str]) -> int:
    if not processes:
        return 0
    min_list = _applescript_name_list(frozenset(processes))
    script = f"""
set minCount to 0
tell application "System Events"
    repeat with procName in {min_list}
        try
            tell process procName
                set windowCount to count of windows
                repeat with i from windowCount to 1 by -1
                    try
                        set value of attribute "AXMinimized" of window i to true
                        set minCount to minCount + 1
                    end try
                end repeat
            end tell
        end try
    end repeat
end tell
return minCount
"""
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    try:
        return max(0, int(result.stdout.strip()))
    except ValueError:
        return 0


def apply_block_end_actions(cfg: AppConfig) -> dict[str, int]:
    """Minimize, hide, or quit apps per .env when block-on-end overlay is dismissed."""
    skip = frozenset(_SYSTEM_SKIP_PROCESSES | cfg.block_end_skip)
    to_quit: list[str] = []
    to_hide: list[str] = []
    to_minimize: list[str] = []

    for process in _foreground_process_names():
        action = _action_for_process(process, cfg, skip)
        if action == "quit":
            to_quit.append(process)
        elif action == "hide":
            to_hide.append(process)
        elif action == "minimize":
            to_minimize.append(process)

    counts = {"minimize": 0, "hide": 0, "quit": 0}
    failed_quit: list[str] = []

    for process in to_quit:
        if _quit_application(process):
            counts["quit"] += 1
        else:
            failed_quit.append(process)

    counts["hide"] = _applescript_hide_processes(to_hide)
    counts["minimize"] = _applescript_minimize_processes(to_minimize)

    if failed_quit:
        names = ", ".join(failed_quit)
        print(
            f"Could not quit: {names} (macOS may block Finder/system apps, or name may differ — "
            f"check Activity Monitor for exact process name).",
            file=sys.stderr,
            flush=True,
        )

    return counts


def _format_block_end_summary(counts: dict[str, int]) -> str | None:
    parts = []
    if counts.get("minimize"):
        n = counts["minimize"]
        parts.append(f"minimized {n} window{'s' if n != 1 else ''}")
    if counts.get("hide"):
        n = counts["hide"]
        parts.append(f"hid {n} app{'s' if n != 1 else ''}")
    if counts.get("quit"):
        n = counts["quit"]
        parts.append(f"quit {n} app{'s' if n != 1 else ''}")
    if not parts:
        return None
    return "Block end: " + ", ".join(parts) + "."


# Above screen saver — NSAlert (level ~8) gets buried after hide-all-windows.
_STOP_MODAL_LEVEL = AppKit.NSScreenSaverWindowLevel + 1


# Ignore stray key/mouse events fired while the overlay grabs focus.
_STOP_DISMISS_DELAY = 0.6


class _StopModalController(AppKit.NSObject):
    def init(self):
        self = objc.super(_StopModalController, self).init()
        if self is None:
            return None
        self.dismissed = False
        self.shown_at = time.monotonic()
        self._monitor = None
        self._event_handler = None
        return self

    def can_dismiss(self) -> bool:
        return time.monotonic() - self.shown_at >= _STOP_DISMISS_DELAY

    def dismiss(self) -> None:
        if self.can_dismiss():
            self.dismissed = True

    def install_input_monitor(self) -> None:
        if self._monitor is not None:
            return

        def handle(event):
            if self.can_dismiss():
                if event.type() == AppKit.NSLeftMouseDown:
                    self.dismiss()
                    return None
                if event.type() == AppKit.NSKeyDown and event.keyCode() in (36, 53):
                    self.dismiss()
                    return None
            return event

        self._event_handler = handle
        mask = AppKit.NSLeftMouseDownMask | AppKit.NSKeyDownMask
        self._monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(mask, handle)

    def remove_input_monitor(self) -> None:
        if self._monitor is not None:
            AppKit.NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
        self._event_handler = None


class StopBlockView(AppKit.NSView):
    def initWithFrame_controller_(self, frame, controller):
        self = objc.super(StopBlockView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._controller = controller
        return self

    def isFlipped(self) -> bool:
        return True

    def acceptsFirstResponder(self) -> bool:
        return True

    def becomeFirstResponder(self) -> bool:
        return True

    def keyDown_(self, event) -> None:
        # Return or Escape only — any other key was auto-closing the overlay.
        if self._controller is not None and event.keyCode() in (36, 53):
            self._controller.dismiss()
            return
        objc.super(StopBlockView, self).keyDown_(event)

    def mouseDown_(self, _event) -> None:
        if self._controller is not None and self._controller.can_dismiss():
            self._controller.dismiss()

    def drawRect_(self, _rect) -> None:
        NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.82).set()
        NSBezierPath.fillRect_(self.bounds())

        w = self.bounds().size.width
        h = self.bounds().size.height
        lines = [
            ("It's time to stop.", 42, AppKit.NSFontWeightBold, 1.0),
            ("Your session has ended.", 18, AppKit.NSFontWeightRegular, 0.75),
            ("Click anywhere to tidy windows · Return · or Ctrl+C", 16, AppKit.NSFontWeightMedium, 0.55),
        ]
        sizes = []
        for text, size, weight, _alpha in lines:
            attrs = {
                AppKit.NSFontAttributeName: NSFont.systemFontOfSize_weight_(size, weight),
                AppKit.NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(
                    1.0, _alpha
                ),
            }
            attr_str = AppKit.NSAttributedString.alloc().initWithString_attributes_(text, attrs)
            sizes.append((attr_str, attr_str.size()))

        gap = 18
        total_h = sum(s.height for _, s in sizes) + gap * (len(sizes) - 1)
        y = (h - total_h) / 2
        for (attr_str, size) in sizes:
            attr_str.drawAtPoint_(AppKit.NSMakePoint((w - size.width) / 2, y))
            y += size.height + gap


class StopBlockWindow(AppKit.NSWindow):
    def initWithScreen_controller_(self, screen, controller):
        frame = screen.frame()
        self = objc.super(StopBlockWindow, self).initWithContentRect_styleMask_backing_defer_(
            frame,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        if self is None:
            return None
        self.setLevel_(_STOP_MODAL_LEVEL)
        self.setOpaque_(False)
        self.setBackgroundColor_(NSColor.clearColor())
        self.setIgnoresMouseEvents_(False)
        self.setHasShadow_(False)
        self.setHidesOnDeactivate_(False)
        self.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | AppKit.NSWindowCollectionBehaviorStationary
            | AppKit.NSWindowCollectionBehaviorIgnoresCycle
        )
        view = StopBlockView.alloc().initWithFrame_controller_(
            AppKit.NSMakeRect(0, 0, frame.size.width, frame.size.height), controller
        )
        self.setContentView_(view)
        self._modal_controller = controller
        return self

    def canBecomeKeyWindow(self) -> bool:
        return True

    def canBecomeMainWindow(self) -> bool:
        return True


def _pump_run_loop(seconds: float = 0.1) -> None:
    """Pump the run loop without manually dequeuing events (avoids PyObjC crashes)."""
    deadline = AppKit.NSDate.dateWithTimeIntervalSinceNow_(seconds)
    for mode in (AppKit.NSEventTrackingRunLoopMode, AppKit.NSDefaultRunLoopMode):
        AppKit.NSRunLoop.currentRunLoop().runMode_beforeDate_(mode, deadline)


def _front_stop_modal(windows: list[StopBlockWindow]) -> None:
    AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    AppKit.NSApp.activateIgnoringOtherApps_(True)
    for window in windows:
        window.orderFrontRegardless()
        window.makeKeyAndOrderFront_(None)
    if windows:
        windows[0].makeFirstResponder_(windows[0].contentView())


def _close_stop_modal(windows: list[StopBlockWindow]) -> None:
    for window in windows:
        window.orderOut_(None)
        window.close()


def _shake_window_desc(cfg: AppConfig, total_sec: float) -> str:
    before = cfg.shake_before_mins * 60
    if total_sec < before:
        start = total_sec * cfg.shake_start_fraction
        return f"last {cfg.shake_start_fraction:.0%} ({format_duration(start)}), nudge {cfg.shake_nudge_seconds:.0f}s"
    return (
        f"last {cfg.shake_before_mins:.0f}m, nudge {cfg.shake_nudge_seconds:.0f}s, "
        f"calm final {cfg.shake_stop_before_mins:.0f}m"
    )


class CountdownView(AppKit.NSView):
    def initWithFrame_redZone_(self, frame, red_zone: float):
        self = objc.super(CountdownView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.remaining_fraction = 1.0
        self.stroke_width = 2.0
        self.inset = 0.0
        self.red_zone = red_zone
        self.stroke_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.75, 1.0, 0.95)
        self.label = ""
        return self

    def setProgress_(self, fraction: float) -> None:
        self.remaining_fraction = max(0.0, min(1.0, fraction))
        self.stroke_color = _stroke_color_for_fraction(self.remaining_fraction, self.red_zone)
        self.setNeedsDisplay_(True)

    def setLabel_(self, label: str) -> None:
        self.label = label
        self.setNeedsDisplay_(True)

    def isFlipped(self) -> bool:
        return True

    def drawRect_(self, _rect) -> None:
        bounds = self.bounds()
        w = bounds.size.width
        h = bounds.size.height
        inset = self.inset
        sw = self.stroke_width
        inner = NSMakeRect(inset, inset, w - 2 * inset, h - 2 * inset)

        if self.remaining_fraction > 0:
            self._stroke_perimeter(inner, self.remaining_fraction, self.stroke_color, sw)

        if self.label:
            attrs = {
                AppKit.NSFontAttributeName: NSFont.monospacedDigitSystemFontOfSize_weight_(
                    14, AppKit.NSFontWeightMedium
                ),
                AppKit.NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(
                    1.0, 0.95
                ),
            }
            text = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                self.label, attrs
            )
            size = text.size()
            margin = 16
            text.drawAtPoint_(
                AppKit.NSMakePoint(w - size.width - margin, h - size.height - margin)
            )

    def _stroke_perimeter(self, rect, fraction: float, color, line_width: float) -> None:
        if fraction <= 0:
            return
        x = rect.origin.x
        y = rect.origin.y
        w = rect.size.width
        h = rect.size.height
        perimeter = 2 * (w + h)
        length = fraction * perimeter
        color.set()
        path = NSBezierPath.bezierPath()
        path.setLineWidth_(line_width)
        path.setLineCapStyle_(AppKit.NSLineCapStyleButt)
        path.setLineJoinStyle_(AppKit.NSLineJoinStyleMiter)
        segments = [
            ((x, y), (x + w, y)),
            ((x + w, y), (x + w, y + h)),
            ((x + w, y + h), (x, y + h)),
            ((x, y + h), (x, y)),
        ]
        remaining = length
        path.moveToPoint_(segments[0][0])
        for (start, end) in segments:
            seg_len = abs(end[0] - start[0]) + abs(end[1] - start[1])
            if remaining <= 0:
                break
            if remaining >= seg_len:
                path.lineToPoint_(end)
                remaining -= seg_len
            else:
                t = remaining / seg_len if seg_len else 0
                partial = (
                    start[0] + t * (end[0] - start[0]),
                    start[1] + t * (end[1] - start[1]),
                )
                path.lineToPoint_(partial)
                remaining = 0
        path.stroke()


class CountdownWindow(AppKit.NSWindow):
    def initWithScreen_redZone_(self, screen, red_zone: float):
        frame = screen.frame()
        self = objc.super(CountdownWindow, self).initWithContentRect_styleMask_backing_defer_(
            frame,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        if self is None:
            return None
        self.setLevel_(AppKit.NSStatusWindowLevel + 2)
        self.setOpaque_(False)
        self.setBackgroundColor_(NSColor.clearColor())
        self.setIgnoresMouseEvents_(True)
        self.setHasShadow_(False)
        self.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | AppKit.NSWindowCollectionBehaviorStationary
        )
        view = CountdownView.alloc().initWithFrame_redZone_(
            AppKit.NSMakeRect(0, 0, frame.size.width, frame.size.height), red_zone
        )
        self.setContentView_(view)
        self._view = view
        return self

    def setProgress_(self, fraction: float) -> None:
        self._view.setProgress_(fraction)

    def setLabel_(self, label: str) -> None:
        self._view.setLabel_(label)


class FocusShaker:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._total_seconds = 1.0
        self._phase = 0.0
        self._dx = 0.0
        self._dy = 0.0
        self._ax_window = None
        self._ax_origin: AppKit.NSPoint | None = None
        self._ax_enabled = _HAS_ACCESSIBILITY
        self._warned_no_target = False
        self._warned_no_access = False
        self._active_app_name: str | None = None

    def set_total_seconds(self, total: float) -> None:
        self._total_seconds = max(1.0, total)

    def update(self, remaining_sec: float, dt_seconds: float) -> None:
        if not _HAS_ACCESSIBILITY:
            if not self._warned_no_access:
                self._warned_no_access = True
                print(
                    "Shake disabled: install pyobjc-framework-ApplicationServices",
                    file=sys.stderr,
                    flush=True,
                )
            return

        c = self._cfg
        intensity = shake_intensity(remaining_sec, self._total_seconds, c)
        if intensity <= 0.0:
            self._restore()
            self._phase = 0.0
            self._dx = 0.0
            self._dy = 0.0
            self._active_app_name = None
            return

        if not self._ax_enabled:
            return

        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is not None:
            name = app.localizedName() or "?"
            if name != self._active_app_name:
                self._active_app_name = name
                print(f"Shake → {name}", flush=True)

        self._phase += dt_seconds * c.shake_speed * (0.4 + intensity * 0.6)
        wave = math.sin(self._phase) * 0.65 + math.sin(self._phase * 0.55 + 0.8) * 0.35
        target_dx = c.shake_max_x * wave * intensity * math.sin(self._phase * c.shake_speed_x)
        target_dy = c.shake_max_y * wave * intensity * math.cos(self._phase * c.shake_speed_y + 0.4)
        self._dx = _lerp(self._dx, target_dx, dt_seconds, c.shake_smooth)
        self._dy = _lerp(self._dy, target_dy, dt_seconds, c.shake_smooth)
        if not self._apply_shake() and not self._warned_no_target:
            self._warned_no_target = True
            print(
                "Shake: no focused window — click the app you want nudged.",
                file=sys.stderr,
                flush=True,
            )

    def restore(self) -> None:
        self._restore()
        self._phase = 0.0
        self._dx = 0.0
        self._dy = 0.0
        self._active_app_name = None

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

    def _apply_shake(self) -> bool:
        window = self._focused_window()
        if window is None:
            self._ax_window = None
            self._ax_origin = None
            return False
        if window != self._ax_window:
            self._restore()
            self._ax_window = window
            self._ax_origin = self._window_position(window)
        if self._ax_origin is None:
            return False
        point = AppKit.NSPoint(self._ax_origin.x + self._dx, self._ax_origin.y + self._dy)
        if not self._move_window(window, point):
            self._ax_enabled = False
            print(
                "Shake disabled: allow Accessibility for this terminal in "
                "System Settings → Privacy & Security → Accessibility.",
                file=sys.stderr,
                flush=True,
            )
            self._restore()
            return False
        return True

    def _window_position(self, window):
        err, value = AXUIElementCopyAttributeValue(window, "AXPosition", None)
        if err != 0 or value is None:
            return None
        ok, point = AXValueGetValue(value, kAXValueCGPointType, None)
        if not ok:
            return None
        return AppKit.NSPoint(point.x, point.y)

    def _move_window(self, window, point: AppKit.NSPoint) -> bool:
        value = AXValueCreate(kAXValueCGPointType, point)
        err = AXUIElementSetAttributeValue(window, "AXPosition", value)
        return err == 0

    def _restore(self) -> None:
        if _HAS_ACCESSIBILITY and self._ax_window is not None and self._ax_origin is not None:
            value = AXValueCreate(kAXValueCGPointType, self._ax_origin)
            AXUIElementSetAttributeValue(self._ax_window, "AXPosition", value)
        self._ax_window = None
        self._ax_origin = None


class _TimerBridge(AppKit.NSObject):
    def initWithHandler_(self, handler):
        self = objc.super(_TimerBridge, self).init()
        if self is None:
            return None
        self._handler = handler
        return self

    def tick_(self, _timer) -> None:
        self._handler()


class CountdownApp:
    def __init__(self, target: dt.datetime, cfg: AppConfig) -> None:
        self.target = target
        self.cfg = cfg
        self.started = dt.datetime.now()
        self.total_seconds = max(1.0, (target - self.started).total_seconds())
        self.windows: list[CountdownWindow] = []
        self._done = False
        self._interrupted = False
        self._blocked = False
        self._shaker = FocusShaker(cfg)
        self._shaker.set_total_seconds(self.total_seconds)
        self._display_fraction = 1.0
        self._last_frame = dt.datetime.now()
        self._timer = None
        self._timer_bridge = None
        self._stop_modal_active = False
        self._stop_controller = None
        self._stop_windows: list[StopBlockWindow] = []
        self._stop_click_down = False
        self._minimize_after_dismiss = False

    def run(self) -> bool:
        AppKit.NSApplication.sharedApplication()
        AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        signal.signal(signal.SIGINT, self._handle_sigint)

        for screen in AppKit.NSScreen.screens():
            window = CountdownWindow.alloc().initWithScreen_redZone_(screen, self.cfg.red_zone_fraction)
            window._view.stroke_width = self.cfg.stroke_width
            window.orderFrontRegardless()
            self.windows.append(window)

        self._tick()
        self._timer_bridge = _TimerBridge.alloc().initWithHandler_(self._on_tick)
        self._timer = AppKit.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            FRAME_INTERVAL, self._timer_bridge, "tick:", None, True
        )
        AppKit.NSRunLoop.currentRunLoop().addTimer_forMode_(
            self._timer, AppKit.NSRunLoopCommonModes
        )

        while not self._done:
            _pump_run_loop(FRAME_INTERVAL)
            if self._minimize_after_dismiss:
                self._minimize_after_dismiss = False
                self._minimize_apps_after_block()
            if self._stop_modal_active:
                self._poll_stop_modal_click()
            if self._stop_modal_active and self._stop_controller is not None:
                if self._interrupted or self._stop_controller.dismissed:
                    self._dismiss_stop_modal()

        self._teardown()
        return self._interrupted

    def _handle_sigint(self, _signum, _frame) -> None:
        self._interrupted = True
        if not self._blocked:
            self._done = True

    def _teardown(self) -> None:
        self._shaker.restore()
        if self._stop_controller is not None:
            self._stop_controller.remove_input_monitor()
        _close_stop_modal(self._stop_windows)
        self._stop_windows.clear()
        self._stop_controller = None
        for window in self.windows:
            window.orderOut_(None)
            window.close()
        self.windows.clear()

    def _on_tick(self) -> None:
        if self._stop_modal_active:
            return
        self._tick()
        if dt.datetime.now() >= self.target:
            if self.cfg.block_on_end:
                self._enter_stop_modal()
            else:
                self._done = True

    def _enter_stop_modal(self) -> None:
        if self._blocked:
            return
        self._blocked = True
        self._stop_modal_active = True
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        self._shaker.restore()
        for window in self.windows:
            window.orderOut_(None)
        self._stop_controller = _StopModalController.alloc().init()
        self._stop_windows = [
            StopBlockWindow.alloc().initWithScreen_controller_(screen, self._stop_controller)
            for screen in AppKit.NSScreen.screens()
        ]
        _front_stop_modal(self._stop_windows)
        self._stop_controller.install_input_monitor()

    def _poll_stop_modal_click(self) -> None:
        if self._stop_controller is None or not self._stop_controller.can_dismiss():
            return
        if AppKit.NSEvent.pressedMouseButtons() & 1:
            self._stop_click_down = True
        elif self._stop_click_down:
            self._stop_click_down = False
            self._stop_controller.dismiss()

    def _dismiss_stop_modal(self) -> None:
        """Close the overlay immediately; minimize windows on the next run-loop tick."""
        if self._stop_controller is not None:
            self._stop_controller.remove_input_monitor()
        _close_stop_modal(self._stop_windows)
        self._stop_windows.clear()
        self._stop_controller = None
        self._stop_modal_active = False
        AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        _pump_run_loop(0.05)
        self._minimize_after_dismiss = True

    def _minimize_apps_after_block(self) -> None:
        summary = _format_block_end_summary(apply_block_end_actions(self.cfg))
        if summary:
            print(summary, flush=True)
        self._done = True

    def _tick(self) -> None:
        now = dt.datetime.now()
        dt_seconds = max(FRAME_INTERVAL, (now - self._last_frame).total_seconds())
        self._last_frame = now
        remaining = max(0.0, (self.target - now).total_seconds())
        target_fraction = remaining / self.total_seconds
        self._display_fraction = _lerp(
            self._display_fraction, target_fraction, dt_seconds, DISPLAY_SMOOTH_RATE
        )
        label = format_duration(remaining)
        for window in self.windows:
            window.setProgress_(self._display_fraction)
            window.setLabel_(label)
        self._shaker.update(remaining, dt_seconds)


def _add_config_args(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("config (.env defaults, CLI overrides)")
    g.add_argument("--stroke-width", type=float, default=None)
    g.add_argument("--shake-before-mins", type=float, default=None, metavar="MIN")
    g.add_argument("--shake-start-fraction", type=float, default=None, metavar="0-1")
    g.add_argument("--shake-nudge-seconds", type=float, default=None)
    g.add_argument("--shake-nudge-level", type=float, default=None, metavar="0-1")
    g.add_argument("--shake-stop-before-mins", type=float, default=None, metavar="MIN")
    g.add_argument("--shake-max-x", type=float, default=None)
    g.add_argument("--shake-max-y", type=float, default=None)
    g.add_argument("--shake-speed", type=float, default=None)
    g.add_argument("--shake-speed-x", type=float, default=None)
    g.add_argument("--shake-speed-y", type=float, default=None)
    g.add_argument("--shake-smooth", type=float, default=None)
    g.add_argument("--red-zone-fraction", type=float, default=None, metavar="0-1")
    g.add_argument(
        "--block-on-end",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="At zero: show stop modal, then tidy windows (see BLOCK_END_* in .env)",
    )


def _cli_to_config(args: argparse.Namespace) -> AppConfig:
    base = AppConfig.from_env()
    return base.merge_cli(
        stroke_width=args.stroke_width,
        shake_before_mins=args.shake_before_mins,
        shake_start_fraction=args.shake_start_fraction,
        shake_nudge_seconds=args.shake_nudge_seconds,
        shake_nudge_level=args.shake_nudge_level,
        shake_stop_before_mins=args.shake_stop_before_mins,
        shake_max_x=args.shake_max_x,
        shake_max_y=args.shake_max_y,
        shake_speed=args.shake_speed,
        shake_speed_x=args.shake_speed_x,
        shake_speed_y=args.shake_speed_y,
        shake_smooth=args.shake_smooth,
        red_zone_fraction=args.red_zone_fraction,
        block_on_end=args.block_on_end,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen-edge countdown (macOS).")
    parser.add_argument("time", nargs="?", help="Target clock time, e.g. 6:00, 18:00")
    parser.add_argument("--at", dest="at", metavar="HH:MM", help="Target time (flag form)")
    parser.add_argument(
        "--for-minutes",
        type=float,
        default=None,
        metavar="MIN",
        help="Count down N minutes from now (instead of clock time)",
    )
    _add_config_args(parser)
    args = parser.parse_args()
    cfg = _cli_to_config(args)

    if args.for_minutes is not None:
        if args.time or args.at:
            parser.error("Use either --for-minutes or a clock time, not both")
        target = dt.datetime.now() + dt.timedelta(minutes=args.for_minutes)
    else:
        raw = args.time or args.at
        if not raw:
            parser.error("Provide a target time or --for-minutes")
        try:
            target = parse_target_time(raw)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1

    remaining = (target - dt.datetime.now()).total_seconds()
    if remaining <= 0:
        print("Target time is already in the past.", file=sys.stderr)
        return 1

    total = remaining
    print(
        f"Countdown → {target.strftime('%H:%M:%S')} ({format_duration(remaining)} remaining)",
        flush=True,
    )
    print(f"Shake: {_shake_window_desc(cfg, total)}", flush=True)
    if not _HAS_ACCESSIBILITY:
        print("Warning: shake needs pyobjc-framework-ApplicationServices.", file=sys.stderr, flush=True)
    else:
        print("Shake: frontmost app window.", flush=True)
    if cfg.block_on_end:
        print("Block on end: stop overlay — dismiss to tidy windows (see BLOCK_END_* in .env).", flush=True)
    print("Ctrl+C to quit.", flush=True)

    app = CountdownApp(target, cfg)
    if app.run():
        print("\nStopped.", flush=True)
        return 0

    if app._blocked and not app._interrupted:
        print("\nIt's time to stop.", flush=True)
        return 0
    print(f"\nDone — {target.strftime('%H:%M')} reached.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
