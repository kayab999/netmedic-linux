"""Validate tool parameters against the ActionRegistry schema."""
from __future__ import annotations

import re

from netmedic_ai.toolkit import registry

try:
    # Canonical validators (M4 single source) when netmedic is installed.
    from netmedic.validators import (
        ValidationError as _ValidationError,
        validate_dns as _validate_dns,
        validate_iface as _validate_iface,
    )
except ImportError:  # pragma: no cover - standalone netmedic_ai installs
    import ipaddress as _ipaddress

    class _ValidationError(ValueError):
        pass

    def _validate_dns(server: str) -> str:
        try:
            return str(_ipaddress.IPv4Address(server))
        except _ipaddress.AddressValueError:
            raise _ValidationError(f"Invalid DNS server IP: {server}") from None

    _IFACE_FB = re.compile(r"^[A-Za-z0-9._@+-]+$")

    def _validate_iface(iface: str, *, medic_only: bool = False) -> str:
        if not isinstance(iface, str) or not _IFACE_FB.fullmatch(iface):
            raise _ValidationError(f"Invalid interface name: {iface!r}")
        if iface.startswith("-") or len(iface) > 15:
            raise _ValidationError(f"Invalid interface name: {iface!r}")
        return iface


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
        try:
            _validate_dns(server)
        except _ValidationError:
            return f"Invalid DNS server IP: {server}"

    if action_name == "vpn_reconnect":
        iface = params.get("interface", "default")
        try:
            _validate_iface(iface)
        except _ValidationError:
            return f"Invalid interface name: {iface}"

    return None