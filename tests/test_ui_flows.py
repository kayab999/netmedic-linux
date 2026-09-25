"""ui.py coverage (P1.2): busy, dialogs, task_done branches, settle, smart-repair.

Harness mirrors tests/test_ui_elements_wiring.py: real MainWindow with mocked
IPC bridge, immediate GLib.idle_add. Threading is avoided: task funcs are
captured from run_async_task and executed synchronously; on_task_done is
driven directly with mock futures.
"""
from __future__ import annotations

import concurrent.futures
import os
from unittest.mock import ANY, MagicMock, patch

import gi
import pytest

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # noqa: E402, F401

from netmedic.models import NetResult, ResultCode, TaskResult  # noqa: E402

os.environ.setdefault("NO_AT_BRIDGE", "1")


def _immediate_idle(cb, *args, **kwargs):
    try:
        cb(*args) if args else cb()
    except TypeError:
        return cb()
    return False


@pytest.fixture
def win():
    mock_bridge = MagicMock()
    mock_bridge.call.return_value = NetResult("Mock", True, "ok")
    mock_bridge.is_available.return_value = True
    with patch("netmedic.ui.NetworkMedic"), patch(
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
        "netmedic.ui.GLib.idle_add", side_effect=_immediate_idle
    ), patch(
        "netmedic.ui_vpn.GLib.idle_add", side_effect=_immediate_idle
    ):
        medic = MagicMock()
        medic.cleanup.return_value = NetResult("Cleanup", True, "ok")
        from netmedic.ui import MainWindow

        w = MainWindow()
        w.actions = mock_bridge
        w.vpn_panel.actions = mock_bridge
        yield w, mock_bridge
        w.is_destroyed = True


def _nr(op="Op", success=True, msg="ok", **kw):
    return NetResult(op, success, msg, **kw)


# --- install health / tab switch ---

def test_report_install_health_ok_and_incomplete(win, monkeypatch):
    w, _ = win
    monkeypatch.setattr(
        "netmedic.status.collect_status",
        lambda: {"production_ready": True, "helper_mode": True, "hints": []},
    )
    assert w._report_install_health() is False
    monkeypatch.setattr(
        "netmedic.status.collect_status",
        lambda: {"production_ready": False, "hints": ["install policy"]},
    )
    assert w._report_install_health() is False

    def boom():
        raise RuntimeError("no status")

    monkeypatch.setattr("netmedic.status.collect_status", boom)
    assert w._report_install_health() is False


def test_on_tab_switch(win, monkeypatch):
    w, _ = win
    monkeypatch.setattr(w.vpn_panel, "refresh_state", MagicMock())
    w.vpn_panel._state_loaded = False
    w.vpn_panel._needs_retry = False
    w._on_tab_switch(None, None, 1)
    w.vpn_panel.refresh_state.assert_called_once()
    w.vpn_panel._state_loaded = True
    w._on_tab_switch(None, None, 1)
    assert w.vpn_panel.refresh_state.call_count == 1
    w.vpn_panel._needs_retry = True
    w._on_tab_switch(None, None, 1)
    assert w.vpn_panel.refresh_state.call_count == 2
    w._on_tab_switch(None, None, 0)
    assert w.vpn_panel.refresh_state.call_count == 2


# --- busy ---

def test_set_busy_refcount(win):
    w, _ = win
    assert w._busy_count == 0
    w.set_busy(True, "a")
    w.set_busy(True, "b")
    assert w._busy_count == 2
    assert w.notebook.get_sensitive() is False
    w.set_busy(False)
    assert w._busy_count == 1
    w.set_busy(False)
    assert w._busy_count == 0
    assert w.notebook.get_sensitive() is True
    w.set_busy(False)
    assert w._busy_count == 0


def test_update_busy_destroyed(win):
    w, _ = win
    w.is_destroyed = True
    assert w._update_busy_ui(True, "x") is False
    w.is_destroyed = False


# --- dialogs / icon / shutdown ---

def test_ask_confirmation(win):
    w, _ = win
    with patch("netmedic.ui.Gtk.MessageDialog") as mock_dlg:
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.OK
        assert w.ask_confirmation("T", "M") is True
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.CANCEL
        assert w.ask_confirmation("T", "M") is False


