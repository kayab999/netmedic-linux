"""Regression: AI palette overlay must not steal clicks when hidden.

Gtk.Overlay children default to FILL alignment and participate in hit-testing
for their full allocation. A CROSSFADE Gtk.Revealer keeps its allocation while
only changing opacity, so without set_overlay_pass_through the invisible
palette blocks every button under it. Window chrome (titlebar) stays usable —
exactly the failure mode reported when function buttons did nothing.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from netmedic.ai_console import AIConsoleController  # noqa: E402


class _FakeMainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="overlay-test")
        self.is_destroyed = False
        self.overlay = Gtk.Overlay()
        self.add(self.overlay)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.overlay.add(content)
        self.btn = Gtk.Button(label="Action")
        content.pack_start(self.btn, True, True, 0)


def test_hidden_palette_passes_through_events():
    win = _FakeMainWindow()
    ctrl = AIConsoleController(win)
    ctrl.mount(win.overlay)
    win.show_all()

    try:
        assert ctrl.revealer.get_reveal_child() is False
        assert win.overlay.get_overlay_pass_through(ctrl.revealer) is True
        assert ctrl.revealer.get_valign() == Gtk.Align.START
        assert ctrl.revealer.get_vexpand() is False
    finally:
        win.destroy()


def test_visible_palette_receives_events():
    win = _FakeMainWindow()
    ctrl = AIConsoleController(win)
    ctrl.mount(win.overlay)
    win.show_all()

    try:
        ctrl._set_palette_visible(True)
        assert ctrl.revealer.get_reveal_child() is True
        assert win.overlay.get_overlay_pass_through(ctrl.revealer) is False

        ctrl._dismiss_palette()
        assert ctrl.revealer.get_reveal_child() is False
        assert win.overlay.get_overlay_pass_through(ctrl.revealer) is True
    finally:
        win.destroy()


def test_toggle_restores_pass_through():
    win = _FakeMainWindow()
    ctrl = AIConsoleController(win)
    ctrl.mount(win.overlay)
    win.show_all()

    try:
        ctrl._toggle_palette()
        assert win.overlay.get_overlay_pass_through(ctrl.revealer) is False
        ctrl._toggle_palette()
        assert win.overlay.get_overlay_pass_through(ctrl.revealer) is True
    finally:
        win.destroy()
