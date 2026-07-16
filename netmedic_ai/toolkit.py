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


def _run_tool(action: str, params: dict = None, default_sim: str = "Simulation") -> str:
    try:
        from netmedic.ipc_sync_client import SyncIPCClient
        client = SyncIPCClient()
        if client.is_available():
            res = client.request(action, params or {}, confirmed=True)
            if res.get("status") == "ok":
                msg = res.get("message", "OK")
                return f"Success: {msg}"
            return f"Error: {res.get('message', 'Unknown error')}"
    except Exception:
        pass
    return default_sim


registry = ActionRegistry()


@registry.register(
    name="vpn_reconnect",
    description="Fuerza la reconexión de una interfaz VPN activa si se detecta latencia crítica.",
    parameters={"interface": "string"},
)
def tool_vpn_reconnect(interface: str = "actual"):
    return _run_tool("vpn_reconnect", {}, f"Simulación: Reiniciando VPN en {interface}")


@registry.register(
    name="network_status",
    description="Obtiene el estado actual del stack de red, latencia y DNS.",
    parameters={},
)
def tool_network_status():
    return _run_tool("network_status", {}, "Simulación: Red estable, latencia 20ms.")


@registry.register(
    name="wifi_diagnostics",
    description="Analiza el espectro Wi-Fi buscando canales menos congestionados.",
    parameters={},
)
def tool_wifi_diagnostics():
    return _run_tool("wifi_diagnostics", {}, "Simulación: Escaneo Wi-Fi completado.")


@registry.register(
    name="flush_dns",
    description="Limpia la caché DNS del sistema.",
    parameters={},
)
def tool_flush_dns():
    return _run_tool("flush_dns", {}, "Simulación: Caché DNS limpiada.")


@registry.register(
    name="renew_ip",
    description="Renueva la dirección IP vía DHCP en la interfaz activa.",
    parameters={},
)
def tool_renew_ip():
    return _run_tool("renew_ip", {}, "Simulación: IP renovada.")


@registry.register(
    name="change_dns",
    description="Redirige la resolución de nombres a un servidor DNS específico.",
    parameters={"server": "string"},
)
def tool_change_dns(server: str = "1.1.1.1"):
    return _run_tool("change_dns", {"server": server}, f"Simulación: DNS cambiado a {server}.")


@registry.register(
    name="restart_adapter",
    description="Cycle the default network adapter down and up.",
    parameters={},
)
def tool_restart_adapter():
    return _run_tool("restart_adapter", {}, "Simulation: default adapter cycled.")


@registry.register(
    name="reset_tcp_ip_stack",
    description="Restart NetworkManager to reset the TCP/IP stack.",
    parameters={},
)
def tool_reset_tcp_ip_stack():
    return _run_tool("reset_tcp_ip_stack", {}, "Simulation: NetworkManager restarted.")


@registry.register(
    name="toggle_firewall",
    description="Toggle the UFW firewall on or off.",
    parameters={},
)
def tool_toggle_firewall():
    return _run_tool("toggle_firewall", {}, "Simulation: firewall toggled.")


@registry.register(
    name="donate",
    description="Muestra información sobre cómo apoyar el desarrollo de NetMedic.",
    parameters={},
)
def tool_donate():
    return _run_tool("donate", {}, (
        "Gracias por considerar apoyar el desarrollo de NetMedic. "
        "Puedes hacerlo en: https://www.buymeacoffee.com/kayabsoftware"
    ))