def test_apply_window_icon_paths(win, tmp_path, monkeypatch):
    from netmedic import ui as uimod

    w, _ = win
    monkeypatch.setattr(uimod, "resolve_app_icon_path", lambda: None)
    monkeypatch.setattr(w, "set_icon_name", MagicMock())
    w._apply_window_icon()
    w.set_icon_name.assert_called_with("netmedic")

    # Missing file -> real GLib.Error -> fallback
    monkeypatch.setattr(uimod, "resolve_app_icon_path", lambda: "/nonexistent/icon.png")
    w._apply_window_icon()
    assert w.set_icon_name.called


def test_apply_window_icon_success(win, tmp_path, monkeypatch):
    from PIL import Image

    from netmedic import ui as uimod

    w, _ = win
    icon = tmp_path / "icon.png"
    Image.new("RGB", (8, 8)).save(icon)
    monkeypatch.setattr(uimod, "resolve_app_icon_path", lambda: icon)
    w._apply_window_icon()  # real set_icon_from_file, covers success return


def test_on_destroy_pilot_error(win, monkeypatch):
    w, _ = win
    w.is_destroyed = False
    w._emergency_done = False
    monkeypatch.setattr("netmedic.ui.Gtk.main_quit", lambda: None)
    mock_pilot = MagicMock()
    mock_pilot.shutdown.side_effect = RuntimeError("pilot gone")
    monkeypatch.setattr("netmedic.ipc_client.PilotClient", lambda: mock_pilot)
    w.on_destroy(None)  # logs, does not raise


def test_append_log_destroyed(win):
    w, _ = win
    w.is_destroyed = True
    w.append_log("dropped")
    w.is_destroyed = False


def test_emergency_shutdown_once(win, monkeypatch):
    w, _ = win
    mock_shutdown_ops = MagicMock()
    monkeypatch.setattr("netmedic.ui.shutdown_operators", mock_shutdown_ops)
    w.emergency_shutdown()
    assert w.is_destroyed is True
    assert mock_shutdown_ops.call_count == 1
    w.emergency_shutdown()
    assert mock_shutdown_ops.call_count == 1


def test_emergency_shutdown_executor_error(win, monkeypatch):
    w, _ = win
    w._emergency_done = False
    w.is_destroyed = False
    monkeypatch.setattr("netmedic.ui.shutdown_operators", MagicMock())

    def boom(**kwargs):
        raise RuntimeError("pool gone")

    monkeypatch.setattr(w.executor, "shutdown", boom)
    w.emergency_shutdown()  # logs, does not raise
    assert w.is_destroyed is True


def test_on_destroy_paths(win, monkeypatch):
    w, _ = win
    w.is_destroyed = False
    w._emergency_done = False
    monkeypatch.setattr("netmedic.ui.Gtk.main_quit", lambda: None)
    mock_pilot = MagicMock()
    monkeypatch.setattr("netmedic.ipc_client.PilotClient", lambda: mock_pilot)
    w.on_destroy(None)
    mock_pilot.shutdown.assert_called_once()

    # medic cleanup exception path
    w.is_destroyed = False
    w._emergency_done = False
    w.medic.cleanup.side_effect = RuntimeError("cleanup boom")
    w.on_destroy(None)  # logs, does not raise
    w.medic.cleanup.side_effect = None


def test_show_error_dialog(win):
    w, _ = win
    w.is_destroyed = True
    with patch("netmedic.ui.Gtk.MessageDialog") as mock_dlg:
        w._show_error_dialog("T", "M")
        mock_dlg.assert_not_called()
    w.is_destroyed = False
    with patch("netmedic.ui.Gtk.MessageDialog") as mock_dlg:
        mock_dlg.return_value.run.return_value = Gtk.ResponseType.OK
        w._show_error_dialog("Title", "Body")
        mock_dlg.return_value.run.assert_called_once()
        mock_dlg.return_value.destroy.assert_called_once()


def test_ipc_action_delegates(win):
    w, bridge = win
    w._ipc_action("flush_dns")
    bridge.call.assert_called_with("flush_dns", None, confirmed=None)


# --- run_async_task / on_task_done ---

def _done_future(task_result=None, exc=None):
    f = MagicMock()
    if exc is not None:
        f.result.side_effect = exc
    else:
        f.result.return_value = task_result
    return f


def test_run_async_task_success_and_error(win):
    from concurrent.futures import Future

    w, _ = win

    class InlineExecutor:
        def submit(self, fn):
            fut: Future = Future()
            try:
                fut.set_result(fn())
            except Exception as exc:  # noqa: BLE001 — mirrors task_wrapper
                fut.set_exception(exc)
            return fut

    # NOTE: the real ThreadPoolExecutor would run on_task_done (and its Gtk
    # dialogs, via immediate idle_add) on a worker thread -> segfault under
    # coverage. Inline keeps everything on the test thread.
    w.executor = InlineExecutor()
    w.run_async_task(lambda: _nr("T", True, "fine"))
    w.run_async_task(lambda: 1 / 0, msg="Boom")


