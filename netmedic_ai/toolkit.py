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


def _run_tool(action: str, params: dict | None = None) -> str:
    """Execute via IPC when the daemon is available; fail closed otherwise."""
    try:
        from netmedic.ipc_sync_client import SyncIPCClient

        client = SyncIPCClient()
        if not client.is_available():
            return "Error: NetMedic daemon is not running. Start the GUI or run: netmedic --headless"
        res = client.request(action, params or {}, confirmed=True)
        if res.get("status") == "ok":
            msg = res.get("message", "OK")
            return f"Success: {msg}"
        return f"Error: {res.get('message', 'Unknown error')}"
    except Exception as exc:
        return f"Error: {exc}"


registry = ActionRegistry()


@registry.register(
    name="vpn_reconnect",
    description="Force reconnection of an active VPN interface when critical latency is detected.",
    parameters={"interface": "string"},
)
def tool_vpn_reconnect(interface: str = "default"):
    return _run_tool("vpn_reconnect", {"interface": interface})


@registry.register(
    name="network_status",
    description="Get current network stack status, latency, and DNS health.",
    parameters={},
)
def tool_network_status():
    return _run_tool("network_status")


@registry.register(
    name="wifi_diagnostics",
    description="Analyze the Wi-Fi spectrum for less congested channels.",
    parameters={},
)
def tool_wifi_diagnostics():
    return _run_tool("wifi_diagnostics")


@registry.register(
    name="flush_dns",
    description="Clear the system DNS resolver cache.",
    parameters={},
)
def tool_flush_dns():
    return _run_tool("flush_dns")


@registry.register(
    name="renew_ip",
    description="Renew the IP address via DHCP on the active interface.",
    parameters={},
)
def tool_renew_ip():
    return _run_tool("renew_ip")


@registry.register(
    name="change_dns",
    description="Redirect name resolution to a specific DNS server.",
    parameters={"server": "string"},
)
def tool_change_dns(server: str = "1.1.1.1"):
    return _run_tool("change_dns", {"server": server})


@registry.register(
    name="restart_adapter",
    description="Cycle the default network adapter down and up.",
    parameters={},
)
def tool_restart_adapter():
    return _run_tool("restart_adapter")


@registry.register(
    name="reset_tcp_ip_stack",
    description="Restart NetworkManager to reset the TCP/IP stack.",
    parameters={},
)
def tool_reset_tcp_ip_stack():
    return _run_tool("reset_tcp_ip_stack")


@registry.register(
    name="toggle_firewall",
    description="Toggle the UFW firewall on or off.",
    parameters={},
)
def tool_toggle_firewall():
    return _run_tool("toggle_firewall")


@registry.register(
    name="donate",
    description="Show information about supporting NetMedic development.",
    parameters={},
)
def tool_donate():
    return _run_tool("donate")