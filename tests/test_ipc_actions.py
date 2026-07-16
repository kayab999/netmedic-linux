from unittest.mock import MagicMock, patch

from netmedic.ipc_actions import create_action_dispatcher
from netmedic.ipc_security import IPCSession
from netmedic.models import NetResult


@patch("netmedic.ipc_actions.AngristanOperator")
def test_vpn_reconnect_restarts_vpn_not_network_stack(mock_vpn_cls):
    mock_vpn = MagicMock()
    mock_vpn.restart_service.return_value = NetResult("VPN", True, "VPN tunnel restarted")
    mock_vpn_cls.return_value = mock_vpn

    medic = MagicMock()
    session = IPCSession()
    token = session.issue_token()
    dispatch = create_action_dispatcher(medic, session)

    result = dispatch("vpn_reconnect", {"confirmed": True, "session_token": token})

    mock_vpn.restart_service.assert_called_once()
    medic.reset_tcp_ip_stack.assert_not_called()
    assert result["status"] == "ok"
    assert "VPN" in result["message"]


def test_donate_action_returns_url():
    session = IPCSession()
    dispatch = create_action_dispatcher(MagicMock(), session)
    result = dispatch("donate", {})

    assert result["status"] == "ok"
    assert "buymeacoffee.com" in result["url"]


@patch("netmedic.ipc_actions.AngristanOperator")
def test_vpn_status_ipc(mock_vpn_cls):
    mock_vpn = MagicMock()
    mock_vpn.check_status.return_value = NetResult("VPN status", True, "RUNNING")
    mock_vpn_cls.return_value = mock_vpn

    dispatch = create_action_dispatcher(MagicMock(), IPCSession())
    result = dispatch("vpn_status", {})

    mock_vpn.check_status.assert_called_once()
    assert result["status"] == "ok"
    assert result["message"] == "RUNNING"


@patch("netmedic.ipc_actions.AngristanOperator")
def test_vpn_list_clients_ipc(mock_vpn_cls):
    from netmedic.operators.vpn.base import VPNClient
    mock_vpn = MagicMock()
    mock_vpn.list_clients.return_value = NetResult(
        "VPN clients", True, "clients retrieved",
        data=[VPNClient(name="carlos-laptop", active=True), VPNClient(name="old-phone", active=False)]
    )
    mock_vpn_cls.return_value = mock_vpn

    dispatch = create_action_dispatcher(MagicMock(), IPCSession())
    result = dispatch("vpn_list_clients", {})

    mock_vpn.list_clients.assert_called_once()
    assert result["status"] == "ok"
    assert result["data"] == [
        {"name": "carlos-laptop", "active": True},
        {"name": "old-phone", "active": False}
    ]


@patch("netmedic.ipc_actions.AngristanOperator")
def test_vpn_create_and_revoke_client_security(mock_vpn_cls):
    mock_vpn = MagicMock()
    mock_vpn.add_client.return_value = NetResult("VPN", True, "Client created")
    mock_vpn.revoke_client.return_value = NetResult("VPN", True, "Client revoked")
    mock_vpn_cls.return_value = mock_vpn

    session = IPCSession()
    dispatch = create_action_dispatcher(MagicMock(), session)

    # 1. Unconfirmed create should fail
    res_fail = dispatch("vpn_create_client", {"name": "test-client"})
    assert res_fail["status"] == "error"
    assert res_fail.get("requires_confirmation") is True

    # 2. Confirmed without token should fail
    res_no_token = dispatch("vpn_create_client", {"name": "test-client", "confirmed": True})
    assert res_no_token["status"] == "error"
    assert "token" in res_no_token["message"].lower()

    # 3. Confirmed with token should succeed
    token = session.issue_token()
    res_ok = dispatch("vpn_create_client", {"name": "test-client", "confirmed": True, "session_token": token})
    assert res_ok["status"] == "ok"
    mock_vpn.add_client.assert_called_once_with("test-client")

    # 4. Revoke client with token should succeed
    res_revoke_ok = dispatch("vpn_revoke_client", {"name": "test-client", "confirmed": True, "session_token": token})
    assert res_revoke_ok["status"] == "ok"
    mock_vpn.revoke_client.assert_called_once_with("test-client")