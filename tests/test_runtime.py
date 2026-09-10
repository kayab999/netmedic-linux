import sys
import types
from unittest.mock import patch, MagicMock

import pytest

from netmedic.runtime import bootstrap, shutdown, parse_args, run


def test_parse_args_headless():
    args = parse_args(["--headless"])
    assert args.headless is True


def test_parse_args_gui_default():
    args = parse_args([])
    assert args.headless is False


@patch("netmedic.runtime.NetMedicIPCServer")
@patch("netmedic.runtime.NetworkMedic")
@patch("netmedic.runtime._lifecycle_manager.acquire_lock", return_value=True)
def test_bootstrap_starts_ipc(mock_lock, mock_medic, mock_ipc, tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    monkeypatch.setattr("netmedic.runtime.setup_logging", lambda: None)

    mock_server = MagicMock()
    mock_ipc.return_value = mock_server

    assert bootstrap(headless=True) is True
    mock_server.start.assert_called_once()


@patch("netmedic.runtime._ipc_server")
def test_shutdown_stops_ipc(mock_ipc):
    mock_ipc.stop = MagicMock()
    shutdown()


def test_run_gui_start_failure_shows_dialog(monkeypatch):
    shown = []
    fake_gui = types.ModuleType("netmedic.gui")
    fake_gui.run_gui = lambda: (_ for _ in ()).throw(
        ImportError("No module named 'netmedic.constants'")
    )
    fake_gui.show_error_dialog = lambda message, title="Instance Error": shown.append(
        (title, message)
    )
    monkeypatch.setitem(sys.modules, "netmedic.gui", fake_gui)
    monkeypatch.setattr("netmedic.runtime.bootstrap", lambda headless=False: True)
    monkeypatch.setattr("netmedic.runtime.shutdown", lambda: None)
    monkeypatch.setattr("netmedic.runtime._shutting_down", False)

    with pytest.raises(SystemExit) as exc_info:
        run(headless=False)
    assert exc_info.value.code == 1
    assert shown == [
        ("NetMedic failed to start", "ImportError: No module named 'netmedic.constants'")
    ]