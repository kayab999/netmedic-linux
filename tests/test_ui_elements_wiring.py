"""Post-fix verification: every MainWindow / VPN / AI control is wired correctly.

Constructs a real GTK MainWindow (mocked IPC + NetworkMedic side effects) and
asserts labels, sensitivity, signal connections, overlay pass-through, busy
state, confirmation gates, and IPC action routing for each control.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import gi
import pytest

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # noqa: E402

from netmedic.models import NetResult  # noqa: E402
from netmedic.operators.base import OperatorStatus  # noqa: E402
from netmedic.operators.vpn.base import VPNClient  # noqa: E402

os.environ.setdefault("NO_AT_BRIDGE", "1")


def _run_idles_once():
    ctx = GLib.MainContext.default()
    # Bound iterations so we never spin forever.
    for _ in range(50):
        if not ctx.pending():
            break
        ctx.iteration(False)


@pytest.fixture
def main_window():
    """Build MainWindow with IPC bridge mocked and medic side effects neutered."""
    mock_bridge = MagicMock()
    mock_bridge.call.return_value = NetResult("Mock", True, "ok")
    mock_bridge.is_available.return_value = True

    # Execute GLib.idle_add callbacks immediately so busy UI updates are sync.
    def immediate_idle(cb, *args, **kwargs):
        try:
            cb(*args) if args else cb()
        except TypeError:
            return cb()
        return False

    with patch("netmedic.ui.NetworkMedic") as mock_medic_cls, patch(
        "netmedic.ui.WifiOperator"
    ), patch("netmedic.ui.GuiActionBridge", return_value=mock_bridge), patch(
        "netmedic.ui_vpn.GuiActionBridge", return_value=mock_bridge
    ), patch(
        "netmedic.ui_vpn.AngristanOperator"
    ), patch(
        "netmedic.ai_console.PilotClient"
    ), patch(
        "netmedic.ui.apply_theme"
    ), patch(
        "netmedic.ui.resolve_app_icon_path", return_value=None
    ), patch(
        "netmedic.ui.register_teardown"
    ), patch(
        "netmedic.ui.GLib.idle_add", side_effect=immediate_idle
    ), patch(
        "netmedic.ui_vpn.GLib.idle_add", side_effect=immediate_idle
    ):
        medic = MagicMock()
        medic.cleanup.return_value = NetResult("Cleanup", True, "ok")
        mock_medic_cls.return_value = medic

        from netmedic.ui import MainWindow

        win = MainWindow()
        win.actions = mock_bridge
        win.vpn_panel.actions = mock_bridge
        # Do not show_all() — avoids realize/map side effects in CI/headless.
        yield win, mock_bridge
        win.is_destroyed = True
        try:
            win.destroy()
        except Exception:
            pass
        _run_idles_once()


def test_header_and_chrome_present(main_window):
    win, _ = main_window
    assert win.get_title()
    assert win.get_titlebar() is not None
    assert isinstance(win.notebook, Gtk.Notebook)
    assert win.notebook.get_n_pages() == 2
    assert win.log_view is not None
    assert win.status_bar is not None
    assert win.spinner is not None
    assert win._root_overlay is not None
    assert win.actions is not None


def test_basic_repair_buttons_wired(main_window):
    win, _ = main_window
    expected = {
        "repair_btn": "SMART REPAIR (Safe)",
        "btn_diag": "Check Connectivity",
        "btn_dns": "Flush DNS",
        "btn_ip": "Renew IP Address",
        "btn_wifi": "Scan Wi-Fi Congestion",
    }
    for attr, label in expected.items():
        btn = getattr(win, attr)
        assert btn is not None, attr
        assert btn.get_sensitive() is True, attr
        assert btn.get_label() == label, f"{attr}: {btn.get_label()!r}"


def test_infrastructure_buttons_wired(main_window):
    win, _ = main_window
    expected = {
        "btn_stack": "Reset TCP/IP Stack",
        "btn_adapter": "Cycle Network Adapter",
        "btn_firewall": "Toggle Firewall (UFW)",
    }
    for attr, label in expected.items():
        btn = getattr(win, attr)
        assert btn.get_label() == label
        assert btn.get_sensitive() is True
        assert btn.get_style_context().has_class("destructive-action")


def test_busy_disables_all_action_buttons(main_window):
    win, _ = main_window
    win._update_busy_ui(True, "Busy")
    for attr in (
        "repair_btn",
        "btn_diag",
        "btn_dns",
        "btn_ip",
        "btn_wifi",
        "btn_stack",
        "btn_adapter",
        "btn_firewall",
    ):
        assert getattr(win, attr).get_sensitive() is False, attr
    assert win.notebook.get_sensitive() is False
    assert win.vpn_panel.get_sensitive() is False
    win._update_busy_ui(False, "Ready")
    for attr in (
        "repair_btn",
        "btn_diag",
        "btn_dns",
        "btn_ip",
        "btn_wifi",
        "btn_stack",
        "btn_adapter",
        "btn_firewall",
    ):
        assert getattr(win, attr).get_sensitive() is True, attr


def test_ipc_routing_diagnostics_flush_renew_wifi(main_window):
    win, bridge = main_window
    bridge.call.reset_mock()
    win._ipc_action("network_status")
    win._ipc_action("flush_dns")
    win._ipc_action("renew_ip")
    win._ipc_action("wifi_diagnostics")
    actions = [c.args[0] for c in bridge.call.call_args_list]
    assert actions == [
        "network_status",
        "flush_dns",
        "renew_ip",
        "wifi_diagnostics",
    ]


def test_handler_ipc_actions_via_run_async_mock(main_window):
    win, bridge = main_window
    bridge.call.reset_mock()

    def immediate(task_func, msg="..."):
        return task_func()

    with patch.object(win, "run_async_task", side_effect=immediate):
        win.on_diagnostics(None)
        win.on_flush_dns(None)
        win.on_renew_ip(None)
        win.on_scan_wifi(None)

    called = [c.args[0] for c in bridge.call.call_args_list]
    assert called == [
        "network_status",
        "flush_dns",
        "renew_ip",
        "wifi_diagnostics",
    ]


def test_destructive_handlers_require_confirmation(main_window):
    win, bridge = main_window
    bridge.call.reset_mock()

    def immediate(task_func, msg="..."):
        return task_func()

    with patch.object(win, "run_async_task", side_effect=immediate):
        with patch.object(win, "ask_confirmation", return_value=False):
            win.on_reset_tcp_ip(None)
            win.on_restart_adapter(None)
            win.on_toggle_firewall(None)
        assert bridge.call.call_count == 0

        with patch.object(win, "ask_confirmation", return_value=True):
            win.on_reset_tcp_ip(None)
            win.on_restart_adapter(None)
            win.on_toggle_firewall(None)

    called = [c.args[0] for c in bridge.call.call_args_list]
    assert called == [
        "reset_tcp_ip_stack",
        "restart_adapter",
        "toggle_firewall",
    ]


def test_smart_repair_sequence_actions(main_window):
    win, bridge = main_window
    bridge.call.reset_mock()
    bridge.call.side_effect = [
        NetResult(
            "Diagnostics",
            True,
            "Gateway Reachable | DNS Resolution OK | Internet Access OK",
        ),
        NetResult("Flush DNS", True, "flushed"),
        NetResult("Renew IP", True, "renewed"),
    ]
    captured = {}

    def capture(task_func, msg="..."):
        captured["result"] = task_func()
        return captured["result"]

    with patch.object(win, "run_async_task", side_effect=capture), patch.object(
        win, "append_log"
    ):
        win.on_smart_repair(None)

    assert captured["result"].success is True
    assert "all 3" in captured["result"].message
    assert [c.args[0] for c in bridge.call.call_args_list] == [
        "network_status",
        "flush_dns",
        "renew_ip",
    ]


def test_smart_repair_skips_renew_without_gateway(main_window):
    win, bridge = main_window
    bridge.call.reset_mock()
    bridge.call.side_effect = [
        NetResult(
            "Diagnostics",
            False,
            "Gateway Not Found | DNS Resolution Failed | No Internet Access",
        ),
        NetResult("Flush DNS", True, "flushed"),
    ]
    captured = {}

    def capture(task_func, msg="..."):
        captured["result"] = task_func()

    with patch.object(win, "run_async_task", side_effect=capture), patch.object(
        win, "append_log"
    ):
        win.on_smart_repair(None)

    actions = [c.args[0] for c in bridge.call.call_args_list]
    assert actions == ["network_status", "flush_dns"]
    assert "renew_ip" not in actions


def test_ai_overlay_pass_through_when_hidden(main_window):
    win, _ = main_window
    ai = win.ai_console
    assert ai.revealer is not None
    assert ai.revealer.get_reveal_child() is False
    assert win._root_overlay.get_overlay_pass_through(ai.revealer) is True
    ai._set_palette_visible(True)
    assert ai.revealer.get_reveal_child() is True
    assert win._root_overlay.get_overlay_pass_through(ai.revealer) is False
    ai._set_palette_visible(False)
    assert win._root_overlay.get_overlay_pass_through(ai.revealer) is True


def test_ai_palette_alignment_does_not_fill_vertically(main_window):
    win, _ = main_window
    rev = win.ai_console.revealer
    assert rev.get_valign() == Gtk.Align.START
    assert rev.get_vexpand() is False


def test_vpn_panel_controls_present(main_window):
    win, _ = main_window
    vpn = win.vpn_panel
    assert vpn.action_btn is not None
    assert vpn.btn_add.get_label() == "Add Client"
    assert vpn.btn_revoke.get_label() == "Revoke Selected"
    assert vpn.btn_refresh.get_label() == "Refresh"
    assert vpn.status_label is not None
    assert vpn.tree_view is not None
    assert vpn._state_loaded is False
    # starts disabled until status check
    assert vpn.action_btn.get_sensitive() is False


def test_tab_switch_triggers_vpn_refresh(main_window):
    win, _ = main_window
    with patch.object(win.vpn_panel, "refresh_state") as refresh:
        win._on_tab_switch(win.notebook, None, 1)
        refresh.assert_called_once()
        refresh.reset_mock()
        win.vpn_panel._state_loaded = True
        win.vpn_panel._needs_retry = False
        win._on_tab_switch(win.notebook, None, 1)
        refresh.assert_not_called()


def test_vpn_refresh_not_installed_enables_install(main_window):
    win, bridge = main_window
    vpn = win.vpn_panel
    bridge.call.reset_mock()
    bridge.call.return_value = NetResult(
        "VPN", True, OperatorStatus.NOT_INSTALLED.value
    )

    def run_async_inline(func, *args, callback=None):
        result = func(*args)
        if callback:
            callback(result)
        return result

    with patch.object(vpn, "run_async", side_effect=run_async_inline):
        vpn.refresh_state()

    assert bridge.call.call_args_list[0].args[0] == "vpn_status"
    assert vpn.action_btn.get_sensitive() is True
    assert "Install" in vpn.action_btn.get_label()
    assert vpn.clients_frame.get_sensitive() is False


def test_vpn_running_loads_clients_via_ipc(main_window):
    win, bridge = main_window
    vpn = win.vpn_panel
    bridge.call.reset_mock()

    def bridge_side_effect(action, params=None, confirmed=None):
        if action == "vpn_status":
            return NetResult("VPN", True, OperatorStatus.RUNNING.value)
        if action == "vpn_list_clients":
            return NetResult(
                "VPN",
                True,
                "ok",
                data=[VPNClient(name="laptop", active=True)],
            )
        return NetResult(action, False, "unexpected")

    bridge.call.side_effect = bridge_side_effect

    def run_async_inline(func, *args, callback=None):
        result = func(*args)
        if callback:
            callback(result)
        return result

    with patch.object(vpn, "run_async", side_effect=run_async_inline):
        vpn.refresh_state()

    actions = [c.args[0] for c in bridge.call.call_args_list]
    assert "vpn_status" in actions
    assert "vpn_list_clients" in actions
    assert vpn.client_list_store.iter_n_children(None) == 1
    assert vpn.clients_frame.get_sensitive() is True


def test_emit_clicked_on_basic_buttons_does_not_crash(main_window):
    win, _ = main_window
    with patch.object(win, "run_async_task") as run:
        for attr in ("repair_btn", "btn_diag", "btn_dns", "btn_ip", "btn_wifi"):
            getattr(win, attr).emit("clicked")
        assert run.call_count == 5


def test_emit_clicked_infrastructure_with_confirm(main_window):
    win, _ = main_window
    with patch.object(win, "ask_confirmation", return_value=True), patch.object(
        win, "run_async_task"
    ) as run:
        win.btn_stack.emit("clicked")
        win.btn_adapter.emit("clicked")
        win.btn_firewall.emit("clicked")
        assert run.call_count == 3


def test_log_view_readonly(main_window):
    win, _ = main_window
    assert win.log_view.get_editable() is False
    assert win.log_view.get_monospace() is True


def test_donate_and_about_handlers_exist(main_window):
    win, _ = main_window
    assert callable(win.on_donate)
    assert callable(win.on_about)
    with patch.object(win, "_spawn_browser") as browser:
        win.on_donate(None)
        browser.assert_called_once()
        assert "buymeacoffee" in browser.call_args[0][0]


def test_ai_disruptive_confirm_gate(main_window):
    win, _ = main_window
    ai = win.ai_console
    with patch.object(win, "ask_confirmation", return_value=False) as ask:
        with patch.object(ai.client, "ask") as ipc_ask:
            ai._confirm_and_execute("reset_tcp_ip_stack", {})
            ask.assert_called_once()
            ipc_ask.assert_not_called()
