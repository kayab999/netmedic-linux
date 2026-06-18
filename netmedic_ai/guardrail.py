import logging

from netmedic_ai.toolkit import registry

logger = logging.getLogger(__name__)


class PilotoGuardrail:
    @staticmethod
    def execute_tool(action_name: str, params: dict) -> dict:
        if not registry.is_registered(action_name):
            logger.error(
                "Bloqueo de seguridad: Intento de llamar a herramienta no registrada '%s'.",
                action_name,
            )
            return {
                "status": "error",
                "message": "Acción no permitida por la Constitución del Piloto.",
            }

        tool = registry.get_tool(action_name)

        try:
            logger.info(
                "Piloto ejecutando: %s con parámetros %s",
                action_name,
                params,
            )
            result = tool["impl"](**params)
            return {"status": "success", "data": result}
        except Exception as exc:
            logger.error(
                "Fallo durante la ejecución de la herramienta %s: %s",
                action_name,
                exc,
            )
            return {
                "status": "error",
                "message": "Fallo interno al ejecutar la acción.",
            }