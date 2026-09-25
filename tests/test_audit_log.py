import json
import os
from unittest.mock import MagicMock, patch

from netmedic.audit_log import get_audit_log_path, record
from netmedic.ipc_actions import create_action_dispatcher
from netmedic.ipc_security import IPCSession
from netmedic.models import NetResult


def test_audit_record_writes_json_line(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    record(
        action="flush_dns",
        peer_uid=os.getuid(),
        peer_pid=42,
        params={"confirmed": True, "session_token": "secret"},
        result={"status": "ok", "message": "done"},
        duration_ms=12.5,
        outcome="ok",
    )
    line = json.loads(get_audit_log_path().read_text().strip())
    assert line["action"] == "flush_dns"
    assert line["peer_uid"] == os.getuid()
    assert line["outcome"] == "ok"
    assert line["params"]["session_token"] == "<redacted>"
    assert get_audit_log_path().stat().st_mode & 0o777 == 0o600


@patch("netmedic.ipc_actions.AngristanOperator")
def test_privileged_dispatch_writes_audit_entry(mock_vpn_cls, tmp_path, monkeypatch):
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
        peer_pid=99,
    )

    assert result["status"] == "ok"
    # Two-phase audit: intent first, completion second (B-4/C-16)
    lines = [
        json.loads(line)
        for line in get_audit_log_path().read_text().strip().splitlines()
    ]
    assert [entry["event"] for entry in lines] == ["privileged_intent", "privileged_ipc"]
    intent, entry = lines
    assert intent["action"] == "flush_dns"
    assert intent["params"]["session_token"] == "<redacted>"
    assert entry["action"] == "flush_dns"
    assert entry["peer_uid"] == os.getuid()
    assert entry["peer_pid"] == 99
    assert entry["outcome"] == "ok"


def test_intent_record_fields(tmp_path, monkeypatch):
    from netmedic.audit_log import record_intent

    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    record_intent(action="renew_ip", peer_uid=1000, peer_pid=7, params={"a": 1})
    line = json.loads(get_audit_log_path().read_text().strip())
    # F-6 field contract for intent records
    assert line["event"] == "privileged_intent"
    assert line["action"] == "renew_ip"
    assert line["peer_uid"] == 1000
    assert line["peer_pid"] == 7
    assert line["params"] == {"a": 1}
    assert "ts" in line


def test_audit_unavailable_aborts_privileged(tmp_path, monkeypatch):
    """Fail-closed (B-4): unwritable audit log refuses the action pre-pkexec."""
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    get_audit_log_path().mkdir()  # open() for append now raises IsADirectoryError
    medic = MagicMock()
    session = IPCSession()
    token = session.issue_token()
    dispatch = create_action_dispatcher(medic, session)
    result = dispatch(
        "flush_dns",
        {"confirmed": True, "session_token": token},
        peer_uid=os.getuid(),
        peer_pid=99,
    )
    assert result["status"] == "error"
    assert "Audit unavailable" in result["message"]
    medic.flush_dns.assert_not_called()


def test_secret_file_atomic_replace(tmp_path, monkeypatch):
    """H-2: no torn reads (rename publish), 0600 from creation, stale tmp replaced."""
    import os as _os

    from netmedic.ipc_security import _write_secret_file

    target = tmp_path / "ipc.token"
    _write_secret_file(target, "a" * 64)
    assert target.read_text() == "a" * 64
    assert _os.stat(target).st_mode & 0o777 == 0o600
    assert list(tmp_path.glob("*.tmp")) == []

    # Stale tmp from a crashed run does not block re-issue.
    stale = tmp_path / f"ipc.token.{_os.getpid()}.tmp"
    stale.write_text("garbage")
    _write_secret_file(target, "b" * 64)
    assert target.read_text() == "b" * 64
    assert not stale.exists()


def test_privileged_denial_writes_audit_entry(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    monkeypatch.delenv("NETMEDIC_SKIP_POLKIT", raising=False)
    session = IPCSession()
    token = session.issue_token()
    dispatch = create_action_dispatcher(MagicMock(), session)

    with patch("netmedic.ipc_security.check_authorization", return_value=(False, "denied")):
        result = dispatch(
            "flush_dns",
            {"confirmed": True, "session_token": token},
            peer_uid=os.getuid(),
            peer_pid=55,
        )

    assert result["status"] == "error"
    entry = json.loads(get_audit_log_path().read_text().strip())
    assert entry["outcome"] == "denied"
    assert entry["requires_polkit"] is True


def test_safe_action_does_not_write_audit(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    medic = MagicMock()
    medic.get_firewall_status.return_value = "ON"
    dispatch = create_action_dispatcher(medic, IPCSession())
    dispatch("firewall_status", {}, peer_uid=os.getuid(), peer_pid=1)
    assert not get_audit_log_path().exists()


def test_audit_redacts_sensitive_keys(tmp_path, monkeypatch):
    from netmedic.audit_log import _sanitize_params

    safe = _sanitize_params(
        {
            "session_token": "abc",
            "password": "secret123",
            "api_key": "k",
            "user_request": "hi",
            "iface": "eth0",
        }
    )
    assert safe["session_token"] == "<redacted>"
    assert safe["password"] == "<redacted>"
    assert safe["api_key"] == "<redacted>"
    assert safe["iface"] == "eth0"


def test_audit_truncates_long_strings(tmp_path, monkeypatch):
    from netmedic.audit_log import _sanitize_params

    long_val = "a" * 600
    safe = _sanitize_params({"user_request": long_val})
    assert len(safe["user_request"]) <= 500 + len("...[truncated]")
    assert safe["user_request"].endswith("...[truncated]")