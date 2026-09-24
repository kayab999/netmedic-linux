"""runtime.py coverage (P1.3): signals, logging, bootstrap, shutdown, run.

Module globals are saved/restored around each test; collaborators
(teardown, IPC server/session, lifecycle, medic, gui) are mocked.
"""
import logging
import signal
from unittest.mock import MagicMock

import pytest

from netmedic import runtime as rt


@pytest.fixture
def globals_saved(monkeypatch):
    saved = {
        "medic": rt._medic_instance,
        "server": rt._ipc_server,
        "session": rt._ipc_session,
        "shutting": rt._shutting_down,
    }
    rt._medic_instance = None
    rt._ipc_server = None
    rt._ipc_session = None
    rt._shutting_down = False
    yield
    rt._medic_instance = saved["medic"]
    rt._ipc_server = saved["server"]
    rt._ipc_session = saved["session"]
    rt._shutting_down = saved["shutting"]


def test_getters_lazy_session(globals_saved):
    assert rt.get_medic_instance() is None
    first = rt.get_ipc_session()
    assert rt.get_ipc_session() is first


def test_handle_signals_reentrant(globals_saved):
    rt._shutting_down = True
    rt.handle_signals(signal.SIGTERM, None)  # returns immediately
    assert rt._shutting_down is True


def test_handle_signals_full(globals_saved, monkeypatch):
    teardown = []
    monkeypatch.setattr(rt, "run_teardown_callbacks", lambda: teardown.append(1))
    server = rt._ipc_server = MagicMock()
    session = rt._ipc_session = MagicMock()
    lifecycle_calls = []
    monkeypatch.setattr(rt._lifecycle_manager, "cleanup", lambda: lifecycle_calls.append(1))
    medic = rt._medic_instance = MagicMock()
    quit_calls = []
    monkeypatch.setattr("netmedic.gui.quit_gui_if_running", lambda: quit_calls.append(1))
    with pytest.raises(SystemExit) as exc:
        rt.handle_signals(signal.SIGTERM, None)
    assert exc.value.code == 0
    assert teardown and lifecycle_calls and quit_calls
    server.stop.assert_called_once()
    session.cleanup.assert_called_once()
    medic.cleanup.assert_called_once()


def test_handle_signals_cleanup_errors(globals_saved, monkeypatch):
    monkeypatch.setattr(rt, "run_teardown_callbacks", lambda: None)
    rt._ipc_server = None
    rt._ipc_session = None
    monkeypatch.setattr(rt._lifecycle_manager, "cleanup", lambda: None)
    medic = rt._medic_instance = MagicMock()
    medic.cleanup.side_effect = RuntimeError("cleanup boom")

    def no_gui():
        raise RuntimeError("no display")

    monkeypatch.setattr("netmedic.gui.quit_gui_if_running", no_gui)
    with pytest.raises(SystemExit) as exc:
        rt.handle_signals(signal.SIGTERM, None)
    assert exc.value.code == 0


def test_setup_logging_new_and_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        rt.setup_logging(headless=True)
        log_file = rt.Config.get_log_file()
        assert log_file.exists()
        assert log_file.stat().st_mode & 0o777 == 0o600
        assert len(root.handlers) >= 2  # file + console handlers attached
        # second run hits the exists/chmod branch
        rt.setup_logging(headless=False)
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
        for h in saved_handlers:
            root.addHandler(h)
        root.setLevel(saved_level)


def test_bootstrap_lock_fail_headless_and_gui(globals_saved, monkeypatch, capsys):
    monkeypatch.setattr(rt, "setup_logging", lambda headless=False: None)
    monkeypatch.setattr(rt._lifecycle_manager, "acquire_lock", lambda: False)
    assert rt.bootstrap(headless=True) is False
    assert "already running" in capsys.readouterr().err

    monkeypatch.setattr("netmedic.gui.show_error_dialog", lambda msg: None)
    assert rt.bootstrap(headless=False) is False

    def no_dialog(msg):
        raise RuntimeError("no display")

    monkeypatch.setattr("netmedic.gui.show_error_dialog", no_dialog)
    assert rt.bootstrap(headless=False) is False
    assert "already running" in capsys.readouterr().err


def test_bootstrap_logging_failure(globals_saved, monkeypatch):
    def boom(headless=False):
        raise RuntimeError("log boom")

    monkeypatch.setattr(rt, "setup_logging", boom)
    monkeypatch.setattr(rt._lifecycle_manager, "acquire_lock", lambda: False)
    assert rt.bootstrap(headless=True) is False


