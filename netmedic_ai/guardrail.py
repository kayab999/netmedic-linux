# /home/carlos/netmedic_linux/netmedic_ai/guardrail.py
from .toolkit import registry
import logging

class PilotoGuardrail:
    @staticmethod
    def execute_tool(action_name: str, params: dict):
        """
        Valida y ejecuta una herramienta solicitada por el modelo.
        """
        if not registry.is_registered(action_name):
            logging.error(f"Bloqueo de seguridad: Intento de llamar a herramienta no registrada '{action_name}'.")
            return {"status": "error", "message": "Acción no permitida por la Constitución del Piloto."}
        
        tool = registry.get_tool(action_name)
        
        try:
            logging.info(f"Piloto ejecutando: {action_name} con parámetros {params}")
            result = tool["impl"](**params)
            return {"status": "success", "data": result}
        except Exception as e:
            logging.error(f"Fallo durante la ejecución de la herramienta {action_name}: {e}")
            return {"status": "error", "message": "Fallo interno al ejecutar la acción."}
