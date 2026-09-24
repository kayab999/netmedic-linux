"""ui_vpn.py coverage (P1.2): panel state machine, client list, dialogs, run_async.

Harness follows tests/test_ui_elements_wiring.py: real Gtk widgets (never
shown), GuiActionBridge + AngristanOperator mocked, GLib.idle_add executed
inline via an InlineExecutor so all async paths run synchronously.
"""
from __future__ import annotations

import os
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import gi
import pytest

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # noqa: E402, F401

from netmedic.models import NetResult, ResultCode  # noqa: E402
from netmedic.operators.base import OperatorStatus  # noqa: E402
from netmedic.operators.vpn.base import VPNClient  # noqa: E402

os.environ.setdefault("NO_AT_BRIDGE", "1")


def _immediate_idle(cb, *args, **kwargs):
    try:
        cb(*args) if args else cb()
    except TypeError:
        return cb()
    return False


class InlineExecutor:
    """Synchronous executor: submit runs inline, callbacks fire immediately."""

    def submit(self, fn):
        fut: Future = Future()
        try:
            fut.set_result(fn())
        except Exception as exc:  # noqa: BLE001 — mirrors task_wrapper
            fut.set_exception(exc)
        return fut


def _ok(msg="ok", **kw):
    return NetResult("VPN", True, msg, code=ResultCode.OK, **kw)


def _err(msg="fail", code=ResultCode.FAILED, **kw):
    return NetResult("VPN", False, msg, code=code, **kw)


@pytest.fixture
def panel():
    mock_actions = MagicMock()
    mock_actions.call.return_value = _ok()
    with patch("netmedic.ui_vpn.GuiActionBridge", return_value=mock_actions), patch(
        "netmedic.ui_vpn.AngristanOperator"
    ), patch("netmedic.ui_vpn.GLib.idle_add", side_effect=_immediate_idle):
        from netmedic.ui_vpn import VPNPanel

        log_calls: list = []
        busy_calls: list = []
        p = VPNPanel(
            InlineExecutor(),
            log_callback=log_calls.append,
            set_busy_callback=lambda b, m="": busy_calls.append((b, m)),
            main_window=None,
        )
        p.actions = mock_actions
        yield p, mock_actions, log_calls, busy_calls


# --- log / busy helpers ---

def test_log_with_and_without_callback(panel):
    p, _, log_calls, _ = panel
    p.log("hello")
    assert log_calls == ["hello"]
    p.log_cb = None
    p.log("to-logger")  # falls back to logging, must not raise


def test_set_busy_with_and_without_callback(panel):
    p, _, _, busy_calls = panel
    p.set_busy(True, "Working")
    assert busy_calls == [(True, "Working")]
    p.set_busy_cb = None
    p.set_busy(False)  # no-op, must not raise


# --- run_async ---

def test_run_async_ok_logs_and_callback(panel):
    p, _, log_calls, busy_calls = panel
    seen = []
    p.run_async(lambda: _ok("done"), callback=seen.append)
    assert seen and seen[0].message == "done"
    assert any("done" in entry for entry in log_calls)
    assert busy_calls[0][0] is True
    assert busy_calls[-1][0] is False


def test_run_async_task_error_logged(panel):
    p, _, log_calls, _ = panel

    def boom():
        raise RuntimeError("task boom")

    p.run_async(boom)
    assert any("task boom" in entry for entry in log_calls)


def test_run_async_future_exception_logs_critical(panel):
    p, _, log_calls, _ = panel

    class ExplodingExecutor:
        def submit(self, fn):
            fut: Future = Future()
            fut.set_exception(RuntimeError("future boom"))
            return fut

    p.executor = ExplodingExecutor()
    p.run_async(lambda: _ok())
    assert any("Critical" in entry and "future boom" in entry for entry in log_calls)


def test_run_async_helper_missing_shows_error(panel, monkeypatch):
    p, _, _, _ = panel
    shown = []
    monkeypatch.setattr(p, "_show_error", lambda t, m: shown.append((t, m)))
    p.run_async(lambda: _err("helper-missing policy", code=ResultCode.ERROR))
    assert shown and shown[0][0] == "Helper Not Installed"


def test_run_async_cancelled_shows_auth(panel, monkeypatch):
    p, _, _, _ = panel
    shown = []
    monkeypatch.setattr(p, "_show_error", lambda t, m: shown.append((t, m)))
    p.run_async(lambda: _err("Authentication cancelled", code=ResultCode.CANCELLED))
    assert shown and shown[0][0] == "Authentication Required"


def test_run_async_dismissed_text_shows_auth(panel, monkeypatch):
    p, _, _, _ = panel
    shown = []
    monkeypatch.setattr(p, "_show_error", lambda t, m: shown.append((t, m)))
    p.run_async(lambda: _err("dismissed by user", code=ResultCode.FAILED))
    assert shown and shown[0][0] == "Authentication Required"