def test_bootstrap_success_and_rollback(globals_saved, monkeypatch):
    monkeypatch.setattr(rt, "setup_logging", lambda headless=False: None)
    monkeypatch.setattr(rt._lifecycle_manager, "acquire_lock", lambda: True)
    written = []
    monkeypatch.setattr(rt._lifecycle_manager, "write_pid", lambda: written.append(1))
    monkeypatch.setattr("netmedic.runtime.NetworkMedic", lambda: MagicMock())
    monkeypatch.setattr("netmedic.runtime.IPCSession", lambda: MagicMock())
    monkeypatch.setattr("netmedic.runtime.create_action_dispatcher", lambda m, s: MagicMock())
    server = MagicMock()
    monkeypatch.setattr("netmedic.runtime.NetMedicIPCServer", lambda disp, life: server)
    assert rt.bootstrap(headless=True) is True
    assert written
    server.start.assert_called_once()

    cleaned = []
    monkeypatch.setattr(rt._lifecycle_manager, "cleanup", lambda: cleaned.append(1))

    def fail_medic():
        raise RuntimeError("medic boom")

    monkeypatch.setattr("netmedic.runtime.NetworkMedic", fail_medic)
    with pytest.raises(RuntimeError):
        rt.bootstrap(headless=True)
    assert cleaned


def test_shutdown_paths(globals_saved, monkeypatch):
    rt._shutting_down = True
    rt.shutdown()  # early return
    rt._shutting_down = False

    monkeypatch.setattr(rt, "run_teardown_callbacks", lambda: None)
    server = rt._ipc_server = MagicMock()
    session = rt._ipc_session = MagicMock()
    monkeypatch.setattr(rt._lifecycle_manager, "cleanup", lambda: None)
    medic = rt._medic_instance = MagicMock()
    rt.shutdown()
    assert rt._shutting_down is True
    server.stop.assert_called_once()
    session.cleanup.assert_called_once()
    medic.cleanup.assert_called_once()

    rt._shutting_down = False
    medic.cleanup.side_effect = RuntimeError("bye boom")
    rt.shutdown()  # logs, does not raise


def test_parse_args():
    assert rt.parse_args([]).headless is False
    assert rt.parse_args(["--headless"]).headless is True
    assert rt.parse_args(["--status"]).status is True
    assert rt.parse_args(["--status-json"]).status_json is True


def test_run_status_paths(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        "netmedic.status.print_status", lambda as_json=False: seen.update(json=as_json) or 0
    )
    with pytest.raises(SystemExit) as exc:
        rt.run(status=True)
    assert exc.value.code == 0
    assert seen["json"] is False
    with pytest.raises(SystemExit):
        rt.run(status_json=True)
    assert seen["json"] is True


def test_run_bootstrap_fail(monkeypatch):
    monkeypatch.setattr("signal.signal", lambda *a, **k: None)
    monkeypatch.setattr(rt, "bootstrap", lambda headless=False: False)
    with pytest.raises(SystemExit) as exc:
        rt.run(headless=True)
    assert exc.value.code == 1


def test_run_headless_keyboard_interrupt(monkeypatch):
    monkeypatch.setattr("signal.signal", lambda *a, **k: None)
    monkeypatch.setattr(rt, "bootstrap", lambda headless=False: True)

    def sleep_forever(s):
        raise KeyboardInterrupt()

    monkeypatch.setattr("time.sleep", sleep_forever)
    shutdown_calls = []
    monkeypatch.setattr(rt, "shutdown", lambda: shutdown_calls.append(1))
    with pytest.raises(KeyboardInterrupt):
        rt.run(headless=True)
    assert shutdown_calls  # finally ran


def test_run_gui_and_error(monkeypatch, capsys):
    monkeypatch.setattr("signal.signal", lambda *a, **k: None)
    monkeypatch.setattr(rt, "bootstrap", lambda headless=False: True)
    ran = []
    monkeypatch.setattr("netmedic.gui.run_gui", lambda: ran.append(1))
    monkeypatch.setattr(rt, "shutdown", lambda: None)
    rt.run(headless=False)
    assert ran

    def fail_gui():
        raise RuntimeError("gui boom")

    monkeypatch.setattr("netmedic.gui.run_gui", fail_gui)
    shown = []
    monkeypatch.setattr("netmedic.gui.show_error_dialog", lambda *a, **k: shown.append(1))
    with pytest.raises(SystemExit) as exc:
        rt.run(headless=False)
    assert exc.value.code == 1
    assert shown

    def no_dialog(*a, **k):
        raise RuntimeError("no display")

    monkeypatch.setattr("netmedic.gui.show_error_dialog", no_dialog)
    with pytest.raises(SystemExit):
        rt.run(headless=False)
    assert "gui boom" in capsys.readouterr().err