def test_on_task_done_ok(win, monkeypatch):
    w, _ = win
    monkeypatch.setattr(w, "_show_error_dialog", MagicMock())
    w.on_task_done(_done_future(TaskResult(True, data=_nr("T", True, "all good"))))
    w._show_error_dialog.assert_not_called()


def test_on_task_done_cancelled(win, monkeypatch):
    w, _ = win
    mock_err = MagicMock()
    monkeypatch.setattr(w, "_show_error_dialog", mock_err)
    w.on_task_done(
        _done_future(TaskResult(True, data=_nr("T", False, "denied", code=ResultCode.CANCELLED)))
    )
    mock_err.assert_called_with("Authentication Required", ANY)


def test_on_task_done_helper_missing(win, monkeypatch):
    w, _ = win
    mock_err = MagicMock()
    monkeypatch.setattr(w, "_show_error_dialog", mock_err)
    w.on_task_done(
        _done_future(
            TaskResult(
                True,
                data=_nr("T", False, "fail", details="helper-missing policy", code=ResultCode.ERROR),
            )
        )
    )
    assert mock_err.call_args[0][0] == "Helper Not Installed"


def test_on_task_done_legacy_text_fallback(win, monkeypatch):
    w, _ = win
    mock_err = MagicMock()
    monkeypatch.setattr(w, "_show_error_dialog", mock_err)
    w.on_task_done(
        _done_future(
            TaskResult(True, data=_nr("T", False, "helper not installed", code=ResultCode.FAILED))
        )
    )
    assert mock_err.call_args[0][0] == "Helper Not Installed"
    w.on_task_done(
        _done_future(TaskResult(True, data=_nr("T", False, "dismissed", code=ResultCode.FAILED)))
    )
    assert mock_err.call_args[0][0] == "Authentication Required"


def test_on_task_done_string_codes(win, monkeypatch):
    w, _ = win
    mock_err = MagicMock()
    monkeypatch.setattr(w, "_show_error_dialog", mock_err)
    r = _nr("T", True, "ok")
    object.__setattr__(r, "code", "ok")
    w.on_task_done(_done_future(TaskResult(True, data=r)))
    mock_err.assert_not_called()
    r2 = _nr("T", False, "bad", details="x")
    object.__setattr__(r2, "code", "bogus")
    w.on_task_done(_done_future(TaskResult(True, data=r2)))
    # bogus code -> falls through legacy text path, no dialog for plain text
    mock_err.assert_not_called()


def test_on_task_done_system_error_and_cancelled_future(win, monkeypatch):
    w, _ = win
    mock_err = MagicMock()
    monkeypatch.setattr(w, "_show_error_dialog", mock_err)
    w.on_task_done(_done_future(TaskResult(False, error="worker blew up")))
    assert mock_err.call_args[0][0] == "Unexpected Error"
    w.on_task_done(_done_future(exc=concurrent.futures.CancelledError()))
    w.on_task_done(_done_future(exc=RuntimeError("fatal boom")))


def test_on_task_done_details_string(win, monkeypatch):
    w, _ = win
    monkeypatch.setattr(w, "_show_error_dialog", MagicMock())
    w.on_task_done(
        _done_future(TaskResult(True, data=_nr("T", True, "ok", details="plain string")))
    )


# --- settle ---

def test_wait_for_settle_no_iface(win, monkeypatch):
    w, _ = win
    monkeypatch.setattr("time.sleep", lambda s: None)
    w._wait_for_settle(None)


def test_wait_for_settle_ready_paths(win, monkeypatch):
    w, _ = win
    monkeypatch.setattr("time.sleep", lambda s: None)
    from netmedic.system import CommandRunner

    monkeypatch.setattr(
        CommandRunner,
        "run",
        staticmethod(
            lambda cmd, timeout=None, **k: MagicMock(
                success=True,
                stdout="    inet 192.168.1.10/24" if cmd[0] == "ip" else "GENERAL.STATE:100 (activated)",
            )
        ),
    )
    w._wait_for_settle("eth0", timeout=2)

    monkeypatch.setattr(
        CommandRunner,
        "run",
        staticmethod(
            lambda cmd, timeout=None, **k: MagicMock(
                success=(cmd[0] == "ip"), stdout="    inet 192.168.1.10/24"
            )
        ),
    )
    w._wait_for_settle("eth0", timeout=2)


