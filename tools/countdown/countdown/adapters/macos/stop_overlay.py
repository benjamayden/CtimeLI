"""MacStopOverlay — the StopOverlay port: the full-screen block-on-end modal.

Covers every display above the screen-saver window level until the user
dismisses it. A 0.6 s input lockout stops an in-flight keystroke from
dismissing it instantly (edge-cases #7). See docs/ports.md.
"""

from __future__ import annotations

import time

import AppKit
import objc
from Cocoa import NSColor

# Above the screen saver — a plain alert gets buried after a hide-all-windows.
_STOP_MODAL_LEVEL = AppKit.NSScreenSaverWindowLevel + 1
# Ignore input fired in the first moments while the overlay grabs focus.
_STOP_DISMISS_DELAY = 0.6
# (font size, weight, alpha) per displayed line, by index.
_LINE_STYLES = [
    (42, AppKit.NSFontWeightBold, 1.0),
    (18, AppKit.NSFontWeightRegular, 0.75),
    (16, AppKit.NSFontWeightMedium, 0.55),
]


class _StopModalController(AppKit.NSObject):
    """Tracks dismissal and owns the dismiss-lockout timer."""

    def init(self):
        self = objc.super(_StopModalController, self).init()
        if self is None:
            return None
        self.dismissed = False
        self._shown_at = time.monotonic()
        self._monitor = None
        return self

    @objc.python_method
    def can_dismiss(self) -> bool:
        return time.monotonic() - self._shown_at >= _STOP_DISMISS_DELAY

    @objc.python_method
    def dismiss(self) -> None:
        if self.can_dismiss():
            self.dismissed = True

    @objc.python_method
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

        mask = AppKit.NSLeftMouseDownMask | AppKit.NSKeyDownMask
        self._monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            mask, handle
        )

    @objc.python_method
    def remove_input_monitor(self) -> None:
        if self._monitor is not None:
            AppKit.NSEvent.removeMonitor_(self._monitor)
            self._monitor = None


class StopBlockView(AppKit.NSView):
    """The opaque modal surface — draws the message lines."""

    def initWithFrame_controller_lines_(self, frame, controller, lines):
        self = objc.super(StopBlockView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._controller = controller
        self._lines = list(lines)
        return self

    def isFlipped(self) -> bool:
        return True

    def acceptsFirstResponder(self) -> bool:
        return True

    def becomeFirstResponder(self) -> bool:
        return True

    def acceptsFirstMouse_(self, event) -> bool:
        # Deliver the click even when our app is not yet the active app.
        # Without this, the first click activates the app but mouseDown_ is
        # never called — the user must click twice to dismiss.
        return True

    def keyDown_(self, event) -> None:
        if self._controller is not None and event.keyCode() in (36, 53):
            self._controller.dismiss()
            return
        objc.super(StopBlockView, self).keyDown_(event)

    def mouseDown_(self, _event) -> None:
        if self._controller is not None:
            self._controller.dismiss()

    def drawRect_(self, _rect) -> None:
        NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.82).set()
        AppKit.NSBezierPath.fillRect_(self.bounds())

        width = self.bounds().size.width
        height = self.bounds().size.height
        rendered = []
        for index, text in enumerate(self._lines):
            size, weight, alpha = _LINE_STYLES[min(index, len(_LINE_STYLES) - 1)]
            attrs = {
                AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_weight_(
                    size, weight
                ),
                AppKit.NSForegroundColorAttributeName: (
                    NSColor.colorWithCalibratedWhite_alpha_(1.0, alpha)
                ),
            }
            attributed = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                text, attrs
            )
            rendered.append((attributed, attributed.size()))

        gap = 18
        total_h = sum(s.height for _, s in rendered) + gap * max(0, len(rendered) - 1)
        y = (height - total_h) / 2
        for attributed, size in rendered:
            attributed.drawAtPoint_(
                AppKit.NSMakePoint((width - size.width) / 2, y)
            )
            y += size.height + gap


class StopBlockWindow(AppKit.NSWindow):
    """A full-display modal window."""

    def initWithScreen_controller_lines_(self, screen, controller, lines):
        frame = screen.frame()
        self = objc.super(
            StopBlockWindow, self
        ).initWithContentRect_styleMask_backing_defer_(
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
        view = StopBlockView.alloc().initWithFrame_controller_lines_(
            AppKit.NSMakeRect(0, 0, frame.size.width, frame.size.height),
            controller,
            lines,
        )
        self.setContentView_(view)
        return self

    def canBecomeKeyWindow(self) -> bool:
        return True

    def canBecomeMainWindow(self) -> bool:
        return True


class MacStopOverlay:
    """The StopOverlay port — the block-on-end modal across all displays."""

    def __init__(self) -> None:
        self._controller: _StopModalController | None = None
        self._windows: list[StopBlockWindow] = []

    def show(self, lines: list[str]) -> None:
        self._controller = _StopModalController.alloc().init()
        self._windows = [
            StopBlockWindow.alloc().initWithScreen_controller_lines_(
                screen, self._controller, lines
            )
            for screen in AppKit.NSScreen.screens()
        ]
        # Order front first so the windows are visible during activation.
        for window in self._windows:
            window.orderFrontRegardless()
        # Use the macOS 14+ activate() API if available; fall back to the
        # deprecated ignoring-other-apps form on older systems.
        if hasattr(AppKit.NSApp, "activate") and callable(
            getattr(AppKit.NSApp, "activate", None)
        ):
            try:
                AppKit.NSApp.activate()
            except Exception:
                AppKit.NSApp.activateIgnoringOtherApps_(True)
        else:
            AppKit.NSApp.activateIgnoringOtherApps_(True)
        # Give the run loop one cycle to process the activation event before
        # trying to make the window key (makeKeyAndOrderFront_ requires the
        # app to be active).
        AppKit.NSRunLoop.currentRunLoop().runMode_beforeDate_(
            AppKit.NSDefaultRunLoopMode,
            AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.05),
        )
        for window in self._windows:
            window.makeKeyAndOrderFront_(None)
        if self._windows:
            self._windows[0].makeFirstResponder_(self._windows[0].contentView())
        self._controller.install_input_monitor()

    def dismissed(self) -> bool:
        return self._controller is not None and bool(self._controller.dismissed)

    def hide(self) -> None:
        if self._controller is not None:
            self._controller.remove_input_monitor()
        for window in self._windows:
            window.setIgnoresMouseEvents_(True)
            window.orderOut_(None)
            window.close()
        self._windows.clear()
        self._controller = None
