"""MacOverlay — the CountdownOverlay port: stroke + edge glow + HUD.

Renders a RenderFrame on one borderless, click-through window per display.
All drawing lives here; all *decisions* (fraction, colour, glow) were made by
the domain. See docs/ports.md and edge-cases.md "Unverified surface".
"""

from __future__ import annotations

import math

import AppKit
import objc
from Cocoa import NSBezierPath, NSColor, NSMakeRect

from countdown import ports
from countdown.domain.config import AppConfig
from countdown.domain.session import RenderFrame

from .hud import CountdownHUDWindow, HudState


def _stroke_perimeter(rect, fraction: float, color, line_width: float) -> None:
    """Draw `fraction` of the rectangle perimeter, clockwise from bottom-left."""
    if fraction <= 0:
        return
    x, y = rect.origin.x, rect.origin.y
    w, h = rect.size.width, rect.size.height
    length = fraction * 2 * (w + h)
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
    for start, end in segments:
        seg_len = abs(end[0] - start[0]) + abs(end[1] - start[1])
        if remaining <= 0:
            break
        if remaining >= seg_len:
            path.lineToPoint_(end)
            remaining -= seg_len
        else:
            t = remaining / seg_len if seg_len else 0
            path.lineToPoint_(
                (start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1]))
            )
            remaining = 0
    path.stroke()


def _draw_soft_strip(rx, ry, rw, rh, r, g, b, peak_alpha, direction) -> None:
    """Soft edge glow via stacked fills — NSGradient crashes on Py 3.14 (#19)."""
    bands = 7
    band_h = rh / bands
    band_w = rw / bands
    for i in range(bands):
        alpha = peak_alpha * (1.0 - (i + 0.5) / bands) ** 1.4
        if alpha < 0.004:
            continue
        NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, alpha).setFill()
        if direction == "down":
            NSBezierPath.fillRect_(NSMakeRect(rx, ry + band_h * i, rw, band_h + 0.5))
        elif direction == "up":
            NSBezierPath.fillRect_(
                NSMakeRect(rx, ry + rh - band_h * (i + 1), rw, band_h + 0.5)
            )
        elif direction == "right":
            NSBezierPath.fillRect_(NSMakeRect(rx + band_w * i, ry, band_w + 0.5, rh))
        else:
            NSBezierPath.fillRect_(
                NSMakeRect(rx + rw - band_w * (i + 1), ry, band_w + 0.5, rh)
            )


def _draw_edge_pulse(rect, rgb, opacity, spread, phase, depths, visual_power) -> None:
    """Bloom a flowing glow inward from all four edges."""
    if opacity < 0.02 and spread < 0.01:
        return
    depth_min, depth_max, max_opacity = depths
    spread_vis = spread ** max(0.1, visual_power)
    depth = depth_min + (depth_max - depth_min) * spread_vis
    if depth < 1.0 and opacity < 0.02:
        return

    r, g, b = rgb
    x, y, w, h = rect.origin.x, rect.origin.y, rect.size.width, rect.size.height
    segments = 16
    step = 1.0 / segments
    overlap = 3.0
    for edge_name, edge_phase in (
        ("bottom", 0.0),
        ("right", math.pi * 0.5),
        ("top", math.pi),
        ("left", math.pi * 1.5),
    ):
        for i in range(segments):
            t = (i + 0.5) * step
            flow = 0.54 + 0.46 * math.sin(
                phase * 0.75 + edge_phase + t * math.pi * 2.0 * 1.35
            )
            band = opacity * flow
            if band < 0.014:
                continue
            alpha = min(max_opacity, band * 0.95)
            if edge_name == "bottom":
                sx, sw = x + t * w, w * step + overlap
                _draw_soft_strip(sx - sw / 2, y + h - depth, sw, depth, r, g, b, alpha, "up")
            elif edge_name == "top":
                sx, sw = x + t * w, w * step + overlap
                _draw_soft_strip(sx - sw / 2, y, sw, depth, r, g, b, alpha, "down")
            elif edge_name == "right":
                sy, sh = y + t * h, h * step + overlap
                _draw_soft_strip(x + w - depth, sy - sh / 2, depth, sh, r, g, b, alpha, "left")
            else:
                sy, sh = y + t * h, h * step + overlap
                _draw_soft_strip(x, sy - sh / 2, depth, sh, r, g, b, alpha, "right")