def test_wait_for_settle_timeout(win, monkeypatch):
    w, _ = win
    monkeypatch.setattr("time.sleep", lambda s: None)
    from netmedic.system import CommandRunner

    monkeypatch.setattr(
        CommandRunner, "run", staticmethod(lambda cmd, timeout=None, **k: MagicMock(success=False, stdout=""))
    )
    w._wait_for_settle("eth0", timeout=2)  # proceeds, does not fail


# --- smart repair ---

def _diag(gw_ok=True, dns_ok=True, net_ok=True, code=None, legacy=False):
    if legacy:
        return NetResult("Diagnostics", False, "Gateway Not Found", details=None, data=None, code=ResultCode.FAILED)
    data = {"gateway_ok": gw_ok, "dns_ok": dns_ok, "internet_ok": net_ok, "gateway": "192.168.1.1" if gw_ok else None}
    details = {"gateway": "192.168.1.1" if gw_ok else "none", "gateway_ok": gw_ok}
    ok = gw_ok and dns_ok and net_ok
    return NetResult(
        "Diagnostics", ok, "diag", details=details, data=data,
        code=code or (ResultCode.OK if ok else ResultCode.FAILED),
    )


def _run_sequence(w, monkeypatch, calls, pre, post=None, flush=None, renew=None, verify=True):
    monkeypatch.setattr(w, "_wait_for_settle", lambda *a, **k: None)
    monkeypatch.setattr("netmedic.network.NetworkMedic.get_default_interface", lambda self: "eth0")
    if not verify:
        monkeypatch.setenv("NETMEDIC_POST_REPAIR_VERIFY", "0")
    else:
        monkeypatch.delenv("NETMEDIC_POST_REPAIR_VERIFY", raising=False)
    table = {
        "network_status": [pre] + ([post] if post is not None else []),
        "flush_dns": [flush or _nr("Flush DNS", True, "executed", code=ResultCode.EXECUTED)],
        "renew_ip": [renew or _nr("Renew IP", True, "executed", code=ResultCode.EXECUTED)],
    }

    def fake_call(action, params=None, confirmed=None):
        calls.append(action)
        items = table.get(action, [_nr(action)])
        return items.pop(0) if len(items) > 1 else items[0]

    w.actions.call.side_effect = fake_call
    captured = {}
    w.run_async_task = lambda fn, msg="": captured.setdefault("fn", fn)
    w.on_smart_repair(None)
    return captured["fn"]()


def test_smart_repair_healthy_skipped(win, monkeypatch):
    w, _ = win
    calls: list = []
    post = _diag()
    res = _run_sequence(w, monkeypatch, calls, _diag(), post=post)
    assert res.code == ResultCode.SKIPPED
    assert "flush_dns" not in calls and "renew_ip" not in calls
    assert calls.count("network_status") == 2


def test_smart_repair_healthy_no_verify(win, monkeypatch):
    w, _ = win
    calls = []
    res = _run_sequence(w, monkeypatch, calls, _diag(), verify=False)
    assert res.code == ResultCode.SKIPPED
    assert calls == ["network_status"]


def test_smart_repair_full_success(win, monkeypatch):
    w, _ = win
    calls = []
    pre = _diag(gw_ok=True, dns_ok=False, net_ok=False)
    post = _diag()
    flush = _nr("Flush DNS", True, "executed", details={"probe": "google.com"}, code=ResultCode.EXECUTED)
    renew = _nr("Renew IP", True, "executed", details={"iface": "eth0"}, code=ResultCode.EXECUTED)
    res = _run_sequence(w, monkeypatch, calls, pre, post=post, flush=flush, renew=renew)
    assert res.code == ResultCode.OK
    assert "SUCCESS" in res.message
    assert set(calls) == {"network_status", "flush_dns", "renew_ip"}


def test_smart_repair_no_gateway_skips_renew(win, monkeypatch):
    w, _ = win
    calls = []
    pre = _diag(gw_ok=False, dns_ok=False, net_ok=False)
    post = _diag(gw_ok=False, dns_ok=False, net_ok=False)
    res = _run_sequence(w, monkeypatch, calls, pre, post=post)
    assert "renew_ip" not in calls
    assert res.code == ResultCode.FAILED


