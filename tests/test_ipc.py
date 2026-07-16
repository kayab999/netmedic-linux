import os
from unittest.mock import patch, MagicMock

from netmedic.ipc_actions import create_action_dispatcher
from netmedic.ipc_bridge import NetMedicIPCServer
from netmedic.ipc_security import IPCSession
from netmedic.lifecycle import LifecycleManager


@patch("netmedic.system.CommandRunner.run")
def test_ipc_dispatcher_network_status(mock_run):
    mock_run.side_effect = [
        MagicMock(success=True, stdout="default via 192.168.1.1 dev eth0", stderr=""),
        MagicMock(success=True, stdout="", stderr=""),
        MagicMock(success=True, stdout="", stderr=""),
        MagicMock(success=True, stdout="", stderr=""),
    ]

    from netmedic.network import NetworkMedic

    session = IPCSession()
    session.issue_token()
    medic = NetworkMedic()
    dispatch = create_action_dispatcher(medic, session)
    result = dispatch("network_status", {})

    assert result["status"] == "ok"
    assert result["success"] is True
    assert "Gateway" in result["message"]


def test_ipc_privileged_requires_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    session = IPCSession()
    session.issue_token()

    from netmedic.network import NetworkMedic

    dispatch = create_action_dispatcher(NetworkMedic(), session)
    result = dispatch("flush_dns", {})

    assert result["status"] == "error"
    assert result.get("requires_confirmation") is True


@patch("netmedic.system.CommandRunner.is_service_active", return_value=True)
@patch("netmedic.system.CommandRunner.run")
def test_ipc_privileged_with_token(mock_run, mock_active, tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    mock_run.return_value = MagicMock(success=True, stdout="", stderr="")

    from netmedic.network import NetworkMedic

    session = IPCSession()
    token = session.issue_token()
    dispatch = create_action_dispatcher(NetworkMedic(), session)

    result = dispatch(
        "flush_dns",
        {"confirmed": True, "session_token": token},
        peer_uid=os.getuid(),
        peer_pid=os.getpid(),
    )
    assert result["status"] == "ok"


def test_ipc_bridge_handles_invalid_json(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    lifecycle = LifecycleManager()

    def dispatch(action, params, **kwargs):
        return {"status": "ok", "action": action}

    server = NetMedicIPCServer(dispatch, lifecycle)
    payload = server._handle_payload(b"not-json", peer_pid=1, peer_uid=os.getuid())

    assert payload["status"] == "error"
    assert "JSON" in payload["message"]


def test_ipc_bridge_strips_trailing_newline(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    lifecycle = LifecycleManager()

    def dispatch(action, params, **kwargs):
        return {"status": "ok", "action": action, "params": params}

    server = NetMedicIPCServer(dispatch, lifecycle)
    payload = server._handle_payload(
        b'{"action": "network_status", "params": {}}\n',
        peer_pid=1,
        peer_uid=os.getuid(),
    )

    assert payload["status"] == "ok"
    assert payload["action"] == "network_status"