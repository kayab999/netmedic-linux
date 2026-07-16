import logging

from netmedic_ai.param_validation import validate_tool_params
from netmedic_ai.toolkit import registry

logger = logging.getLogger(__name__)


class PilotoGuardrail:
    @staticmethod
    def execute_tool(action_name: str, params: dict) -> dict:
        if not registry.is_registered(action_name):
            logger.error(
                "Security block: attempt to call unregistered tool '%s'.",
                action_name,
            )
            return {
                "status": "error",
                "message": "Action not permitted by the pilot guardrail.",
            }

        param_error = validate_tool_params(action_name, params)
        if param_error:
            return {"status": "error", "message": param_error}

        tool = registry.get_tool(action_name)

        try:
            logger.info(
                "Pilot executing: %s with parameters %s",
                action_name,
                params,
            )
            result = tool["impl"](**params)
            if isinstance(result, str) and result.startswith("Error:"):
                return {"status": "error", "message": result[6:].strip()}
            return {"status": "success", "data": result}
        except Exception as exc:
            logger.error(
                "Tool execution failed for %s: %s",
                action_name,
                exc,
            )
            return {
                "status": "error",
                "message": "Internal error while executing the action.",
            }