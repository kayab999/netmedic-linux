"""Validate tool parameters against the ActionRegistry schema."""
from __future__ import annotations

import re

from netmedic_ai.toolkit import registry

_DNS_IP_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)


def validate_tool_params(action_name: str, params: dict) -> str | None:
    """Return an error message if params are invalid, else None."""
    tool = registry.get_tool(action_name)
    if not tool:
        return f"Unknown tool: {action_name}"

    schema: dict = tool.get("parameters", {})
    if not isinstance(params, dict):
        return "Parameters must be a dictionary."

    for key, value in params.items():
        if key not in schema:
            return f"Unexpected parameter: {key}"
        if not isinstance(value, str):
            return f"Parameter '{key}' must be a string."

    if action_name == "change_dns":
        server = params.get("server", "1.1.1.1")
        if not _DNS_IP_RE.match(server):
            return f"Invalid DNS server IP: {server}"

    if action_name == "vpn_reconnect":
        iface = params.get("interface", "default")
        if not re.match(r"^[a-zA-Z0-9._-]+$", iface):
            return f"Invalid interface name: {iface}"

    return None