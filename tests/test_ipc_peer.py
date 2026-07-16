import os
from unittest.mock import MagicMock, patch

from netmedic.ipc_actions import create_action_dispatcher
from netmedic.ipc_peer import validate_peer_identity
from netmedic.ipc_security import IPCSession
from netmedic.models import NetResult


def test_validate_peer_identity_accepts_owner():
    assert validate_peer_identity(os.getuid(), 1234) is None


def test_validate_peer_identity_rejects_missing():
    result = validate_peer_identity(-1, -1)
    assert result is not None
    assert result.get("requires_peer_auth") is True


def test_validate_peer_identity_rejects_foreign_uid():
    foreign = os.getuid() + 1
    result = validate_peer_identity(foreign, 1234)
    assert result is not None
    assert "owner" in result["message"].lower()


def test_privileged_dispatch_rejects_foreign_peer(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    session = IPCSession()
    token = session.issue_token()
    dispatch = create_action_dispatcher(MagicMock(), session)
    foreign = os.getuid() + 1

    result = dispatch(
        "flush_dns",
        {"confirmed": True, "session_token": token},
        peer_uid=foreign,
        peer_pid=99,
    )

    assert result["status"] == "error"
    assert result.get("requires_peer_auth") is True


@patch("netmedic.ipc_actions.AngristanOperator")
def test_privileged_dispatch_accepts_owner_peer(mock_vpn_cls, tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    medic = MagicMock()
    medic.flush_dns.return_value = NetResult("DNS", True, "flushed")
    session = IPCSession()
    token = session.issue_token()
    dispatch = create_action_dispatcher(medic, session)

    result = dispatch(
        "flush_dns",
        {"confirmed": True, "session_token": token},
        peer_uid=os.getuid(),
        peer_pid=os.getpid(),
    )

    assert result["status"] == "ok"
    medic.flush_dns.assert_called_once()


def test_get_session_token_rejects_missing_peer(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    session = IPCSession()
    session.issue_token()
    dispatch = create_action_dispatcher(MagicMock(), session)

    result = dispatch("get_session_token", {}, peer_uid=-1, peer_pid=-1)

    assert result["status"] == "error"
    assert result.get("requires_peer_auth") is True