import pytest
from netmedic_ai.guardrail import PilotoGuardrail
from netmedic_ai.param_validation import validate_tool_params

pytestmark = pytest.mark.ai


def test_validate_change_dns_rejects_invalid_ip():
    assert validate_tool_params("change_dns", {"server": "not-an-ip"}) is not None


def test_validate_change_dns_accepts_valid_ip():
    assert validate_tool_params("change_dns", {"server": "1.1.1.1"}) is None


def test_guardrail_rejects_unknown_param():
    result = PilotoGuardrail.execute_tool("change_dns", {"server": "1.1.1.1", "evil": "1"})
    assert result["status"] == "error"
    assert "Unexpected parameter" in result["message"]