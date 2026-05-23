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
    is the safe form. Each mode gets its own slice — a single shared deadline lets
    the first mode consume the whole window and starve NSDefaultRunLoopMode, which
    is where status-bar clicks arrive (edge-cases #42).
    """
    if seconds <= 0:
        return
    run_loop = AppKit.NSRunLoop.currentRunLoop()
    modes = (
        AppKit.NSDefaultRunLoopMode,
        AppKit.NSEventTrackingRunLoopMode,
        AppKit.NSModalPanelRunLoopMode,
    )
    per_mode = seconds / len(modes)
    for mode in modes:
        deadline = AppKit.NSDate.dateWithTimeIntervalSinceNow_(per_mode)
        run_loop.runMode_beforeDate_(mode, deadline)


class MacScheduler:
    """Yields to the AppKit run loop between frames."""

    def pump(self, seconds: float) -> None:
        pump_run_loop(seconds)

    def stop(self) -> None:
        # Nothing retained — the run loop is process-global.
        pass


def run_cocoa_watch_loop(watch) -> int:
    """Drive WatchRunner on the real NSApplication event loop.

    Manual ``pump_run_loop`` slices cannot reliably deliver status-bar menu
    events; ``AppHelper.runEventLoop`` must own the main thread (edge-cases #42).
    """
    from PyObjCTools import AppHelper

    watch._startup()
    try:
        watch._announce()

        def tick() -> None:
            if not watch._tick_once(pump_idle=False, yield_loop=False):
                AppHelper.stopEventLoop()
                return
            AppHelper.callLater(watch.tick_interval(), tick)

        AppHelper.callLater(0, tick)
        AppHelper.runEventLoop()
    finally:
        watch._shutdown()
    return 0
