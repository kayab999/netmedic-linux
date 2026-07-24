import os
from unittest.mock import MagicMock, patch

from netmedic.ipc_actions import create_action_dispatcher
from netmedic.ipc_security import IPCSession
from netmedic.models import NetResult

_PEER = {"peer_uid": os.getuid(), "peer_pid": os.getpid()}


@patch("netmedic.ipc_actions.AngristanOperator")
def test_vpn_reconnect_restarts_vpn_not_network_stack(mock_vpn_cls):
    mock_vpn = MagicMock()
    mock_vpn.restart_service.return_value = NetResult("VPN", True, "VPN tunnel restarted")
    mock_vpn_cls.return_value = mock_vpn

    medic = MagicMock()
    session = IPCSession()
    token = session.issue_token()
    dispatch = create_action_dispatcher(medic, session)

    result = dispatch(
        "vpn_reconnect",
        {"confirmed": True, "session_token": token},
        **_PEER,
    )

    mock_vpn.restart_service.assert_called_once()
    medic.reset_tcp_ip_stack.assert_not_called()
    assert result["status"] == "ok"
    assert "VPN" in result["message"]


def test_donate_action_returns_url():
    session = IPCSession()
    dispatch = create_action_dispatcher(MagicMock(), session)
    result = dispatch("donate", {}, **_PEER)

    assert result["status"] == "ok"
    assert "buymeacoffee.com" in result["url"]


def test_safe_action_rejects_missing_peer():
    dispatch = create_action_dispatcher(MagicMock(), IPCSession())
    result = dispatch("donate", {}, peer_uid=-1, peer_pid=-1)
    assert result["status"] == "error"
    assert result.get("requires_peer_auth") is True


@patch("netmedic.ipc_actions.AngristanOperator")
def test_vpn_status_ipc(mock_vpn_cls):
    mock_vpn = MagicMock()
    mock_vpn.check_status.return_value = NetResult("VPN status", True, "RUNNING")
    mock_vpn_cls.return_value = mock_vpn

    dispatch = create_action_dispatcher(MagicMock(), IPCSession())
    result = dispatch("vpn_status", {}, **_PEER)

    mock_vpn.check_status.assert_called_once()
    assert result["status"] == "ok"
    assert result["message"] == "RUNNING"


@patch("netmedic.ipc_actions.AngristanOperator")
def test_vpn_list_clients_ipc(mock_vpn_cls):
    from netmedic.operators.vpn.base import VPNClient

    mock_vpn = MagicMock()
    mock_vpn.list_clients.return_value = NetResult(
        "VPN clients",
        True,
        "clients retrieved",
        data=[
            VPNClient(name="carlos-laptop", active=True),
            VPNClient(name="old-phone", active=False),
        ],
    )
    mock_vpn_cls.return_value = mock_vpn

    session = IPCSession()
    token = session.issue_token()
    dispatch = create_action_dispatcher(MagicMock(), session)
    result = dispatch(
        "vpn_list_clients",
        {"confirmed": True, "session_token": token},
        **_PEER,
    )

    mock_vpn.list_clients.assert_called_once()
    assert result["status"] == "ok"
    assert result["data"] == [
        {"name": "carlos-laptop", "active": True},
        {"name": "old-phone", "active": False},
    ]


@patch("netmedic.ipc_actions.AngristanOperator")
def test_vpn_list_clients_requires_privileged_auth(mock_vpn_cls):
    mock_vpn_cls.return_value = MagicMock()
    dispatch = create_action_dispatcher(MagicMock(), IPCSession())
    result = dispatch("vpn_list_clients", {}, **_PEER)
    assert result["status"] == "error"
    assert result.get("requires_confirmation") is True


@patch("netmedic.ipc_actions.AngristanOperator")
def test_vpn_create_and_revoke_client_security(mock_vpn_cls):
    mock_vpn = MagicMock()
    mock_vpn.add_client.return_value = NetResult("VPN", True, "Client created")
    mock_vpn.revoke_client.return_value = NetResult("VPN", True, "Client revoked")
    mock_vpn_cls.return_value = mock_vpn

    session = IPCSession()
    dispatch = create_action_dispatcher(MagicMock(), session)

    # 1. Unconfirmed create should fail
    res_fail = dispatch("vpn_create_client", {"name": "test-client"}, **_PEER)
    assert res_fail["status"] == "error"
    assert res_fail.get("requires_confirmation") is True

    # 2. Confirmed without token should fail (before polkit prompt)
    res_no_token = dispatch(
        "vpn_create_client",
        {"name": "test-client", "confirmed": True},
        **_PEER,
    )
    assert res_no_token["status"] == "error"
    assert "token" in res_no_token["message"].lower()
    assert res_no_token.get("requires_polkit") is not True

    # 3. Confirmed with token should succeed
    token = session.issue_token()
    res_ok = dispatch(
        "vpn_create_client",
        {"name": "test-client", "confirmed": True, "session_token": token},
        **_PEER,
    )
    assert res_ok["status"] == "ok"
    mock_vpn.add_client.assert_called_once_with("test-client")

    # 4. Revoke client with token should succeed
    res_revoke_ok = dispatch(
        "vpn_revoke_client",
        {"name": "test-client", "confirmed": True, "session_token": token},
        **_PEER,
    )
    assert res_revoke_ok["status"] == "ok"
    mock_vpn.revoke_client.assert_called_once_with("test-client")