def test_smart_repair_legacy_payload(win, monkeypatch):
    w, _ = win
    calls = []
    _run_sequence(w, monkeypatch, calls, _diag(legacy=True), post=_diag())
    assert "renew_ip" not in calls  # substring fallback path


def test_smart_repair_no_verify_executed(win, monkeypatch):
    w, _ = win
    calls = []
    pre = _diag(gw_ok=True, dns_ok=False, net_ok=False)
    res = _run_sequence(w, monkeypatch, calls, pre, verify=False)
    assert res.code == ResultCode.EXECUTED
    assert "DISABLED" in res.message


def test_smart_repair_repair_failed(win, monkeypatch):
    w, _ = win
    calls = []
    pre = _diag(gw_ok=True, dns_ok=False, net_ok=False)
    post = _diag(gw_ok=True, dns_ok=False, net_ok=False)
    flush = _nr("Flush DNS", False, "flush failed", code=ResultCode.FAILED)
    res = _run_sequence(w, monkeypatch, calls, pre, post=post, flush=flush)
    assert res.code == ResultCode.FAILED
    assert "review log" in res.message


def test_smart_repair_partial(win, monkeypatch):
    w, _ = win
    calls = []
    pre = _diag(gw_ok=True, dns_ok=False, net_ok=False)
    post = _diag(gw_ok=True, dns_ok=True, net_ok=False)
    res = _run_sequence(w, monkeypatch, calls, pre, post=post)
    assert res.code == ResultCode.PARTIAL
    assert "upstream" in res.message


def test_smart_repair_captive_hint(win, monkeypatch):
    w, _ = win
    calls = []
    pre = _diag(gw_ok=True, dns_ok=False, net_ok=False)
    post = _diag(gw_ok=True, dns_ok=True, net_ok=True)
    post.details["captive_portal_hint"] = "possible portal"
    res = _run_sequence(w, monkeypatch, calls, pre, post=post)
    assert res.code == ResultCode.OK


def test_smart_repair_medic_exception(win, monkeypatch):
    w, _ = win
    calls = []
    pre = _diag(gw_ok=True, dns_ok=False, net_ok=False)
    post = _diag()
    with patch("netmedic.network.NetworkMedic", side_effect=RuntimeError("no medic")):
        res = _run_sequence(w, monkeypatch, calls, pre, post=post)
    assert res.code == ResultCode.OK


def test_smart_repair_healthy_by_code(win, monkeypatch):
    w, _ = win
    calls = []
    diag = NetResult("Diagnostics", True, "ok")  # no data: code fallback path
    res = _run_sequence(w, monkeypatch, calls, diag, post=_diag())
    assert res.code == ResultCode.SKIPPED


def test_smart_repair_pre_ok_post_ok(win, monkeypatch):
    w, _ = win
    calls = []
    pre = NetResult(
        "Diagnostics", False, "flaky",
        details={"gateway": "192.168.1.1", "gateway_ok": True},
        data={"gateway_ok": True, "dns_ok": False, "internet_ok": False, "gateway": "192.168.1.1"},
        code=ResultCode.OK,
    )
    res = _run_sequence(w, monkeypatch, calls, pre, post=_diag())
    assert res.code == ResultCode.OK
    assert "pre=OK post=OK" in res.message


def test_smart_repair_upstream_outage(win, monkeypatch):
    w, _ = win
    calls = []
    pre = NetResult(
        "Diagnostics", False, "down",
        details={"gateway": "192.168.1.1", "gateway_ok": True},
        data={"gateway_ok": True, "dns_ok": True, "internet_ok": False, "gateway": "192.168.1.1"},
        code=ResultCode.FAILED,
    )
    post = NetResult(
        "Diagnostics", False, "down",
        details={"gateway": "192.168.1.1", "gateway_ok": True},
        data={"gateway_ok": True, "dns_ok": False, "internet_ok": False, "gateway": "192.168.1.1"},
        code=ResultCode.FAILED,
    )
    res = _run_sequence(w, monkeypatch, calls, pre, post=post)
    assert res.code == ResultCode.FAILED
    assert "upstream outage" in res.message