def test_run_async_failed_no_dialog(panel, monkeypatch):
    p, _, log_calls, _ = panel
    shown = []
    monkeypatch.setattr(p, "_show_error", lambda t, m: shown.append((t, m)))
    p.run_async(lambda: _err("plain failure", code=ResultCode.FAILED))
    assert shown == []
    assert any("plain failure" in entry for entry in log_calls)


# --- _show_error ---

def test_show_error_no_parent_returns(panel):
    p, _, _, _ = panel
    with patch("netmedic.ui_vpn.Gtk.MessageDialog") as mock_dlg:
        p._show_error("T", "M")
        mock_dlg.assert_not_called()


def test_show_error_destroyed_parent_returns(panel):
    p, _, _, _ = panel
    p.main_window = MagicMock()
    p.main_window.is_destroyed = True
    with patch("netmedic.ui_vpn.Gtk.MessageDialog") as mock_dlg:
        p._show_error("T", "M")
        mock_dlg.assert_not_called()


def test_show_error_with_parent(panel):
    p, _, _, _ = panel
    parent = MagicMock(spec=Gtk.Window)
    p.main_window = parent
    with patch("netmedic.ui_vpn.Gtk.MessageDialog") as mock_dlg:
        instance = mock_dlg.return_value
        instance.run.return_value = Gtk.ResponseType.OK
        p._show_error("Title", "Body")
        mock_dlg.assert_called_once()
        instance.run.assert_called_once()
        instance.destroy.assert_called_once()


# --- refresh_state state machine ---

def _status_side_effect(status_res, list_res):
    def fake(action, params=None, **kwargs):
        if action == "vpn_status":
            return status_res
        return list_res

    return fake


def test_refresh_error_state(panel):
    p, actions, _, _ = panel
    actions.call.side_effect = _status_side_effect(
        _err("backend down", code=ResultCode.ERROR), _ok()
    )
    p.refresh_state()
    assert p._needs_retry is True
    assert p._state_loaded is False
    assert "backend down" in p.status_label.get_text()


def test_refresh_not_installed(panel):
    p, actions, _, _ = panel
    actions.call.side_effect = _status_side_effect(
        _ok(OperatorStatus.NOT_INSTALLED.value), _ok()
    )
    p.refresh_state()
    assert p._state_loaded is True
    assert p.status_label.get_text() == "VPN Not Installed"
    assert p.action_btn.get_label() == "Install OpenVPN"
    assert p.action_btn.get_sensitive() is True
    assert p.clients_frame.get_sensitive() is False


def test_refresh_running_loads_clients(panel):
    p, actions, _, _ = panel
    clients = [VPNClient(name="laptop", active=True), VPNClient(name="old", active=False)]
    actions.call.side_effect = _status_side_effect(
        _ok(OperatorStatus.RUNNING.value), _ok("list", data=clients)
    )
    p.refresh_state()
    assert p.status_label.get_text() == "VPN Running"
    assert p.action_btn.get_label() == "Re-Check Status"
    rows = list(p.client_list_store)
    assert [r[0] for r in rows] == ["laptop", "old"]
    assert [r[1] for r in rows] == ["Active", "Revoked"]
    assert [r[2] for r in rows] == ["#4CAF50", "#9E9E9E"]


def test_refresh_stopped(panel):
    p, actions, _, _ = panel
    actions.call.side_effect = _status_side_effect(
        _ok(OperatorStatus.STOPPED.value), _ok("empty")
    )
    p.refresh_state()
    assert p.status_label.get_text() == "VPN Service Stopped"
    assert p.action_btn.get_label() == "Start VPN Service"
    # NOTE: client_stack.get_visible_child_name() needs widget realization;
    # assert store state instead (update_client_list cleared it).
    assert len(p.client_list_store) == 0


def test_refresh_unknown_status(panel):
    p, actions, _, _ = panel
    actions.call.side_effect = _status_side_effect(_ok("weird-state"), _ok())
    p.refresh_state()
    assert p.status_label.get_text() == "Status: weird-state"
    assert p.clients_frame.get_sensitive() is False


# --- update_client_list ---

def test_update_client_list_branches(panel):
    p, _, _, _ = panel
    # NOTE: visible-child-name needs realization; store length is the contract.
    p.update_client_list(_err("denied"))
    assert len(p.client_list_store) == 0
    p.update_client_list(_ok("empty", data=[]))
    assert len(p.client_list_store) == 0
    p.update_client_list(_ok("empty", data=None))
    assert len(p.client_list_store) == 0


# --- on_main_action ---

def test_main_action_install_ok(panel, monkeypatch):
    p, actions, _, _ = panel
    p.action_btn.set_label("Install OpenVPN")
    monkeypatch.setattr(p, "refresh_state", MagicMock())
    with patch("netmedic.ui_vpn.Gtk.MessageDialog") as mock_dlg:
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.OK
        p.on_main_action(p.action_btn)
    actions.call.assert_any_call("vpn_install")
    p.refresh_state.assert_called()


def test_main_action_install_cancel(panel):
    p, actions, _, _ = panel
    p.action_btn.set_label("Install OpenVPN")
    actions.reset_mock()
    with patch("netmedic.ui_vpn.Gtk.MessageDialog") as mock_dlg:
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.CANCEL
        p.on_main_action(p.action_btn)
    actions.call.assert_not_called()


