from functools import wraps

class ActionRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, name, description, parameters):
        """
        Decorador para exponer funciones seguras a Nandi Mini.
        """
        def decorator(func):
            self._tools[name] = {
                "impl": func,
                "description": description,
                "parameters": parameters
            }
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator

    def get_manifest(self):
        """Retorna el JSON de capacidades para inyectar en el prompt del modelo."""
        return [
            {
                "name": name,
                "description": data["description"],
                "parameters": data["parameters"]
            }
            for name, data in self._tools.items()
        ]

    def get_tool(self, name):
        return self._tools.get(name)

    def is_registered(self, name):
        return name in self._tools

# Instancia global del registro
registry = ActionRegistry()

# --- Ejemplo de Integración con el Core ---
# (Asumiendo que importarás tus operadores reales de NetMedic aquí)

@registry.register(
    name="vpn_reconnect",
    description="Fuerza la reconexión de una interfaz VPN activa si se detecta latencia crítica.",
    parameters={"interface": "string"}
)
def tool_vpn_reconnect(interface: str):
    # Aquí llamas al NetMedic Core real
    return f"Simulación: Reiniciando VPN en {interface}"

@registry.register(
    name="network_status",
    description="Obtiene el estado actual del stack de red, latencia y DNS.",
    parameters={}
)
def tool_network_status():
    return "Simulación: Red estable, latencia 20ms."

@registry.register(
    name="donate",
    description="Muestra información sobre cómo apoyar el desarrollo de NetMedic.",
    parameters={}
)
def tool_donate():
    return "Gracias por considerar apoyar el desarrollo de NetMedic. Puedes hacerlo en: https://www.buymeacoffee.com/kayabsoftware"
