from functools import wraps


class ActionRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, name, description, parameters):
        def decorator(func):
            self._tools[name] = {
                "impl": func,
                "description": description,
                "parameters": parameters,
            }

            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)

            return wrapper

        return decorator

    def get_manifest(self):
        return [
            {
                "name": name,
                "description": data["description"],
                "parameters": data["parameters"],
            }
            for name, data in self._tools.items()
        ]

    def get_tool(self, name):
        return self._tools.get(name)

    def is_registered(self, name):
        return name in self._tools


registry = ActionRegistry()


@registry.register(
    name="vpn_reconnect",
    description="Fuerza la reconexión de una interfaz VPN activa si se detecta latencia crítica.",
    parameters={"interface": "string"},
)
def tool_vpn_reconnect(interface: str = "actual"):
    return f"Simulación: Reiniciando VPN en {interface}"


@registry.register(
    name="network_status",
    description="Obtiene el estado actual del stack de red, latencia y DNS.",
    parameters={},
)
def tool_network_status():
    return "Simulación: Red estable, latencia 20ms."


@registry.register(
    name="wifi_diagnostics",
    description="Analiza el espectro Wi-Fi buscando canales menos congestionados.",
    parameters={},
)
def tool_wifi_diagnostics():
    return "Simulación: Escaneo Wi-Fi completado."


@registry.register(
    name="flush_dns",
    description="Limpia la caché DNS del sistema.",
    parameters={},
)
def tool_flush_dns():
    return "Simulación: Caché DNS limpiada."


@registry.register(
    name="renew_ip",
    description="Renueva la dirección IP vía DHCP en la interfaz activa.",
    parameters={},
)
def tool_renew_ip():
    return "Simulación: IP renovada."


@registry.register(
    name="change_dns",
    description="Redirige la resolución de nombres a un servidor DNS específico.",
    parameters={"server": "string"},
)
def tool_change_dns(server: str = "1.1.1.1"):
    return f"Simulación: DNS cambiado a {server}."


@registry.register(
    name="donate",
    description="Muestra información sobre cómo apoyar el desarrollo de NetMedic.",
    parameters={},
)
def tool_donate():
    return (
        "Gracias por considerar apoyar el desarrollo de NetMedic. "
        "Puedes hacerlo en: https://www.buymeacoffee.com/kayabsoftware"
    )