class CountdownView(AppKit.NSView):
    """Draws one display's stroke and edge glow from the latest RenderFrame."""

    def initWithFrame_config_(self, frame, cfg: AppConfig):
        self = objc.super(CountdownView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._cfg = cfg
        self._fraction = 1.0
        self._rgb = (0.2, 0.75, 1.0)
        self._pulse_opacity = 0.0
        self._pulse_spread = 0.0
        self._pulse_phase = 0.0
        return self

    def isFlipped(self) -> bool:
        return True

    @objc.python_method
    def render_frame(self, frame: RenderFrame) -> None:
        """Plain Python entry point — called by MacOverlay each tick."""
        self._fraction = max(0.0, min(1.0, frame.fraction))
        self._rgb = (frame.color.r, frame.color.g, frame.color.b)
        self._pulse_opacity = max(0.0, min(1.0, frame.pulse_opacity))
        self._pulse_spread = max(0.0, min(1.0, frame.pulse_spread))
        self._pulse_phase = frame.pulse_phase
        self.setNeedsDisplay_(True)

    def drawRect_(self, _rect) -> None:
        cfg = self._cfg
        bounds = self.bounds()
        inner = NSMakeRect(0, 0, bounds.size.width, bounds.size.height)
        if self._pulse_opacity >= 0.02 or self._pulse_spread >= 0.01:
            _draw_edge_pulse(
                inner,
                self._rgb,
                self._pulse_opacity,
                self._pulse_spread,
                self._pulse_phase,
                (cfg.pulse_depth_min, cfg.pulse_depth_max, cfg.pulse_max_opacity),
                cfg.pulse_visual_power,
            )
        if self._fraction > 0:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(*self._rgb, 0.95)
            _stroke_perimeter(inner, self._fraction, color, cfg.stroke_width)


class CountdownWindow(AppKit.NSWindow):
    """A borderless, click-through overlay window covering one display."""

    def initWithScreen_config_(self, screen, cfg: AppConfig):
        frame = screen.frame()
        self = objc.super(
            CountdownWindow, self
        ).initWithContentRect_styleMask_backing_defer_(
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
        self.setIgnoresMouseEvents_(True)  # the stroke is click-through
        self.setHasShadow_(False)
        self.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | AppKit.NSWindowCollectionBehaviorStationary
        )
        view = CountdownView.alloc().initWithFrame_config_(
            AppKit.NSMakeRect(0, 0, frame.size.width, frame.size.height), cfg
        )
        self.setContentView_(view)
        self.countdown_view = view
        return self

    def canBecomeKeyWindow(self) -> bool:
        return False

    def canBecomeMainWindow(self) -> bool:
        return False


class MacOverlay:
    """The CountdownOverlay port — one stroke window + HUD per display."""

    def __init__(self, config: AppConfig, logger: ports.Logger) -> None:
        self._cfg = config
        self._logger = logger
        self._windows: list[CountdownWindow] = []
        self._huds: list[CountdownHUDWindow] = []
        self._hud_state = HudState()
        self._shown = False

    def show(self) -> None:
        if self._shown:
            return
        self._shown = True
        for screen in AppKit.NSScreen.screens():
            window = CountdownWindow.alloc().initWithScreen_config_(screen, self._cfg)
            window.orderFront_(None)
            self._windows.append(window)
            hud = CountdownHUDWindow.alloc().initWithScreen_state_(
                screen, self._hud_state
            )
            hud.orderFront_(None)
            self._huds.append(hud)

    def render(self, frame: RenderFrame) -> None:
        for window in self._windows:
            window.countdown_view.render_frame(frame)
        for hud in self._huds:
            hud.setLabel_(frame.label)

    def finish_requested(self) -> bool:
        if not self._hud_state.finish_requested:
            for hud in self._huds:
                if hud.isVisible():
                    hud.poll_finish_click(self._hud_state)
        return self._hud_state.finish_requested

    def hide(self) -> None:
        for window in self._windows:
            window.orderOut_(None)
        for hud in self._huds:
            hud.setFinishHidden_(True)
            hud.orderOut_(None)

    def teardown(self) -> None:
        for window in self._windows:
            window.orderOut_(None)
            window.close()
        self._windows.clear()
        for hud in self._huds:
            hud.orderOut_(None)
            hud.close()
        self._huds.clear()
        self._shown = False
