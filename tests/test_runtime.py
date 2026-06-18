from unittest.mock import patch, MagicMock

from netmedic.runtime import bootstrap, shutdown, parse_args


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