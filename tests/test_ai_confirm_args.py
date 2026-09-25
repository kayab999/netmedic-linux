"""I-2/C-13: the AI confirmation must show the resolved verb AND concrete args.

A user authorizes an action, not a narrative. Attacker-controlled diagnostic
strings (SSID/hostname) must appear as inert text, never as instructions.
"""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from unittest.mock import MagicMock  # noqa: E402

from netmedic.ai_console import AIConsoleController  # noqa: E402


class _FakeAIWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="ai-confirm-test")
        self.is_destroyed = False
        self.overlay = Gtk.Overlay()
        self.add(self.overlay)
        self.asked = []
        self.busy = []
        self.logs = []

    def ask_confirmation(self, title, message):
        self.asked.append((title, message))
        return False

    def set_busy(self, busy, msg=""):
        self.busy.append((busy, msg))

    def append_log(self, text):
        self.logs.append(text)


def _make_ctrl(win=None):
    win = win or _FakeAIWindow()
    ctrl = AIConsoleController(win)
    ctrl.mount(win.overlay)
    ctrl.client = MagicMock()
    return win, ctrl


def _label_texts(widget):
    texts = []
    if isinstance(widget, Gtk.Label):
        texts.append(widget.get_text())
    if hasattr(widget, "get_children"):
        for child in widget.get_children():
            texts.extend(_label_texts(child))
    return texts


def test_preview_shows_verb_and_args():
    win, ctrl = _make_ctrl()
    try:
        ctrl._handle_pilot_response(
            {"status": "ok", "action": "change_dns", "params": {"server": "9.9.9.9"}}
        )
        texts = _label_texts(ctrl.preview_box)
        assert any("change_dns" in t for t in texts)
        assert any('"server"' in t and "9.9.9.9" in t for t in texts)
    finally:
        win.destroy()


def test_preview_neutralizes_markup_injection():
    win, ctrl = _make_ctrl()
    try:
        ctrl._handle_pilot_response(
            {
                "status": "ok",
                "action": "change_dns",
                "params": {"server": "<script>alert(1)</script>"},
            }
        )
        texts = _label_texts(ctrl.preview_box)
        # Literal text present (escaped, not interpreted as markup structure)
        assert any("<script>" in t for t in texts)
    finally:
        win.destroy()


def test_disruptive_dialog_includes_args_and_gates():
    win, ctrl = _make_ctrl()
    try:
        ctrl._confirm_and_execute("reset_tcp_ip_stack", {"force": True})
        assert win.asked
        title, message = win.asked[0]
        assert "reset_tcp_ip_stack" in title
        assert '"force"' in message
        ctrl.client.ask.assert_not_called()  # ask returned False
    finally:
        win.destroy()


def test_format_args_unit():
    assert AIConsoleController._format_args({}) == "{}"
    assert AIConsoleController._format_args({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'
    assert AIConsoleController._format_args(object()) != ""
