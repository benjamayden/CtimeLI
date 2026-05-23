"""MacScreenBlur — the ScreenBlur port: progressive full-screen frosted glass.

One borderless, click-through window per display, above the stroke/glow overlay
and below the HUD / block modal. See docs/ports.md.
"""

from __future__ import annotations

import AppKit
import objc
from Cocoa import NSColor, NSMakeRect

# Above stroke/glow (+2), below HUD (+4).
_BLUR_LEVEL = AppKit.NSStatusWindowLevel + 3


class _BlurView(AppKit.NSView):
    """NSVisualEffectView plus optional darkening for high intensities."""

    def initWithFrame_(self, frame):
        self = objc.super(_BlurView, self).initWithFrame_(frame)
        if self is None:
            return None
        effect = AppKit.NSVisualEffectView.alloc().initWithFrame_(frame)
        effect.setMaterial_(AppKit.NSVisualEffectMaterialHUDWindow)
        effect.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(AppKit.NSVisualEffectStateActive)
        effect.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        self.addSubview_(effect)
        self._effect = effect
        self._scrim = AppKit.NSView.alloc().initWithFrame_(frame)
        self._scrim.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        self._scrim.setWantsLayer_(True)
        self.addSubview_(self._scrim)
        self._intensity = 0.0
        return self

    @objc.python_method
    def set_intensity(self, amount: float) -> None:
        self._intensity = max(0.0, min(1.0, amount))
        # Fade the whole effect in; scrim adds extra obscuring near 1.0.
        self._effect.setAlphaValue_(self._intensity)
        scrim_alpha = max(0.0, (self._intensity - 0.35) / 0.65) * 0.55
        self._scrim.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedWhite_alpha_(0.0, scrim_alpha).CGColor()
        )


class BlurWindow(AppKit.NSWindow):
    """A full-display blur surface."""

    def initWithScreen_(self, screen):
        frame = screen.frame()
        self = objc.super(BlurWindow, self).initWithContentRect_styleMask_backing_defer_(
            frame,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        if self is None:
            return None
        self.setLevel_(_BLUR_LEVEL)
        self.setOpaque_(False)
        self.setBackgroundColor_(NSColor.clearColor())
        self.setIgnoresMouseEvents_(True)
        self.setHasShadow_(False)
        self.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | AppKit.NSWindowCollectionBehaviorStationary
        )
        view = _BlurView.alloc().initWithFrame_(
            NSMakeRect(0, 0, frame.size.width, frame.size.height)
        )
        self.setContentView_(view)
        self.blur_view = view
        return self

    def canBecomeKeyWindow(self) -> bool:
        return False

    def canBecomeMainWindow(self) -> bool:
        return False


class MacScreenBlur:
    """The ScreenBlur port — frosted glass across every display."""

    def __init__(self) -> None:
        self._windows: list[BlurWindow] = []
        self._shown = False
        self._intensity = 0.0

    def show(self) -> None:
        if self._shown:
            return
        self._shown = True
        for screen in AppKit.NSScreen.screens():
            window = BlurWindow.alloc().initWithScreen_(screen)
            window.blur_view.set_intensity(self._intensity)
            if self._intensity <= 0.0:
                window.orderOut_(None)
            else:
                window.orderFront_(None)
            self._windows.append(window)

    def set_intensity(self, amount: float) -> None:
        self._intensity = max(0.0, min(1.0, amount))
        for window in self._windows:
            window.blur_view.set_intensity(self._intensity)
            if self._intensity <= 0.0:
                window.orderOut_(None)
            elif not window.isVisible():
                window.orderFront_(None)

    def hide(self) -> None:
        for window in self._windows:
            window.orderOut_(None)

    def teardown(self, *, close: bool = True) -> None:
        for window in self._windows:
            window.orderOut_(None)
            if close:
                window.close()
        self._windows.clear()
        self._shown = False
        self._intensity = 0.0
