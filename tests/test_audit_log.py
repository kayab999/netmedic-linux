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
    entry = json.loads(get_audit_log_path().read_text().strip())
    assert entry["action"] == "flush_dns"
    assert entry["peer_uid"] == os.getuid()
    assert entry["peer_pid"] == 99
    assert entry["outcome"] == "ok"


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