def test_privileged_confirmed_rejects_truthy_non_boolean(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    session = IPCSession()
    token = session.issue_token()
    dispatch = create_action_dispatcher(MagicMock(), session)

    for bad_confirmed in ("false", 1, [], "yes"):
        result = dispatch(
            "flush_dns",
            {"confirmed": bad_confirmed, "session_token": token},
            **_PEER,
        )
        assert result["status"] == "error"
        assert result.get("requires_confirmation") is True


def test_firewall_status_ipc():
    medic = MagicMock()
    medic.get_firewall_status.return_value = "ON"
    dispatch = create_action_dispatcher(medic, IPCSession())
    result = dispatch("firewall_status", {}, **_PEER)

    medic.get_firewall_status.assert_called_once()
    assert result["status"] == "ok"
    assert result["message"] == "ON"
    assert result["data"] == "ON"


@patch("netmedic.ipc_security.check_authorization", return_value=(False, "Polkit authorization denied."))
def test_privileged_requires_polkit_when_not_skipped(mock_polkit, tmp_path, monkeypatch):
    monkeypatch.delenv("NETMEDIC_SKIP_POLKIT", raising=False)
    session = IPCSession()
    token = session.issue_token()
    dispatch = create_action_dispatcher(MagicMock(), session)
    result = dispatch(
        "flush_dns",
        {"confirmed": True, "session_token": token},
        peer_uid=os.getuid(),
        peer_pid=1234,
    )
    assert result["status"] == "error"
    assert result.get("requires_polkit") is True
    mock_polkit.assert_called_once()


def test_invalid_token_does_not_invoke_polkit(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    session = IPCSession()
    session.issue_token()
    dispatch = create_action_dispatcher(MagicMock(), session)

    with patch("netmedic.ipc_security.check_authorization") as mock_polkit:
        result = dispatch(
            "flush_dns",
            {"confirmed": True, "session_token": "0" * 64},
            **_PEER,
        )
        assert result["status"] == "error"
        assert "token" in result["message"].lower()
        mock_polkit.assert_not_called()


def test_get_session_token_before_issue(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    dispatch = create_action_dispatcher(MagicMock(), IPCSession())
    result = dispatch("get_session_token", {}, **_PEER)
    assert result["status"] == "error"
    assert "not yet available" in result["message"].lower()


def test_change_dns_rejects_invalid_ip(tmp_path, monkeypatch):
    monkeypatch.setattr("netmedic.config.Config.get_state_dir", lambda: tmp_path)
    session = IPCSession()
    token = session.issue_token()
    medic = MagicMock()
    dispatch = create_action_dispatcher(medic, session)
    result = dispatch(
        "change_dns",
        {"server": "not-an-ip", "confirmed": True, "session_token": token},
        **_PEER,
    )
    assert result["status"] == "error"
    assert "invalid" in result["message"].lower()
    medic.change_dns.assert_not_called()


@patch("netmedic.ipc_actions.AngristanOperator")
def test_vpn_install_and_start_via_ipc(mock_vpn_cls):
    mock_vpn = MagicMock()
    mock_vpn.install.return_value = NetResult("VPN", True, "Installation successful")
    mock_vpn.start_service.return_value = NetResult("VPN", True, "VPN service started")
    mock_vpn_cls.return_value = mock_vpn

    session = IPCSession()
    token = session.issue_token()
    dispatch = create_action_dispatcher(MagicMock(), session)

    denied = dispatch("vpn_install", {}, **_PEER)
    assert denied.get("requires_confirmation") is True

    ok_install = dispatch(
        "vpn_install",
        {"confirmed": True, "session_token": token},
        **_PEER,
    )
    assert ok_install["status"] == "ok"
    mock_vpn.install.assert_called_once()

    ok_start = dispatch(
        "vpn_start_service",
        {"confirmed": True, "session_token": token},
        **_PEER,
    )
    assert ok_start["status"] == "ok"
    mock_vpn.start_service.assert_called_once()
