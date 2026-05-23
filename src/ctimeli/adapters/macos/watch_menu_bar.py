"""MacWatchMenuBar — the WatchMenuBar port via NSStatusBar.

Menu bar status item with Start/Add prompts and Quit. See docs/ports.md.
"""

from __future__ import annotations

import AppKit
import objc

from ctimeli import ports
from ctimeli.adapters.macos.runloop import pump_run_loop

_MENU_WIDTH = 200.0
_FIELD_HEIGHT = 24.0
_DISPLAY_UNSET = object()


class _WatchAppDelegate(AppKit.NSObject):
    """NSApplication delegate + status-item menu commands."""

    def initWithMenuBar_(self, menu_bar):
        self = objc.super(_WatchAppDelegate, self).init()
        if self is None:
            return None
        self._menu_bar = menu_bar
        return self

    def applicationDidFinishLaunching_(self, _notification) -> None:
        menu_bar = self._menu_bar
        if menu_bar is not None:
            menu_bar._install_status_item()

    def applicationShouldTerminateAfterLastWindowClosed_(self, _sender) -> bool:
        return False

    def menuWillOpen_(self, _menu) -> None:
        menu_bar = self._menu_bar
        if menu_bar is not None:
            menu_bar._menu_open = True
            menu_bar._refresh_menu()

    def menuDidClose_(self, _menu) -> None:
        menu_bar = self._menu_bar
        if menu_bar is not None:
            menu_bar._menu_open = False

    def startTimer_(self, _sender) -> None:
        menu_bar = self._menu_bar
        if menu_bar is None:
            return
        minutes = menu_bar._prompt_minutes("Start timer")
        if minutes is not None:
            menu_bar._enqueue_action(
                ports.WatchMenuAction(kind="start_minutes", minutes=minutes)
            )

    def addTime_(self, _sender) -> None:
        menu_bar = self._menu_bar
        if menu_bar is None:
            return
        minutes = menu_bar._prompt_minutes("Add time")
        if minutes is not None:
            menu_bar._enqueue_action(
                ports.WatchMenuAction(kind="extend_minutes", minutes=minutes)
            )

    def quitWatch_(self, _sender) -> None:
        if self._menu_bar is not None:
            self._menu_bar._enqueue_action(ports.WatchMenuAction(kind="quit"))


class MacWatchMenuBar:
    """Menu bar control surface for watch mode."""

    def __init__(self) -> None:
        self._status_item = None
        self._delegate = None
        self._menu = None
        self._start_item = None
        self._add_item = None
        self._actions: list[ports.WatchMenuAction] = []
        self._idle = True
        self._extend_enabled = True
        self._display_label = _DISPLAY_UNSET
        self._menu_open = False

    def show(self) -> None:
        """Install the status item after Cocoa finishes launching."""
        if self._status_item is not None:
            return
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        self._delegate = _WatchAppDelegate.alloc().initWithMenuBar_(self)
        app.setDelegate_(self._delegate)
        app.finishLaunching()
        if self._status_item is None:
            self._install_status_item()
        pump_run_loop(0.15)

    def teardown(self) -> None:
        if self._status_item is not None:
            self._status_item.setMenu_(None)
            AppKit.NSStatusBar.systemStatusBar().removeStatusItem_(self._status_item)
            self._status_item = None
        self._delegate = None
        self._menu = None
        self._start_item = None
        self._add_item = None

    def poll_actions(self) -> list[ports.WatchMenuAction]:
        actions = self._actions
        self._actions = []
        return actions

    def is_menu_open(self) -> bool:
        return self._menu_open

    def set_status(self, *, label: str | None) -> None:
        if self._status_item is None:
            return
        if self._display_label is not _DISPLAY_UNSET and label == self._display_label:
            return
        self._display_label = label
        button = self._status_item.button()
        if button is None:
            return
        if label:
            self._status_item.setLength_(AppKit.NSVariableStatusItemLength)
            button.setTitle_(label)
            button.setImagePosition_(AppKit.NSImageLeading)
        else:
            square = getattr(AppKit, "NSSquareStatusItemLength", -2)
            self._status_item.setLength_(square)
            button.setTitle_("")
            button.setImagePosition_(AppKit.NSImageOnly)

    def set_idle(self, idle: bool) -> None:
        if idle == self._idle:
            return
        self._idle = idle
        self._refresh_menu()

    def set_extend_enabled(self, enabled: bool) -> None:
        if enabled == self._extend_enabled:
            return
        self._extend_enabled = enabled
        self._refresh_menu()

    @objc.python_method
    def _install_status_item(self) -> None:
        if self._status_item is not None:
            return
        if self._delegate is None:
            self._delegate = _WatchAppDelegate.alloc().initWithMenuBar_(self)
        square = getattr(AppKit, "NSSquareStatusItemLength", -2)
        self._status_item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(
            square
        )
        self._status_item.setVisible_(True)
        self._build_menu()
        self._configure_button()
        self._refresh_menu()
        self._display_label = _DISPLAY_UNSET

    @objc.python_method
    def _configure_button(self) -> None:
        button = self._status_item.button() if self._status_item is not None else None
        if button is None:
            self._status_item.setTitle_("")
            self._status_item.setHighlightMode_(True)
            self._status_item.setMenu_(self._menu)
            return

        button.setTitle_("")
        image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "timer", "CtimeLI watch"
        )
        if image is None:
            image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "clock", "CtimeLI watch"
            )
        if image is not None:
            image.setTemplate_(True)
            button.setImage_(image)
            button.setImagePosition_(AppKit.NSImageOnly)
        self._status_item.setMenu_(self._menu)

    @objc.python_method
    def _build_menu(self) -> None:
        self._menu = AppKit.NSMenu.alloc().init()
        self._menu.setDelegate_(self._delegate)
        self._start_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Start timer…", "startTimer:", ""
        )
        self._start_item.setTarget_(self._delegate)
        self._menu.addItem_(self._start_item)

        self._add_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Add time…", "addTime:", ""
        )
        self._add_item.setTarget_(self._delegate)
        self._menu.addItem_(self._add_item)

        self._menu.addItem_(AppKit.NSMenuItem.separatorItem())

        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit watch mode", "quitWatch:", ""
        )
        quit_item.setTarget_(self._delegate)
        self._menu.addItem_(quit_item)

    @objc.python_method
    def _refresh_menu(self) -> None:
        if self._add_item is None:
            return
        show_add = not self._idle and self._extend_enabled
        self._add_item.setHidden_(not show_add)
        self._add_item.setEnabled_(show_add)

    @objc.python_method
    def _prompt_minutes(self, title: str) -> float | None:
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        pump_run_loop(0.05)
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_("Minutes from now:")
        alert.addButtonWithTitle_("OK")
        alert.addButtonWithTitle_("Cancel")
        field = AppKit.NSTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, _MENU_WIDTH, _FIELD_HEIGHT)
        )
        field.setStringValue_("15")
        alert.setAccessoryView_(field)
        if alert.runModal() != AppKit.NSAlertFirstButtonReturn:
            return None
        try:
            minutes = float((field.stringValue() or "").strip())
        except ValueError:
            return None
        if minutes <= 0:
            return None
        return minutes

    @objc.python_method
    def _enqueue_action(self, action: ports.WatchMenuAction) -> None:
        self._actions.append(action)
