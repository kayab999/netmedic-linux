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
        "donate",
    }
    assert expected.issubset(names)


def test_guardrail_blocks_unknown_action():
    result = PilotoGuardrail.execute_tool("rm_rf_everything", {})
    assert result["status"] == "error"
    assert "no permitida" in result["message"]


def test_guardrail_executes_registered_tool():
    result = PilotoGuardrail.execute_tool("network_status", {})
    assert result["status"] == "success"
    assert "Red estable" in result["data"]


def test_interpret_intent_without_llama():
    from netmedic_ai.pilot import interpret_intent

    result = interpret_intent("check network", {"internet": True})
    assert result["status"] == "error"
    assert "llama" in result["message"].lower() or "instal" in result["message"].lower()