"""MacScheduler — the FrameScheduler port on macOS.

The runner owns the frame loop and drives ticks itself; this adapter only
drains the AppKit run loop so the overlay windows repaint. No NSTimer is
needed (edge-cases #11).
"""

from __future__ import annotations

import AppKit


def pump_run_loop(seconds: float) -> None:
    """Run the loop briefly without manually dequeuing events.

    Manual nextEventMatchingMask dequeuing has crashed PyObjC; runMode:beforeDate:
    is the safe form. Both event-tracking and default modes are pumped so a
    drag in progress does not starve normal redraws.
    """
    deadline = AppKit.NSDate.dateWithTimeIntervalSinceNow_(seconds)
    for mode in (AppKit.NSEventTrackingRunLoopMode, AppKit.NSDefaultRunLoopMode):
        AppKit.NSRunLoop.currentRunLoop().runMode_beforeDate_(mode, deadline)


class MacScheduler:
    """Yields to the AppKit run loop between frames."""

    def pump(self, seconds: float) -> None:
        pump_run_loop(seconds)

    def stop(self) -> None:
        # Nothing retained — the run loop is process-global.
        pass