def test_main_action_start_ok(panel, monkeypatch):
    p, actions, _, _ = panel
    btn = MagicMock()
    btn.get_label.return_value = "Start VPN Service"
    monkeypatch.setattr(p, "refresh_state", MagicMock())
    with patch("netmedic.ui_vpn.Gtk.MessageDialog") as mock_dlg:
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.OK
        p.on_main_action(btn)
    actions.call.assert_any_call("vpn_start_service")
    p.refresh_state.assert_called()


def test_main_action_start_cancel(panel):
    p, actions, _, _ = panel
    btn = MagicMock()
    btn.get_label.return_value = "Start VPN Service"
    actions.reset_mock()
    with patch("netmedic.ui_vpn.Gtk.MessageDialog") as mock_dlg:
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.CANCEL
        p.on_main_action(btn)
    actions.call.assert_not_called()


def test_main_action_other_refreshes(panel, monkeypatch):
    p, actions, _, _ = panel
    btn = MagicMock()
    btn.get_label.return_value = "Re-Check Status"
    monkeypatch.setattr(p, "refresh_state", MagicMock())
    p.on_main_action(btn)
    p.refresh_state.assert_called_once()
    actions.call.assert_not_called()


# --- on_add_client_dialog ---

def test_add_client_ok(panel, monkeypatch):
    p, actions, _, _ = panel
    actions.reset_mock()
    actions.call.return_value = _ok("created")
    with patch("netmedic.ui_vpn.Gtk.Dialog") as mock_dlg, patch(
        "netmedic.ui_vpn.Gtk.Entry"
    ) as mock_entry:
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.OK
        mock_entry.return_value.get_text.return_value = "  laptop  "
        p.on_add_client_dialog(MagicMock())
    called = [c.args[0] for c in actions.call.call_args_list]
    assert "vpn_create_client" in called
    assert "vpn_list_clients" in called
    create_kwargs = [
        c for c in actions.call.call_args_list if c.args[0] == "vpn_create_client"
    ][0]
    assert create_kwargs.args[1] == {"name": "laptop"}


def test_add_client_empty_name(panel, monkeypatch):
    p, actions, _, _ = panel
    shown = []
    monkeypatch.setattr(p, "_show_error", lambda t, m: shown.append((t, m)))
    actions.reset_mock()
    with patch("netmedic.ui_vpn.Gtk.Dialog") as mock_dlg, patch(
        "netmedic.ui_vpn.Gtk.Entry"
    ) as mock_entry:
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.OK
        mock_entry.return_value.get_text.return_value = "   "
        p.on_add_client_dialog(MagicMock())
    assert shown and shown[0][0] == "Invalid Name"
    actions.call.assert_not_called()


def test_add_client_cancel(panel):
    p, actions, _, _ = panel
    actions.reset_mock()
    with patch("netmedic.ui_vpn.Gtk.Dialog") as mock_dlg:
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.CANCEL
        p.on_add_client_dialog(MagicMock())
    actions.call.assert_not_called()


# --- on_revoke_client ---

def test_revoke_no_selection(panel, monkeypatch):
    p, actions, _, _ = panel
    shown = []
    monkeypatch.setattr(p, "_show_error", lambda t, m: shown.append((t, m)))
    actions.reset_mock()
    p.on_revoke_client(MagicMock())
    assert shown and shown[0][0] == "No Selection"
    actions.call.assert_not_called()


def test_revoke_ok(panel):
    p, actions, _, _ = panel
    p.client_list_store.append(["laptop", "Active", "#4CAF50"])
    sel = p.tree_view.get_selection()
    sel.select_iter(p.client_list_store.get_iter_first())
    actions.reset_mock()
    actions.call.return_value = _ok("revoked")
    with patch("netmedic.ui_vpn.Gtk.MessageDialog") as mock_dlg:
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.OK
        p.on_revoke_client(MagicMock())
    called = [c.args[0] for c in actions.call.call_args_list]
    assert "vpn_revoke_client" in called
    assert "vpn_list_clients" in called
    revoke_kwargs = [
        c for c in actions.call.call_args_list if c.args[0] == "vpn_revoke_client"
    ][0]
    assert revoke_kwargs.args[1] == {"name": "laptop"}


def test_revoke_cancel(panel):
    p, actions, _, _ = panel
    p.client_list_store.append(["laptop", "Active", "#4CAF50"])
    sel = p.tree_view.get_selection()
    sel.select_iter(p.client_list_store.get_iter_first())
    actions.reset_mock()
    with patch("netmedic.ui_vpn.Gtk.MessageDialog") as mock_dlg:
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.CANCEL
        p.on_revoke_client(MagicMock())
    actions.call.assert_not_called()


def test_run_async_without_callback(panel):
    p, _, log_calls, _ = panel
    p.run_async(lambda: _ok("nocb"))
    assert any("nocb" in entry for entry in log_calls)
