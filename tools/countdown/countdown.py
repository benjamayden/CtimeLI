#!/usr/bin/env python3
"""Terminal-activated countdown with a screen-edge stroke timer (macOS).

Usage:
    ./run 6:00
    ./run 15              # 15 minutes (quick input)
    ./run --for-minutes 25
    ./run watch           # watcher: auto-starts from calendar, or type 15 / 14:00
    cp .env.example .env   # tune shake + block-on-end + calendar

Config: .env in this directory (see .env.example). CLI flags override .env.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import math
import os
import select
import signal
import subprocess
import sys
import time

import AppKit
import objc
from Cocoa import NSBezierPath, NSColor, NSFont, NSMakeRect

from config import AppConfig, shake_intensity
from input_parse import parse_quick_input

try:
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
        AXUIElementSetAttributeValue,
        AXValueCreate,
        AXValueGetValue,
        CGEventCreate,
        CGEventGetLocation,
        kAXValueCGPointType,
    )

    _HAS_ACCESSIBILITY = True
except ImportError:
    _HAS_ACCESSIBILITY = False

try:
    from calendar_monitor import CalendarMonitor
except ImportError:
    CalendarMonitor = None  # type: ignore[misc, assignment]

STROKE_BLUE = (0.2, 0.75, 1.0)
STROKE_RED = (1.0, 0.12, 0.12)
FRAME_INTERVAL = 1.0 / 60.0
DISPLAY_SMOOTH_RATE = 9.0


def _mouse_location_cocoa() -> AppKit.NSPoint | None:
    """Mouse position in Cocoa screen coordinates (safe on main thread only)."""
    try:
        return AppKit.NSEvent.mouseLocation()
    except Exception:
        pass
    if not _HAS_ACCESSIBILITY:
        return None
    try:
        loc = CGEventGetLocation(CGEventCreate(None))
        primary = AppKit.NSScreen.screens()[0].frame()
        return AppKit.NSPoint(loc.x, primary.origin.y + primary.size.height - loc.y)
    except Exception:
        return None


def _finish_button_screen_rect(hud) -> AppKit.NSRect:
    rect = hud._finish_btn.convertRect_toView_(hud._finish_btn.bounds(), None)
    return hud.convertRectToScreen_(rect)


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _stroke_color_for_fraction(
    fraction: float,
    red_zone: float,
    stroke_base: tuple[float, float, float] = STROKE_BLUE,
):
    if fraction > red_zone:
        r, g, b = stroke_base
    else:
        t = _smoothstep(1.0 - (fraction / red_zone))
        r = stroke_base[0] + t * (STROKE_RED[0] - stroke_base[0])
        g = stroke_base[1] + t * (STROKE_RED[1] - stroke_base[1])
        b = stroke_base[2] + t * (STROKE_RED[2] - stroke_base[2])
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 0.95)


# TERM_PROGRAM values → macOS application names for activate / block-end skip.
_TERM_PROGRAM_TO_APP: dict[str, str] = {
    "Apple_Terminal": "Terminal",
    "iTerm.app": "iTerm2",
}


def calendar_block_target(event_start: dt.datetime, cfg: AppConfig) -> dt.datetime | None:
    """When block/shake/stroke zero should fire for a calendar event."""
    now = dt.datetime.now()
    block_at = event_start - dt.timedelta(minutes=cfg.calendar_block_before_mins)
    if block_at <= now:
        return None
    return block_at


def calendar_stroke_base(cfg: AppConfig) -> tuple[float, float, float]:
    return (cfg.calendar_stroke_r, cfg.calendar_stroke_g, cfg.calendar_stroke_b)


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


def _host_app_names() -> set[str]:
    names = set(_SKIP_SHAKE_APPS)
    term = os.environ.get("TERM_PROGRAM", "").strip()
    if term:
        names.add(term)
        mapped = _TERM_PROGRAM_TO_APP.get(term)
        if mapped:
            names.add(mapped)
    return names


def _shake_host_names() -> set[str]:
    return _host_app_names()


def _frontmost_pid() -> int | None:
    app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    name = (app.localizedName() or "").lower()
    if name in {"python", "org.python.python"}:
        return None
    return app.processIdentifier()


def _activate_pid(pid: int) -> bool:
    for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        if app.processIdentifier() == pid:
            return bool(
                app.activateWithOptions_(
                    AppKit.NSApplicationActivateIgnoringOtherApps
                    | AppKit.NSApplicationActivateAllWindows
                )
            )
    return False


def _activate_finder() -> None:
    subprocess.run(
        ["osascript", "-e", 'tell application "Finder" to activate'],
        capture_output=True,
        check=False,
    )


def _prepare_for_session_ui() -> None:
    AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)


def _set_watcher_idle_policy() -> None:
    AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyProhibited)
    AppKit.NSApp.hide_(None)


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
    "terminal": frozenset({"Terminal", "Apple_Terminal"}),
    "apple_terminal": frozenset({"Terminal", "Apple_Terminal"}),
    "cursor": frozenset({"Cursor"}),
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


def _running_app_names() -> list[str]:
    """All regular GUI apps — including those without visible windows."""
    ws = AppKit.NSWorkspace.sharedWorkspace()
    names: list[str] = []
    seen: set[str] = set()
    for app in ws.runningApplications():
        if app.activationPolicy() != AppKit.NSApplicationActivationPolicyRegular:
            continue
        name = app.localizedName() or ""
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _process_is_skipped(process: str, skip: frozenset[str]) -> bool:
    expanded = _expand_block_end_names(skip)
    if process in expanded:
        return True
    lower = process.lower()
    return lower in {name.lower() for name in expanded}


def _block_end_targets_process(process: str, cfg: AppConfig) -> bool:
    """True if .env block-end rules apply to this app (hide/minimize/quit)."""
    if _process_in_list(process, cfg.block_end_quit):
        return True
    if _process_in_list(process, cfg.block_end_hide):
        return True
    if _process_in_list(process, cfg.block_end_minimize):
        return True
    return False


def _app_name_for_pid(pid: int) -> str | None:
    for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        if app.processIdentifier() == pid:
            return app.localizedName()
    return None


def _should_restore_focus_pid(pid: int | None, cfg: AppConfig) -> bool:
    if pid is None:
        return False
    name = _app_name_for_pid(pid)
    if not name or _block_end_targets_process(name, cfg):
        return False
    return True


def _action_for_process(process: str, cfg: AppConfig, skip: frozenset[str]) -> str:
    if _process_is_skipped(process, skip):
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


def apply_block_end_actions(
    cfg: AppConfig,
    *,
    extra_skip: frozenset[str] = frozenset(),
) -> dict[str, int]:
    """Minimize, hide, or quit apps per .env when block-on-end overlay is dismissed."""
    skip = frozenset(_SYSTEM_SKIP_PROCESSES | cfg.block_end_skip | extra_skip)
    to_quit: list[str] = []
    to_hide: list[str] = []
    to_minimize: list[str] = []
    assigned: set[str] = set()

    def assign(process: str, action: str) -> None:
        if _process_is_skipped(process, skip) or process in assigned:
            return
        assigned.add(process)
        if action == "quit":
            to_quit.append(process)
        elif action == "hide":
            to_hide.append(process)
        elif action == "minimize":
            to_minimize.append(process)

    # Explicit .env lists — act on every matching running app, not just foreground.
    for process in _running_app_names():
        if _process_in_list(process, cfg.block_end_quit):
            assign(process, "quit")
        elif _process_in_list(process, cfg.block_end_hide):
            assign(process, "hide")
        elif _process_in_list(process, cfg.block_end_minimize):
            assign(process, "minimize")

    # Default action for visible apps not already assigned.
    for process in _foreground_process_names():
        if process in assigned or _process_is_skipped(process, skip):
            continue
        assign(process, cfg.block_end_default)

    counts = {"minimize": 0, "hide": 0, "quit": 0}
    failed_quit: list[str] = []

    for process in to_quit:
        if _quit_application(process):
            counts["quit"] += 1
        else:
            failed_quit.append(process)
            if _applescript_hide_processes([process]) > 0:
                counts["hide"] += 1

    counts["hide"] += _applescript_hide_processes(to_hide)
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
        window.setIgnoresMouseEvents_(True)
        window.orderOut_(None)
        window.close()
    _pump_run_loop(0.02)


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
    def initWithFrame_redZone_strokeBase_(self, frame, red_zone: float, stroke_base):
        self = objc.super(CountdownView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.remaining_fraction = 1.0
        self.stroke_width = 2.0
        self.inset = 0.0
        self.red_zone = red_zone
        self.stroke_base = stroke_base
        self.stroke_color = _stroke_color_for_fraction(1.0, red_zone, stroke_base)
        return self

    def setProgress_(self, fraction: float) -> None:
        self.remaining_fraction = max(0.0, min(1.0, fraction))
        self.stroke_color = _stroke_color_for_fraction(
            self.remaining_fraction, self.red_zone, self.stroke_base
        )
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
    def initWithScreen_redZone_strokeBase_(self, screen, red_zone: float, stroke_base):
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
        view = CountdownView.alloc().initWithFrame_redZone_strokeBase_(
            AppKit.NSMakeRect(0, 0, frame.size.width, frame.size.height),
            red_zone,
            stroke_base,
        )
        self.setContentView_(view)
        self._view = view
        return self

    def canBecomeKeyWindow(self) -> bool:
        return False

    def canBecomeMainWindow(self) -> bool:
        return False

    def setProgress_(self, fraction: float) -> None:
        self._view.setProgress_(fraction)


class FinishControl(AppKit.NSView):
    """Clickable Finish control — mouseDown/mouseUp like StopBlockView."""

    def initWithFrame_handler_(self, frame, handler):
        self = objc.super(FinishControl, self).initWithFrame_(frame)
        if self is None:
            return None
        self._handler = handler
        self._pressed = False
        return self

    def acceptsFirstMouse_(self, _event) -> bool:
        return True

    def mouseDown_(self, _event) -> None:
        self._pressed = True
        self.setNeedsDisplay_(True)
        if self._handler is not None:
            self._handler()

    def mouseUp_(self, event) -> None:
        self._pressed = False
        self.setNeedsDisplay_(True)

    def drawRect_(self, _rect) -> None:
        bounds = self.bounds()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, 5.0, 5.0)
        if self._pressed:
            NSColor.colorWithCalibratedWhite_alpha_(0.38, 0.92).set()
        else:
            NSColor.colorWithCalibratedWhite_alpha_(0.24, 0.88).set()
        path.fill()
        attrs = {
            AppKit.NSFontAttributeName: NSFont.systemFontOfSize_weight_(12, AppKit.NSFontWeightMedium),
            AppKit.NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.95),
        }
        text = AppKit.NSAttributedString.alloc().initWithString_attributes_("Finish", attrs)
        size = text.size()
        text.drawAtPoint_(
            AppKit.NSMakePoint(
                (bounds.size.width - size.width) / 2,
                (bounds.size.height - size.height) / 2,
            )
        )

    def setHidden_(self, hidden: bool) -> None:
        objc.super(FinishControl, self).setHidden_(hidden)


class CountdownHUDWindow(AppKit.NSWindow):
    """Small click-target for timer label + Finish — stroke overlay stays click-through."""

    def initWithScreen_finishHandler_(self, screen, finish_handler):
        sf = screen.frame()
        hud_w = 250.0
        hud_h = 32.0
        x = sf.origin.x + sf.size.width - hud_w - 16.0
        y = sf.origin.y + 16.0
        frame = AppKit.NSMakeRect(x, y, hud_w, hud_h)
        self = objc.super(CountdownHUDWindow, self).initWithContentRect_styleMask_backing_defer_(
            frame,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        if self is None:
            return None
        self.setLevel_(AppKit.NSStatusWindowLevel + 3)
        self.setOpaque_(False)
        self.setBackgroundColor_(NSColor.clearColor())
        self.setIgnoresMouseEvents_(False)
        self.setHasShadow_(False)
        self.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | AppKit.NSWindowCollectionBehaviorStationary
        )
        btn_w = 64.0
        btn_h = 24.0
        self._label = AppKit.NSTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 4, hud_w - btn_w - 8, hud_h - 8)
        )
        self._label.setBezeled_(False)
        self._label.setDrawsBackground_(False)
        self._label.setEditable_(False)
        self._label.setSelectable_(False)
        self._label.setAlignment_(AppKit.NSTextAlignmentRight)
        self._label.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(13, AppKit.NSFontWeightMedium))
        self._label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.95))
        self._finish_btn = FinishControl.alloc().initWithFrame_handler_(
            AppKit.NSMakeRect(hud_w - btn_w, (hud_h - btn_h) / 2, btn_w, btn_h),
            finish_handler,
        )
        content = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, hud_w, hud_h))
        content.addSubview_(self._label)
        content.addSubview_(self._finish_btn)
        self.setContentView_(content)
        return self

    def canBecomeKeyWindow(self) -> bool:
        return False

    def canBecomeMainWindow(self) -> bool:
        return False

    def setLabel_(self, label: str) -> None:
        self._label.setStringValue_(label)

    def setFinishHidden_(self, hidden: bool) -> None:
        self._finish_btn.setHidden_(hidden)


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
    def __init__(
        self,
        target: dt.datetime,
        cfg: AppConfig,
        *,
        watch_mode: bool = False,
        is_calendar: bool = False,
        event_start: dt.datetime | None = None,
        event_id: str | None = None,
        event_title: str | None = None,
    ) -> None:
        self.target = target
        self.cfg = cfg
        self.watch_mode = watch_mode
        self.is_calendar = is_calendar
        self.event_start = event_start
        self.event_id = event_id
        self.event_title = event_title
        self.started = dt.datetime.now()
        self.total_seconds = max(1.0, (target - self.started).total_seconds())
        self.stroke_base = calendar_stroke_base(cfg) if is_calendar else STROKE_BLUE
        self.windows: list[CountdownWindow] = []
        self.hud_windows: list[CountdownHUDWindow] = []
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
        self._finish_click_down = False
        self._minimize_after_dismiss = False
        self._setup_complete = False
        self._restore_focus_pid: int | None = None

    def retarget(
        self,
        new_target: dt.datetime,
        *,
        reason: str = "",
        event_start: dt.datetime | None = None,
    ) -> None:
        now = dt.datetime.now()
        if new_target <= now:
            return
        if event_start is not None:
            self.event_start = event_start
        self.target = new_target
        new_total = (new_target - self.started).total_seconds()
        if new_total > self.total_seconds:
            self.total_seconds = max(1.0, new_total)
            self._shaker.set_total_seconds(self.total_seconds)
        label = reason or "calendar event"
        if self.is_calendar and self.event_start is not None:
            print(
                f"Calendar → cleanup {new_target.strftime('%H:%M')} "
                f"(event {self.event_start.strftime('%H:%M')}, {label})",
                flush=True,
            )
        else:
            print(
                f"Calendar → {new_target.strftime('%H:%M')} ({label})",
                flush=True,
            )

    def finish_early(self) -> None:
        if self._done or self._stop_modal_active:
            return
        if self.cfg.block_on_end:
            self._enter_stop_modal()
        else:
            self._done = True

    def setup(self) -> None:
        if self._setup_complete:
            return
        _prepare_for_session_ui()
        handler = lambda: self.finish_early()
        for screen in AppKit.NSScreen.screens():
            window = CountdownWindow.alloc().initWithScreen_redZone_strokeBase_(
                screen, self.cfg.red_zone_fraction, self.stroke_base
            )
            window._view.stroke_width = self.cfg.stroke_width
            window.orderFront_(None)
            self.windows.append(window)
            hud = CountdownHUDWindow.alloc().initWithScreen_finishHandler_(screen, handler)
            hud.orderFront_(None)
            self.hud_windows.append(hud)
        self._tick()
        self._timer_bridge = _TimerBridge.alloc().initWithHandler_(self._on_tick)
        self._timer = AppKit.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            FRAME_INTERVAL, self._timer_bridge, "tick:", None, True
        )
        AppKit.NSRunLoop.currentRunLoop().addTimer_forMode_(
            self._timer, AppKit.NSRunLoopCommonModes
        )
        self._setup_complete = True

    def _poll_finish_click(self) -> None:
        """Detect Finish clicks on the main thread without NSEvent global monitors."""
        if self._done or self._stop_modal_active or not self.hud_windows:
            return
        if not (AppKit.NSEvent.pressedMouseButtons() & 1):
            self._finish_click_down = False
            return
        if self._finish_click_down:
            return
        self._finish_click_down = True
        point = _mouse_location_cocoa()
        if point is None:
            return
        for hud in self.hud_windows:
            if not hud.isVisible() or hud._finish_btn.isHidden():
                continue
            btn_rect = _finish_button_screen_rect(hud)
            if AppKit.NSMouseInRect(point, btn_rect, False):
                self.finish_early()
                return

    def pump_frame(self) -> bool:
        """Run one run-loop slice. Returns False when countdown is finished."""
        if self._minimize_after_dismiss:
            self._minimize_after_dismiss = False
            self._minimize_apps_after_block()
        if self._stop_modal_active:
            self._poll_stop_modal_click()
            if self._stop_controller is not None and (
                self._interrupted or self._stop_controller.dismissed
            ):
                self._dismiss_stop_modal()
        else:
            self._poll_finish_click()
        _pump_run_loop(FRAME_INTERVAL)
        return not self._done

    def run(self) -> bool:
        AppKit.NSApplication.sharedApplication()
        AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        signal.signal(signal.SIGINT, self._handle_sigint)
        self.setup()
        while not self._done:
            if not self.pump_frame():
                break
        self._teardown()
        return self._interrupted

    def stop(self) -> None:
        self._interrupted = True
        self._done = True
        self._teardown()

    def _handle_sigint(self, _signum, _frame) -> None:
        self._interrupted = True
        if not self._blocked:
            self._done = True

    def _teardown(self) -> None:
        if not self._setup_complete and not self.windows and not self.hud_windows:
            return
        self._shaker.restore()
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        if self._stop_controller is not None:
            self._stop_controller.remove_input_monitor()
        _close_stop_modal(self._stop_windows)
        self._stop_windows.clear()
        self._stop_controller = None
        self._stop_modal_active = False
        for window in self.windows:
            window.orderOut_(None)
            window.close()
        self.windows.clear()
        for hud in self.hud_windows:
            hud.orderOut_(None)
            hud.close()
        self.hud_windows.clear()
        self._setup_complete = False

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
        self._restore_focus_pid = _frontmost_pid()
        self._blocked = True
        self._stop_modal_active = True
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        self._shaker.restore()
        for window in self.windows:
            window.orderOut_(None)
        for hud in self.hud_windows:
            hud.orderOut_(None)
            hud.setFinishHidden_(True)
        self._stop_controller = _StopModalController.alloc().init()
        self._stop_windows = [
            StopBlockWindow.alloc().initWithScreen_controller_(screen, self._stop_controller)
            for screen in AppKit.NSScreen.screens()
        ]
        _front_stop_modal(self._stop_windows)

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
        for window in self.windows:
            window.orderOut_(None)
            window.close()
        self.windows.clear()
        for hud in self.hud_windows:
            hud.orderOut_(None)
            hud.close()
        self.hud_windows.clear()
        _set_watcher_idle_policy()
        _pump_run_loop(0.05)
        self._minimize_after_dismiss = True

    def _minimize_apps_after_block(self) -> None:
        summary = _format_block_end_summary(apply_block_end_actions(self.cfg))
        if summary:
            print(summary, flush=True)
        if self.watch_mode:
            print("Session ended — watcher ready (type 15 or q).", flush=True)
        restored = (
            _should_restore_focus_pid(self._restore_focus_pid, self.cfg)
            and _activate_pid(self._restore_focus_pid)
        )
        if not restored:
            _activate_finder()
        self._done = True

    def _hud_label(self, remaining: float) -> str:
        text = format_duration(remaining)
        if self.is_calendar and self.event_start is not None:
            text = f"{text} · {self.event_start.strftime('%H:%M')}"
        return text

    def _tick(self) -> None:
        now = dt.datetime.now()
        dt_seconds = max(FRAME_INTERVAL, (now - self._last_frame).total_seconds())
        self._last_frame = now
        remaining = max(0.0, (self.target - now).total_seconds())
        target_fraction = remaining / self.total_seconds
        self._display_fraction = _lerp(
            self._display_fraction, target_fraction, dt_seconds, DISPLAY_SMOOTH_RATE
        )
        label = self._hud_label(remaining)
        for window in self.windows:
            window.setProgress_(self._display_fraction)
        for hud in self.hud_windows:
            hud.setLabel_(label)
        self._shaker.update(remaining, dt_seconds)


def _enable_stdin_nonblocking() -> None:
    fd = sys.stdin.fileno()
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def _read_stdin_chunk() -> str | None:
    try:
        if not select.select([sys.stdin], [], [], 0)[0]:
            return None
        return sys.stdin.read()
    except (BlockingIOError, OSError):
        return None


class Watcher:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.countdown: CountdownApp | None = None
        self.calendar = CalendarMonitor(cfg) if CalendarMonitor is not None else None
        self._quit = False
        self._stdin_buf = ""
        self._last_cal_poll = 0.0
        self._finished_calendar_events: set[str] = set()

    def run(self) -> int:
        AppKit.NSApplication.sharedApplication()
        _set_watcher_idle_policy()
        signal.signal(signal.SIGINT, self._handle_sigint)
        _enable_stdin_nonblocking()

        if self.cfg.calendar_enabled and self.calendar is not None:
            self.calendar.ensure_access()
            if not self._start_from_nearest_event():
                print("Calendar: no accepted event in the next window.", flush=True)

        print("Watcher ready — enter 15, 14:00, or q to quit.", flush=True)
        if self.cfg.calendar_enabled:
            print(
                f"Calendar: auto-start within {self.cfg.calendar_window_minutes:.0f}m; "
                "snap while running.",
                flush=True,
            )
        if self.cfg.block_on_end:
            print("Block on end: stop overlay — dismiss to tidy windows.", flush=True)

        while not self._quit:
            self._poll_stdin()
            self._poll_calendar()
            if self.countdown is not None:
                if not self.countdown.pump_frame():
                    if (
                        self.countdown._blocked
                        and not self.countdown._interrupted
                        and not self.countdown.watch_mode
                    ):
                        print("\nIt's time to stop.", flush=True)
                    self.countdown._teardown()
                    if (
                        self.countdown.is_calendar
                        and self.countdown.event_id
                        and self.countdown._blocked
                        and not self.countdown._interrupted
                    ):
                        self._finished_calendar_events.add(self.countdown.event_id)
                    self.countdown = None
                    _set_watcher_idle_policy()
            else:
                _pump_run_loop(FRAME_INTERVAL)

        if self.countdown is not None:
            self.countdown.stop()
        return 0

    def _handle_sigint(self, _signum, _frame) -> None:
        self._quit = True
        if self.countdown is not None:
            self.countdown._interrupted = True
            self.countdown._done = True

    def _poll_stdin(self) -> None:
        chunk = _read_stdin_chunk()
        if chunk is None:
            return
        if chunk == "":
            self._quit = True
            return
        self._stdin_buf += chunk
        while "\n" in self._stdin_buf or "\r" in self._stdin_buf:
            line, sep, rest = self._stdin_buf.partition("\n")
            if not sep:
                line, sep, rest = self._stdin_buf.partition("\r")
            self._stdin_buf = rest
            line = line.strip()
            if line:
                self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        if line.lower() in {"q", "quit", "exit"}:
            self._quit = True
            return
        try:
            target = parse_quick_input(line)
        except ValueError as exc:
            print(exc, file=sys.stderr, flush=True)
            return
        remaining = (target - dt.datetime.now()).total_seconds()
        if remaining <= 0:
            print("Target time is already in the past.", file=sys.stderr, flush=True)
            return
        if self.countdown is not None:
            self.countdown.stop()
            self.countdown = None
        self._start_countdown_at(target)
        self._sync_calendar_to_nearest()

    def _start_countdown_at(
        self,
        target: dt.datetime,
        reason: str | None = None,
        *,
        is_calendar: bool = False,
        event_start: dt.datetime | None = None,
        event_id: str | None = None,
    ) -> None:
        remaining = (target - dt.datetime.now()).total_seconds()
        if remaining <= 0:
            return
        suffix = f" [{reason}]" if reason else ""
        if is_calendar and event_start is not None:
            print(
                f"Countdown → cleanup {target.strftime('%H:%M:%S')} "
                f"(event {event_start.strftime('%H:%M')}, "
                f"{format_duration(remaining)} remaining){suffix}",
                flush=True,
            )
        else:
            print(
                f"Countdown → {target.strftime('%H:%M:%S')} "
                f"({format_duration(remaining)} remaining){suffix}",
                flush=True,
            )
        self.countdown = CountdownApp(
            target,
            self.cfg,
            watch_mode=True,
            is_calendar=is_calendar,
            event_start=event_start,
            event_id=event_id,
            event_title=reason,
        )
        self.countdown.setup()

    def _calendar_block_at(self, event_start: dt.datetime) -> dt.datetime | None:
        return calendar_block_target(event_start, self.cfg)

    def _calendar_event_pending(self, event) -> bool:
        if event.event_id in self._finished_calendar_events:
            if dt.datetime.now() >= event.start:
                self._finished_calendar_events.discard(event.event_id)
            else:
                return False
        return self._calendar_block_at(event.start) is not None

    def _start_from_nearest_event(self) -> bool:
        if self.calendar is None or not self.cfg.calendar_enabled or self.countdown is not None:
            return False
        event = self.calendar.nearest_event_within()
        if event is None or not self._calendar_event_pending(event):
            return False
        block_at = self._calendar_block_at(event.start)
        if block_at is None:
            return False
        self._start_countdown_at(
            block_at,
            reason=event.title,
            is_calendar=True,
            event_start=event.start,
            event_id=event.event_id,
        )
        return True

    def _sync_calendar_to_nearest(self) -> None:
        if self.calendar is None or not self.cfg.calendar_enabled or self.countdown is None:
            return
        event = self.calendar.nearest_event_within()
        if event is None or not self._calendar_event_pending(event):
            return
        block_at = self._calendar_block_at(event.start)
        if block_at is None:
            return
        delta = abs((self.countdown.target - block_at).total_seconds())
        if delta > 1.0:
            self.countdown.is_calendar = True
            self.countdown.event_id = event.event_id
            self.countdown.event_title = event.title
            self.countdown.stroke_base = calendar_stroke_base(self.cfg)
            for window in self.countdown.windows:
                window._view.stroke_base = self.countdown.stroke_base
            self.countdown.retarget(
                block_at, reason=event.title, event_start=event.start
            )

    def _poll_calendar(self) -> None:
        if self.calendar is None or not self.cfg.calendar_enabled:
            return
        now = time.monotonic()
        if now - self._last_cal_poll < self.cfg.calendar_poll_seconds:
            return
        self._last_cal_poll = now
        if self.countdown is None or self.countdown._done:
            self._start_from_nearest_event()
            return
        event = self.calendar.nearest_event_within()
        if event is None or not self._calendar_event_pending(event):
            return
        block_at = self._calendar_block_at(event.start)
        if block_at is None:
            return
        delta = abs((self.countdown.target - block_at).total_seconds())
        if delta > 1.0:
            self.countdown.is_calendar = True
            self.countdown.event_id = event.event_id
            self.countdown.event_title = event.title
            self.countdown.stroke_base = calendar_stroke_base(self.cfg)
            for window in self.countdown.windows:
                window._view.stroke_base = self.countdown.stroke_base
            self.countdown.retarget(
                block_at, reason=event.title, event_start=event.start
            )


def _print_countdown_banner(cfg: AppConfig, target: dt.datetime, remaining: float) -> None:
    print(
        f"Countdown → {target.strftime('%H:%M:%S')} ({format_duration(remaining)} remaining)",
        flush=True,
    )
    print(f"Shake: {_shake_window_desc(cfg, remaining)}", flush=True)
    if not _HAS_ACCESSIBILITY:
        print("Warning: shake needs pyobjc-framework-ApplicationServices.", file=sys.stderr, flush=True)
    else:
        print("Shake: frontmost app window.", flush=True)
    if cfg.block_on_end:
        print("Block on end: stop overlay — dismiss to tidy windows (see BLOCK_END_* in .env).", flush=True)
    print("Ctrl+C to quit.", flush=True)


def _main_watch(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Watch mode — quick-add countdown timers.")
    _add_config_args(parser)
    args = parser.parse_args(argv)
    cfg = _cli_to_config(args)
    return Watcher(cfg).run()


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


def _main_countdown(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Screen-edge countdown (macOS).")
    parser.add_argument("time", nargs="?", help="Minutes (15), clock time (6:00), or --for-minutes")
    parser.add_argument("--at", dest="at", metavar="HH:MM", help="Target time (flag form)")
    parser.add_argument(
        "--for-minutes",
        type=float,
        default=None,
        metavar="MIN",
        help="Count down N minutes from now (instead of clock time)",
    )
    _add_config_args(parser)
    args = parser.parse_args(argv)
    cfg = _cli_to_config(args)

    if args.for_minutes is not None:
        if args.time or args.at:
            parser.error("Use either --for-minutes or a clock time, not both")
        target = dt.datetime.now() + dt.timedelta(minutes=args.for_minutes)
    else:
        raw = args.time or args.at
        if not raw:
            parser.error("Provide a target time, --for-minutes, or use: ./run watch")
        try:
            target = parse_quick_input(raw)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1

    remaining = (target - dt.datetime.now()).total_seconds()
    if remaining <= 0:
        print("Target time is already in the past.", file=sys.stderr)
        return 1

    _print_countdown_banner(cfg, target, remaining)
    app = CountdownApp(target, cfg)
    if app.run():
        print("\nStopped.", flush=True)
        return 0

    if app._blocked and not app._interrupted:
        print("\nIt's time to stop.", flush=True)
        return 0
    print(f"\nDone — {target.strftime('%H:%M')} reached.", flush=True)
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "watch":
        return _main_watch(argv[1:])
    return _main_countdown(argv)


if __name__ == "__main__":
    raise SystemExit(main())
