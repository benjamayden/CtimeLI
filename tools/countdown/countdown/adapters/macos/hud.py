"""HUD — the top-right timer label and Finish button.

Part of the CountdownOverlay port surface (docs/ports.md). The Finish button
latches a flag on a shared HudState that MacOverlay.finish_requested() reads.
"""

from __future__ import annotations

import AppKit
import objc
from Cocoa import NSFont


class HudState:
    """Shared flag set by any display's Finish button."""

    def __init__(self) -> None:
        self.finish_requested = False


class FinishControl(AppKit.NSView):
    """A small clickable 'Finish' control."""

    def initWithFrame_state_(self, frame, state):
        self = objc.super(FinishControl, self).initWithFrame_(frame)
        if self is None:
            return None
        self._state = state
        self._pressed = False
        return self

    def acceptsFirstMouse_(self, _event) -> bool:
        return True

    def mouseDown_(self, _event) -> None:
        self._pressed = True
        self.setNeedsDisplay_(True)
        if self._state is not None:
            self._state.finish_requested = True

    def mouseUp_(self, _event) -> None:
        self._pressed = False
        self.setNeedsDisplay_(True)

    def drawRect_(self, _rect) -> None:
        bounds = self.bounds()
        path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            bounds, 5.0, 5.0
        )
        shade = 0.38 if self._pressed else 0.24
        AppKit.NSColor.colorWithCalibratedWhite_alpha_(shade, 0.9).set()
        path.fill()
        attrs = {
            AppKit.NSFontAttributeName: NSFont.systemFontOfSize_weight_(
                12, AppKit.NSFontWeightMedium
            ),
            AppKit.NSForegroundColorAttributeName: (
                AppKit.NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.95)
            ),
        }
        text = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "Finish", attrs
        )
        size = text.size()
        text.drawAtPoint_(
            AppKit.NSMakePoint(
                (bounds.size.width - size.width) / 2,
                (bounds.size.height - size.height) / 2,
            )
        )


class CountdownHUDWindow(AppKit.NSWindow):
    """A small click-target window holding the timer label and Finish button."""

    def initWithScreen_state_(self, screen, state):
        screen_frame = screen.frame()
        hud_w, hud_h = 250.0, 32.0
        x = screen_frame.origin.x + screen_frame.size.width - hud_w - 16.0
        y = screen_frame.origin.y + 16.0
        frame = AppKit.NSMakeRect(x, y, hud_w, hud_h)
        self = objc.super(
            CountdownHUDWindow, self
        ).initWithContentRect_styleMask_backing_defer_(
            frame,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        if self is None:
            return None
        self._button_down = False
        self.setLevel_(AppKit.NSStatusWindowLevel + 3)
        self.setOpaque_(False)
        self.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.setIgnoresMouseEvents_(False)
        self.setHasShadow_(False)
        self.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | AppKit.NSWindowCollectionBehaviorStationary
        )
        btn_w, btn_h = 64.0, 24.0
        self._label = AppKit.NSTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 4, hud_w - btn_w - 8, hud_h - 8)
        )
        self._label.setBezeled_(False)
        self._label.setDrawsBackground_(False)
        self._label.setEditable_(False)
        self._label.setSelectable_(False)
        self._label.setAlignment_(AppKit.NSTextAlignmentRight)
        self._label.setFont_(
            NSFont.monospacedDigitSystemFontOfSize_weight_(13, AppKit.NSFontWeightMedium)
        )
        self._label.setTextColor_(
            AppKit.NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.95)
        )
        self._finish_btn = FinishControl.alloc().initWithFrame_state_(
            AppKit.NSMakeRect(hud_w - btn_w, (hud_h - btn_h) / 2, btn_w, btn_h), state
        )
        content = AppKit.NSView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, hud_w, hud_h)
        )
        content.addSubview_(self._label)
        content.addSubview_(self._finish_btn)
        self.setContentView_(content)
        return self

    def canBecomeKeyWindow(self) -> bool:
        return False

    def canBecomeMainWindow(self) -> bool:
        return False

    @objc.python_method
    def poll_finish_click(self, state: HudState) -> None:
        """Polling fallback — fires when mouseDown_ is missed (non-key window)."""
        btn_pressed = bool(AppKit.NSEvent.pressedMouseButtons() & 1)
        if not btn_pressed:
            self._button_down = False
            return
        if self._button_down or self._finish_btn.isHidden():
            return
        self._button_down = True
        point = AppKit.NSEvent.mouseLocation()
        btn_rect = self._finish_btn.convertRect_toView_(self._finish_btn.bounds(), None)
        screen_rect = self.convertRectToScreen_(btn_rect)
        if AppKit.NSMouseInRect(point, screen_rect, False):
            state.finish_requested = True

    def setLabel_(self, label: str) -> None:
        self._label.setStringValue_(label)

    def setFinishHidden_(self, hidden: bool) -> None:
        self._finish_btn.setHidden_(hidden)