def test_smart_repair_new_fault(win, monkeypatch):
    w, _ = win
    calls = []
    pre = NetResult(
        "Diagnostics", False, "flaky",
        details={"gateway": "192.168.1.1", "gateway_ok": True},
        data={"gateway_ok": True, "dns_ok": False, "internet_ok": False, "gateway": "192.168.1.1"},
        code=ResultCode.OK,
    )
    post = NetResult(
        "Diagnostics", False, "down",
        details={"gateway": "192.168.1.1", "gateway_ok": True},
        data={"gateway_ok": True, "dns_ok": True, "internet_ok": True, "gateway": "192.168.1.1"},
        code=ResultCode.FAILED,
    )
    res = _run_sequence(w, monkeypatch, calls, pre, post=post)
    assert res.code == ResultCode.FAILED
    assert "new fault" in res.message


def test_smart_repair_string_codes(win, monkeypatch):
    w, _ = win
    calls = []
    pre = _diag(gw_ok=True, dns_ok=False, net_ok=False)
    post = _diag()
    flush = _nr("Flush DNS", True, "executed", code=ResultCode.EXECUTED)
    object.__setattr__(flush, "code", "executed")
    # NOTE: an invalid string code would already raise in to_log_entry()
    # (called before the _is_ok_or_executed check), so only valid strings
    # are exercisable here; the ValueError branch is defensive.
    ok_str = _nr("Renew IP", True, "executed", code=ResultCode.EXECUTED)
    object.__setattr__(ok_str, "code", "ok")
    res = _run_sequence(w, monkeypatch, calls, pre, post=post, flush=flush, renew=ok_str)
    assert res.code == ResultCode.OK


# --- simple + dangerous handlers ---

def _capture_task(w):
    captured = {}
    w.run_async_task = lambda fn, msg="": captured.setdefault("fn", fn)
    return captured


def test_simple_handlers_route(win):
    w, bridge = win
    for handler, action in [
        (w.on_diagnostics, "network_status"),
        (w.on_flush_dns, "flush_dns"),
        (w.on_renew_ip, "renew_ip"),
        (w.on_scan_wifi, "wifi_diagnostics"),
    ]:
        cap = _capture_task(w)
        handler(None)
        assert cap["fn"]() is not None
        bridge.call.assert_any_call(action, None, confirmed=None)


def test_dangerous_handlers_confirm(win, monkeypatch):
    w, bridge = win
    for handler, action in [
        (w.on_reset_tcp_ip, "reset_tcp_ip_stack"),
        (w.on_restart_adapter, "restart_adapter"),
        (w.on_toggle_firewall, "toggle_firewall"),
    ]:
        monkeypatch.setattr(w, "ask_confirmation", lambda t, m: True)
        cap = _capture_task(w)
        handler(None)
        cap["fn"]()
        bridge.call.assert_any_call(action, None, confirmed=None)
        monkeypatch.setattr(w, "ask_confirmation", lambda t, m: False)
        cap2 = _capture_task(w)
        handler(None)
        assert "fn" not in cap2


# --- browser / about ---

def test_spawn_browser_ok_and_fail(win, monkeypatch):
    w, _ = win
    proc = MagicMock()
    proc.pid = 1234
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: proc)
    monkeypatch.setattr("netmedic.ui.GLib.child_watch_add", lambda *a, **k: None)
    w._spawn_browser("https://example.com")

    def boom(*a, **k):
        raise OSError("no browser")

    monkeypatch.setattr("subprocess.Popen", boom)
    w._spawn_browser("https://example.com")  # logs, does not raise


def test_on_donate(win, monkeypatch):
    w, _ = win
    seen = []
    monkeypatch.setattr(w, "_spawn_browser", seen.append)
    w.on_donate(None)
    assert seen == ["https://buymeacoffee.com/kayabsoftware"]


def test_on_about(win, monkeypatch):
    from netmedic import ui as uimod

    w, _ = win
    monkeypatch.setattr(uimod, "resolve_manual_path", lambda: None)
    with patch("netmedic.ui.Gtk.AboutDialog") as mock_about:
        w.on_about(None)
        mock_about.return_value.run.assert_called_once()
        mock_about.return_value.destroy.assert_called_once()

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".md") as tmp:
        monkeypatch.setattr(uimod, "resolve_manual_path", lambda: tmp.name)
        with patch("netmedic.ui.Gtk.AboutDialog") as mock_about:
            w.on_about(None)
            mock_about.return_value.run.assert_called_once()


def test_append_log_cap(win):
    from netmedic.ui import MAX_LOG_LINES

    w, _ = win
    for i in range(MAX_LOG_LINES + 20):
        w.append_log(f"line {i}")
    buf = w.log_view.get_buffer()
    assert buf.get_line_count() <= MAX_LOG_LINES + 1
