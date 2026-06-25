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