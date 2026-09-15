"""GUI action bridge maps IPC payloads and routes privileged work correctly."""

from unittest.mock import MagicMock

from netmedic.gui_actions import GuiActionBridge, payload_to_net_result
from netmedic.models import ResultCode
from netmedic.operators.vpn.base import VPNClient


def test_payload_to_net_result_success():
    res = payload_to_net_result(
        "flush_dns",
        {"status": "ok", "success": True, "message": "flushed"},
    )
    assert res.success is True
    assert res.operation == "Flush DNS"
    assert res.message == "flushed"


def test_payload_to_net_result_error_with_polkit_hint():
    res = payload_to_net_result(
        "flush_dns",
        {
            "status": "error",
            "message": "denied",
            "requires_polkit": True,
        },
    )
    assert res.success is False
    assert "polkit" in (res.details or "").lower()


def test_payload_failed_diagnostics_keeps_dict_details():
    """WAN-down diagnostics ship details as a dict; .lower() on that used to crash Smart Repair."""
    details = {
        "gateway": "none",
        "gateway_ok": False,
        "dns_probe": "none",
        "net_probe": "none",
        "per_probe": {"gw_ok": False, "dns_ok": False, "internet_ok": False},
    }
    res = payload_to_net_result(
        "network_status",
        {
            "status": "error",
            "code": "failed",
            "message": "Gateway Not Found | DNS Resolution Failed | No Internet Access",
            "details": details,
            "data": {"gateway_ok": False, "dns_ok": False, "internet_ok": False},
        },
    )
    assert res.code == ResultCode.FAILED
    assert isinstance(res.details, dict)
    assert res.details["gateway_ok"] is False


def test_payload_failed_dict_details_keeps_helper_hint():
    details = {"gateway_ok": False}
    res = payload_to_net_result(
        "network_status",
        {
            "status": "error",
            "code": "error",
            "message": "helper-missing",
            "details": details,
        },
    )
    assert isinstance(res.details, dict)
    assert res.details["gateway_ok"] is False
    assert "helper missing" in res.details["helper_hint"]


def test_payload_vpn_list_converts_dicts():
    res = payload_to_net_result(
        "vpn_list_clients",
        {
            "status": "ok",
            "message": "ok",
            "data": [
                {"name": "laptop", "active": True},
                {"name": "phone", "active": False},
            ],
        },
    )
    assert res.success is True
    assert isinstance(res.data[0], VPNClient)
    assert res.data[0].name == "laptop"
    assert res.data[0].active is True
    assert res.data[1].active is False


def test_bridge_unavailable():
    client = MagicMock()
    client.is_available.return_value = False
    bridge = GuiActionBridge(client=client)
    res = bridge.call("network_status")
    assert res.success is False
    assert "not available" in res.message.lower()
    client.request.assert_not_called()


def test_bridge_privileged_defaults_confirmed():
    client = MagicMock()
    client.is_available.return_value = True
    client.request.return_value = {
        "status": "ok",
        "success": True,
        "message": "done",
    }
    bridge = GuiActionBridge(client=client)
    res = bridge.call("flush_dns")
    assert res.success is True
    client.request.assert_called_once_with("flush_dns", {}, confirmed=True)


def test_bridge_safe_action_not_auto_confirmed():
    client = MagicMock()
    client.is_available.return_value = True
    client.request.return_value = {
        "status": "ok",
        "success": True,
        "message": "Gateway Reachable",
    }
    bridge = GuiActionBridge(client=client)
    res = bridge.call("network_status")
    assert res.success is True
    client.request.assert_called_once_with("network_status", {}, confirmed=False)


def test_bridge_explicit_confirmed_override():
    client = MagicMock()
    client.is_available.return_value = True
    client.request.return_value = {"status": "ok", "message": "ok"}
    bridge = GuiActionBridge(client=client)
    bridge.call("network_status", confirmed=True)
    client.request.assert_called_once_with("network_status", {}, confirmed=True)
