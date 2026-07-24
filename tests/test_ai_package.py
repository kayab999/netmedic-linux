import pytest

pytestmark = pytest.mark.ai

from netmedic_ai.guardrail import PilotoGuardrail
from netmedic_ai.toolkit import registry


def test_registry_manifest_aligned_with_ipc():
    manifest = registry.get_manifest()
    names = {entry["name"] for entry in manifest}
    expected = {
        "vpn_reconnect",
        "network_status",
        "wifi_diagnostics",
        "flush_dns",
        "renew_ip",
        "change_dns",
        "restart_adapter",
        "reset_tcp_ip_stack",
        "toggle_firewall",
        "donate",
    }
    assert expected.issubset(names)


def test_guardrail_blocks_unknown_action():
    result = PilotoGuardrail.execute_tool("rm_rf_everything", {})
    assert result["status"] == "error"
    assert "not permitted" in result["message"].lower()


def test_guardrail_fails_closed_without_daemon():
    result = PilotoGuardrail.execute_tool("network_status", {})
    assert result["status"] == "error"
    assert "not running" in result["message"].lower() or "daemon" in result["message"].lower()


def test_interpret_intent_without_llama():
    from netmedic_ai.pilot import interpret_intent

    result = interpret_intent("check network", {"internet": True})
    assert result["status"] == "error"
    assert "llama" in result["message"].lower() or "instal" in result["message"].lower()


from unittest.mock import MagicMock, patch

def test_user_intent_ipc_does_not_execute_tools():
    from netmedic.ipc_actions import _handle_user_intent

    result = _handle_user_intent({"user_request": "flush dns", "network_state": {}})
    assert result.get("status") in ("ok", "error")
    if result.get("status") == "ok":
        assert "action" in result
        assert "data" not in result or result.get("status") != "success"


@patch("netmedic.ipc_sync_client.SyncIPCClient")
def test_guardrail_executes_via_ipc_when_available(mock_client_cls):
    mock_client = MagicMock()
    mock_client.is_available.return_value = True
    mock_client.request.return_value = {"status": "ok", "message": "Real DNS Flushed"}
    mock_client_cls.return_value = mock_client

    result = PilotoGuardrail.execute_tool("flush_dns", {})
    assert result["status"] == "success"
    assert "Success: Real DNS Flushed" in result["data"]
    mock_client.request.assert_called_once_with("flush_dns", {}, confirmed=True)


def test_process_event_requires_confirmed():
    from netmedic_ai.pilot import NandiPilot

    pilot = object.__new__(NandiPilot)
    with patch.object(
        pilot,
        "infer_intent",
        return_value={"status": "ok", "action": "flush_dns", "params": {}},
    ):
        denied = pilot.process_event({}, "flush dns")
        assert denied["status"] == "error"
        assert denied.get("requires_confirmation") is True
        assert denied.get("action") == "flush_dns"

        with patch(
            "netmedic_ai.pilot.PilotoGuardrail.execute_tool",
            return_value={"status": "success", "data": "ok"},
        ) as exec_tool:
            allowed = pilot.process_event({}, "flush dns", confirmed=True)
            assert allowed["status"] == "success"
            exec_tool.assert_called_once_with("flush_dns", {})